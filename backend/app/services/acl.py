"""知识库权限判断：管理员、创建人、或 ACL 表里勾了可读/可写。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.db.models import KnowledgeBase, KnowledgeBaseAcl, User, UserRole


def is_tenant_admin(user: User) -> bool:
    """租户管理员和超级管理员：本租户知识库默认都能看。"""
    return user.role in {UserRole.super_admin, UserRole.tenant_admin}


async def get_kb(db: AsyncSession, kb_id: UUID, tenant_id: UUID) -> KnowledgeBase:
    """按 id 取知识库，必须属于当前租户，防止跨租户猜 UUID。"""
    kb = await db.scalar(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == tenant_id)
    )
    if kb is None:
        raise AppError(40004, "资源不存在", 404)
    return kb


async def user_can_read_kb(db: AsyncSession, user: User, kb: KnowledgeBase) -> bool:
    """本租户启用中的知识库，管理者和普通用户都能看、都能用来问答。"""
    if kb.tenant_id != user.tenant_id:
        return False
    if not kb.is_active and not is_tenant_admin(user):
        return False
    return True


async def user_can_write_kb(db: AsyncSession, user: User, kb: KnowledgeBase) -> bool:
    """能不能上传/改 ACL。普通成员即使能读也不能写。"""
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
    """知识库列表页：本租户启用中的库，普通用户和管理员都能看见。"""
    rows = (
        await db.scalars(
            select(KnowledgeBase.id).where(
                KnowledgeBase.tenant_id == user.tenant_id, KnowledgeBase.is_active.is_(True)
            )
        )
    ).all()
    return list(rows)


async def require_read(db: AsyncSession, user: User, kb: KnowledgeBase) -> None:
    """接口里没权限就 403。"""
    if not await user_can_read_kb(db, user, kb):
        raise AppError(40003, "无权限", 403)


async def require_read_many(db: AsyncSession, user: User, kbs: list[KnowledgeBase]) -> None:
    """新建会话时一次检查多个库。"""
    if not kbs:
        raise AppError(40022, "至少选择一个知识库", 422)
    for kb in kbs:
        await require_read(db, user, kb)


async def require_write(db: AsyncSession, user: User, kb: KnowledgeBase) -> None:
    """写操作：仅管理者（及知识库编辑）。普通用户只能看和问答。"""
    if user.role == UserRole.member:
        raise AppError(40003, "无权限，仅管理者可修改知识库", 403)
    if not await user_can_write_kb(db, user, kb):
        raise AppError(40003, "无权限", 403)
