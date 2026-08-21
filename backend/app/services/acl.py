"""知识库权限判断：管理员、创建人、或 ACL 表里勾了可读/可写。"""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.db.models import KnowledgeBase, KnowledgeBaseAcl, User, UserRole


def is_tenant_admin(user: User) -> bool:
    return user.role in {UserRole.super_admin, UserRole.tenant_admin}


async def get_kb(db: AsyncSession, kb_id: UUID, tenant_id: UUID) -> KnowledgeBase:
    kb = await db.scalar(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == tenant_id)
    )
    if kb is None:
        raise AppError(40004, "资源不存在", 404)
    return kb


async def user_can_read_kb(db: AsyncSession, user: User, kb: KnowledgeBase) -> bool:
    if kb.tenant_id != user.tenant_id:
        return False
    if is_tenant_admin(user) or kb.created_by == user.id:
        return True
    acl = await db.scalar(
        select(KnowledgeBaseAcl).where(
            KnowledgeBaseAcl.knowledge_base_id == kb.id,
            KnowledgeBaseAcl.user_id == user.id,
            KnowledgeBaseAcl.can_read.is_(True),
        )
    )
    return acl is not None


async def user_can_write_kb(db: AsyncSession, user: User, kb: KnowledgeBase) -> bool:
    if not await user_can_read_kb(db, user, kb):
        return False
    if is_tenant_admin(user) or kb.created_by == user.id:
        return user.role in {UserRole.super_admin, UserRole.tenant_admin, UserRole.kb_editor} or kb.created_by == user.id
    acl = await db.scalar(
        select(KnowledgeBaseAcl).where(
            KnowledgeBaseAcl.knowledge_base_id == kb.id,
            KnowledgeBaseAcl.user_id == user.id,
            KnowledgeBaseAcl.can_write.is_(True),
        )
    )
    return acl is not None and user.role in {UserRole.kb_editor, UserRole.tenant_admin, UserRole.super_admin}


async def readable_kb_ids(db: AsyncSession, user: User) -> list[UUID]:
    if is_tenant_admin(user):
        rows = (
            await db.scalars(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.tenant_id == user.tenant_id, KnowledgeBase.is_active.is_(True)
                )
            )
        ).all()
        return list(rows)
    acl_ids = (
        await db.scalars(
            select(KnowledgeBaseAcl.knowledge_base_id).where(
                KnowledgeBaseAcl.user_id == user.id, KnowledgeBaseAcl.can_read.is_(True)
            )
        )
    ).all()
    cond = KnowledgeBase.created_by == user.id
    if acl_ids:
        cond = or_(cond, KnowledgeBase.id.in_(list(acl_ids)))
    rows = (
        await db.scalars(
            select(KnowledgeBase.id).where(
                KnowledgeBase.tenant_id == user.tenant_id,
                KnowledgeBase.is_active.is_(True),
                cond,
            )
        )
    ).all()
    return list(rows)


async def require_read(db: AsyncSession, user: User, kb: KnowledgeBase) -> None:
    if not await user_can_read_kb(db, user, kb):
        raise AppError(40003, "无权限", 403)


async def require_read_many(db: AsyncSession, user: User, kbs: list[KnowledgeBase]) -> None:
    if not kbs:
        raise AppError(40022, "至少选择一个知识库", 422)
    if is_tenant_admin(user):
        return
    ids = [kb.id for kb in kbs]
    allowed = set(
        await db.scalars(
            select(KnowledgeBaseAcl.knowledge_base_id).where(
                KnowledgeBaseAcl.user_id == user.id,
                KnowledgeBaseAcl.knowledge_base_id.in_(ids),
                KnowledgeBaseAcl.can_read.is_(True),
            )
        )
    )
    for kb in kbs:
        if kb.created_by == user.id:
            continue
        if kb.id not in allowed:
            raise AppError(40003, "无权限", 403)


async def require_write(db: AsyncSession, user: User, kb: KnowledgeBase) -> None:
    if user.role == UserRole.member:
        raise AppError(40003, "无权限", 403)
    if not await user_can_write_kb(db, user, kb):
        raise AppError(40003, "无权限", 403)
