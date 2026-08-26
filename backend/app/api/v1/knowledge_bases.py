"""知识库 CRUD 和 ACL（授权名单）。"""

import shutil
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok
from app.core.config import settings
from app.core.deps import get_current_user, require_roles
from app.core.exceptions import AppError
from app.core.limits import SUPER_ADMIN_USERNAME, max_documents_per_kb, max_knowledge_bases_per_tenant
from app.db.models import Document, DocStatus, KnowledgeBase, KnowledgeBaseAcl, Tenant, User, UserRole
from app.db.session import get_db
from app.schemas.dto import AclPutIn, KnowledgeBaseCreateIn, KnowledgeBaseDTO, KnowledgeBasePatchIn
from app.services.acl import get_kb, is_super_admin, readable_kb_ids, require_read, require_write
from app.services.qdrant_store import delete_collection, ensure_collection
from app.services.storage import delete_file

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _coll_name(slug: str, kb_id: UUID) -> str:
    """Qdrant 集合名：租户 slug + 知识库 id，避免不同公司撞名。"""
    return f"kb_{slug}_{kb_id.hex}"


def _kb_dump(kb: KnowledgeBase, tenant: Tenant | None) -> dict:
    data = KnowledgeBaseDTO.model_validate(kb).model_dump(mode="json")
    data["tenant_slug"] = tenant.slug if tenant else None
    data["tenant_name"] = tenant.name if tenant else None
    return data


@router.get("")
async def list_kbs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    for_qa: bool = Query(False, description="智能问答下拉：只返回启用中的知识库"),
):
    """只返回当前用户有权读的知识库。管理页含停用库；问答选库不含。"""
    ids = await readable_kb_ids(db, user, active_only=for_qa)
    if not ids:
        return ok(request, [])
    rows = (
        await db.scalars(
            select(KnowledgeBase).where(KnowledgeBase.id.in_(ids)).order_by(KnowledgeBase.created_at.desc())
        )
    ).all()
    tenants = {
        t.id: t
        for t in (
            await db.scalars(select(Tenant).where(Tenant.id.in_({r.tenant_id for r in rows})))
        ).all()
    }
    return ok(request, [_kb_dump(r, tenants.get(r.tenant_id)) for r in rows])


@router.post("")
async def create_kb(
    request: Request,
    body: KnowledgeBaseCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.kb_editor, UserRole.tenant_admin)),
):
    """新建知识库，并在 Qdrant 建同名向量集合。名称冲突返回 409。"""
    tenant_id = user.tenant_id
    if is_super_admin(user):
        tenant_id = body.tenant_id
        if tenant_id is None:
            demo = await db.scalar(select(Tenant).where(Tenant.slug == "demo"))
            tenant_id = demo.id if demo else None
    if tenant_id is None:
        raise AppError(40022, "请选择部门", 422)
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise AppError(40004, "资源不存在", 404)
    kb_count = int(
        await db.scalar(
            select(func.count())
            .select_from(KnowledgeBase)
            .where(KnowledgeBase.tenant_id == tenant_id, KnowledgeBase.is_active.is_(True))
        )
        or 0
    )
    if kb_count >= max_knowledge_bases_per_tenant():
        raise AppError(40022, f"知识库最多 {max_knowledge_bases_per_tenant()} 个，请先删除后再创建", 422)
    from uuid import uuid4

    kb_id = uuid4()
    kb = KnowledgeBase(
        id=kb_id,
        tenant_id=tenant_id,
        name=body.name,
        description=(body.description or "").strip() or None,
        created_by=user.id,
        qdrant_collection=_coll_name(tenant.slug, kb_id),
    )
    db.add(kb)
    if not is_super_admin(user):
        db.add(
            KnowledgeBaseAcl(
                knowledge_base_id=kb_id,
                user_id=user.id,
                can_read=True,
                can_write=False,
            )
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError(40901, "知识库名称已存在", 409) from None
    await db.refresh(kb)
    await ensure_collection(kb.qdrant_collection, kb.embedding_dim)
    return ok(request, _kb_dump(kb, tenant), 201)


@router.get("/{kb_id}")
async def get_one(
    request: Request,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """知识库详情，需要读权限。"""
    kb = await get_kb(db, kb_id, user)
    await require_read(db, user, kb)
    tenant = await db.scalar(select(Tenant).where(Tenant.id == kb.tenant_id))
    return ok(request, _kb_dump(kb, tenant))


@router.get("/{kb_id}/stats")
async def kb_stats(
    request: Request,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """知识库统计（无前端页面）。停用库对普通用户不可见。"""
    kb = await get_kb(db, kb_id, user)
    await require_read(db, user, kb)
    total = int(
        await db.scalar(select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb.id)) or 0
    )
    ready = int(
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.knowledge_base_id == kb.id, Document.status == DocStatus.ready)
        )
        or 0
    )
    failed = int(
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.knowledge_base_id == kb.id, Document.status == DocStatus.failed)
        )
        or 0
    )
    return ok(
        request,
        {
            "knowledge_base_id": str(kb.id),
            "name": kb.name,
            "is_active": kb.is_active,
            "document_total": total,
            "document_ready": ready,
            "document_failed": failed,
            "document_limit": max_documents_per_kb(),
        },
    )


@router.patch("/{kb_id}")
async def patch_kb(
    request: Request,
    kb_id: UUID,
    body: KnowledgeBasePatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """改名称、描述、启用状态。"""
    kb = await get_kb(db, kb_id, user)
    await require_write(db, user, kb)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        kb.name = data["name"]
    if "description" in data:
        kb.description = (data["description"] or "").strip() or None
    if "is_active" in data and data["is_active"] is not None:
        kb.is_active = data["is_active"]
    await db.commit()
    await db.refresh(kb)
    tenant = await db.scalar(select(Tenant).where(Tenant.id == kb.tenant_id))
    return ok(request, _kb_dump(kb, tenant))


@router.delete("/{kb_id}")
async def delete_kb(
    request: Request,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """真实删除知识库：文档、切块、向量集合一并去掉。"""
    kb = await get_kb(db, kb_id, user)
    await require_write(db, user, kb)
    docs = (await db.scalars(select(Document).where(Document.knowledge_base_id == kb.id))).all()
    for doc in docs:
        delete_file(doc.storage_key)
    folder = Path(settings.UPLOAD_DIR) / str(kb.tenant_id) / str(kb.id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    coll = kb.qdrant_collection
    await db.delete(kb)
    await db.commit()
    await delete_collection(coll)
    return ok(request, {"deleted": True})


@router.get("/{kb_id}/acl")
async def get_acl(
    request: Request,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看谁被授权读写这个库。"""
    kb = await get_kb(db, kb_id, user)
    await require_write(db, user, kb)
    rows = (await db.scalars(select(KnowledgeBaseAcl).where(KnowledgeBaseAcl.knowledge_base_id == kb.id))).all()
    return ok(
        request,
        [
            {"user_id": str(r.user_id), "can_read": r.can_read, "can_write": r.can_write}
            for r in rows
        ],
    )


@router.put("/{kb_id}/acl")
async def put_acl(
    request: Request,
    kb_id: UUID,
    body: AclPutIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.kb_editor, UserRole.tenant_admin)),
):
    """超管可改该部门全部用户授权；部门管理员只改普通用户，管理者那一层授权保留。"""
    kb = await get_kb(db, kb_id, user)
    await require_write(db, user, kb)
    tenant_users = (await db.scalars(select(User).where(User.tenant_id == kb.tenant_id))).all()
    if is_super_admin(user):
        scope_ids = {u.id for u in tenant_users if u.role != UserRole.super_admin and u.username != SUPER_ADMIN_USERNAME}
    else:
        scope_ids = {
            u.id
            for u in tenant_users
            if u.role not in {UserRole.super_admin, UserRole.tenant_admin}
        }
    item_ids = {item.user_id for item in body.items}
    if not item_ids.issubset(scope_ids):
        raise AppError(40022, "只能授权给本部门用户", 422)
    existing = (await db.scalars(select(KnowledgeBaseAcl).where(KnowledgeBaseAcl.knowledge_base_id == kb.id))).all()
    for row in existing:
        if row.user_id in scope_ids:
            await db.delete(row)
    for item in body.items:
        db.add(
            KnowledgeBaseAcl(
                knowledge_base_id=kb.id,
                user_id=item.user_id,
                can_read=item.can_read,
                can_write=False,
            )
        )
    await db.commit()
    return ok(request, {"updated": len(body.items)})
