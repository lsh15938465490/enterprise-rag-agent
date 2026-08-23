"""知识库 CRUD 和 ACL（授权名单）。"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok
from app.core.deps import get_current_user, require_roles
from app.core.exceptions import AppError
from app.core.limits import max_documents_per_kb, max_knowledge_bases_per_tenant
from app.db.models import Document, DocStatus, KnowledgeBase, KnowledgeBaseAcl, Tenant, User, UserRole
from app.db.session import get_db
from app.schemas.dto import AclPutIn, KnowledgeBaseCreateIn, KnowledgeBaseDTO, KnowledgeBasePatchIn
from app.services.acl import get_kb, readable_kb_ids, require_read, require_write
from app.services.qdrant_store import ensure_collection

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _coll_name(slug: str, kb_id: UUID) -> str:
    """Qdrant 集合名：租户 slug + 知识库 id，避免不同公司撞名。"""
    return f"kb_{slug}_{kb_id.hex}"


@router.get("")
async def list_kbs(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """只返回当前用户有权读的知识库。"""
    ids = await readable_kb_ids(db, user)
    if not ids:
        return ok(request, [])
    rows = (
        await db.scalars(
            select(KnowledgeBase).where(KnowledgeBase.id.in_(ids)).order_by(KnowledgeBase.created_at.desc())
        )
    ).all()
    return ok(request, [KnowledgeBaseDTO.model_validate(r).model_dump(mode="json") for r in rows])


@router.post("")
async def create_kb(
    request: Request,
    body: KnowledgeBaseCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.kb_editor, UserRole.tenant_admin)),
):
    """新建知识库，并在 Qdrant 建同名向量集合。名称冲突返回 409。"""
    tenant = await db.scalar(select(Tenant).where(Tenant.id == user.tenant_id))
    if tenant is None:
        raise AppError(40004, "资源不存在", 404)
    kb_count = int(
        await db.scalar(
            select(func.count())
            .select_from(KnowledgeBase)
            .where(KnowledgeBase.tenant_id == user.tenant_id, KnowledgeBase.is_active.is_(True))
        )
        or 0
    )
    if kb_count >= max_knowledge_bases_per_tenant():
        raise AppError(40022, f"知识库最多 {max_knowledge_bases_per_tenant()} 个，请先删除后再创建", 422)
    from uuid import uuid4

    kb_id = uuid4()
    kb = KnowledgeBase(
        id=kb_id,
        tenant_id=user.tenant_id,
        name=body.name,
        description=body.description,
        created_by=user.id,
        qdrant_collection=_coll_name(tenant.slug, kb_id),
    )
    db.add(kb)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError(40901, "知识库名称已存在", 409) from None
    await db.refresh(kb)
    await ensure_collection(kb.qdrant_collection, kb.embedding_dim)
    return ok(request, KnowledgeBaseDTO.model_validate(kb).model_dump(mode="json"), 201)


@router.get("/{kb_id}")
async def get_one(
    request: Request,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """知识库详情，需要读权限。"""
    kb = await get_kb(db, kb_id, user.tenant_id)
    await require_read(db, user, kb)
    return ok(request, KnowledgeBaseDTO.model_validate(kb).model_dump(mode="json"))


@router.get("/{kb_id}/stats")
async def kb_stats(
    request: Request,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """知识库统计（无前端页面）。停用库对普通用户不可见。"""
    kb = await get_kb(db, kb_id, user.tenant_id)
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
    kb = await get_kb(db, kb_id, user.tenant_id)
    await require_write(db, user, kb)
    if body.name is not None:
        kb.name = body.name
    if body.description is not None:
        kb.description = body.description
    if body.is_active is not None:
        kb.is_active = body.is_active
    await db.commit()
    await db.refresh(kb)
    return ok(request, KnowledgeBaseDTO.model_validate(kb).model_dump(mode="json"))


@router.delete("/{kb_id}")
async def delete_kb(
    request: Request,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """软删除：只停用，不物理删文件。"""
    kb = await get_kb(db, kb_id, user.tenant_id)
    await require_write(db, user, kb)
    kb.is_active = False
    await db.commit()
    return ok(request, {"id": str(kb.id), "is_active": False})


@router.get("/{kb_id}/acl")
async def get_acl(
    request: Request,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看谁被授权读写这个库。"""
    kb = await get_kb(db, kb_id, user.tenant_id)
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
    """整表替换授权名单；user_id 必须是本租户用户。"""
    kb = await get_kb(db, kb_id, user.tenant_id)
    await require_write(db, user, kb)
    user_ids = [item.user_id for item in body.items]
    if user_ids:
        tenant_users = set(
            await db.scalars(
                select(User.id).where(User.id.in_(user_ids), User.tenant_id == user.tenant_id)
            )
        )
        if len(tenant_users) != len(set(user_ids)):
            raise AppError(40022, "ACL 只能授予本租户用户", 422)
    existing = (await db.scalars(select(KnowledgeBaseAcl).where(KnowledgeBaseAcl.knowledge_base_id == kb.id))).all()
    for row in existing:
        await db.delete(row)
    for item in body.items:
        db.add(
            KnowledgeBaseAcl(
                knowledge_base_id=kb.id,
                user_id=item.user_id,
                can_read=item.can_read,
                can_write=item.can_write,
            )
        )
    await db.commit()
    return ok(request, {"updated": len(body.items)})
