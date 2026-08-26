"""知识库权限判断：管理员、创建人、或 ACL 表里勾了可读/可写。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.limits import SUPER_ADMIN_USERNAME
from app.db.models import KnowledgeBase, KnowledgeBaseAcl, User, UserRole


def is_super_admin(user: User) -> bool:
    return user.role == UserRole.super_admin or user.username == SUPER_ADMIN_USERNAME


def is_tenant_admin(user: User) -> bool:
    """租户管理员和超级管理员：本租户知识库默认都能看。"""
    return user.role in {UserRole.super_admin, UserRole.tenant_admin}


async def get_kb(db: AsyncSession, kb_id: UUID, user: User) -> KnowledgeBase:
    """按 id 取知识库。普通账号必须属于当前租户；超级管理员可跨租户查看。"""
    stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
    if not is_super_admin(user):
        stmt = stmt.where(KnowledgeBase.tenant_id == user.tenant_id)
    kb = await db.scalar(stmt)
    if kb is None:
        raise AppError(40004, "资源不存在", 404)
    return kb


async def _acl_flag(db: AsyncSession, user: User, kb: KnowledgeBase, *, write: bool) -> bool:
    stmt = select(KnowledgeBaseAcl).where(
        KnowledgeBaseAcl.knowledge_base_id == kb.id,
        KnowledgeBaseAcl.user_id == user.id,
    )
    if write:
        stmt = stmt.where(KnowledgeBaseAcl.can_write.is_(True))
    else:
        stmt = stmt.where(KnowledgeBaseAcl.can_read.is_(True))
    return await db.scalar(stmt) is not None


async def user_can_read_kb(db: AsyncSession, user: User, kb: KnowledgeBase) -> bool:
    """超管可读全部；其他人（管理者、普通用户）一律以 ACL 可读为准，取消授权立即失效。"""
    if is_super_admin(user):
        return True
    if kb.tenant_id != user.tenant_id:
        return False
    if not kb.is_active and not is_tenant_admin(user):
        return False
    return await _acl_flag(db, user, kb, write=False)


async def user_can_write_kb(db: AsyncSession, user: User, kb: KnowledgeBase) -> bool:
    """能不能上传/改 ACL。停用库对普通用户不可写（ACL 不能覆盖停用）。"""
    if is_super_admin(user):
        return True
    if kb.tenant_id != user.tenant_id:
        return False
    if not kb.is_active and not is_tenant_admin(user):
        return False
    if not await user_can_read_kb(db, user, kb):
        return False
    if is_tenant_admin(user):
        return True
    return False


async def readable_kb_ids(db: AsyncSession, user: User, *, active_only: bool = False) -> list[UUID]:
    """知识库列表：超管看全部；部门管理员看本部门；普通用户只看 ACL 可读或自己创建的库。"""
    stmt = select(KnowledgeBase)
    if is_super_admin(user):
        pass
    else:
        stmt = stmt.where(KnowledgeBase.tenant_id == user.tenant_id)
        if not is_tenant_admin(user):
            stmt = stmt.where(KnowledgeBase.is_active.is_(True))
    if active_only:
        stmt = stmt.where(KnowledgeBase.is_active.is_(True))
    rows = (await db.scalars(stmt.order_by(KnowledgeBase.created_at.desc()))).all()
    if is_super_admin(user):
        return [kb.id for kb in rows]
    return [kb.id for kb in rows if await user_can_read_kb(db, user, kb)]


async def filter_readable_kb_ids(db: AsyncSession, user: User, kb_ids: list[UUID]) -> list[UUID]:
    """会话里绑定的库再按当前用户 ACL 过滤，避免取消授权后仍能检索。"""
    if not kb_ids:
        return []
    out: list[UUID] = []
    for kid in kb_ids:
        kb = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.id == kid))
        if kb is None:
            continue
        if await user_can_read_kb(db, user, kb):
            out.append(kid)
    return out


async def filter_active_kb_ids(db: AsyncSession, kb_ids: list[UUID]) -> list[UUID]:
    """问答只用启用中的知识库，停用库里的文档不再检索。"""
    if not kb_ids:
        return []
    active = set(
        (
            await db.scalars(
                select(KnowledgeBase.id).where(KnowledgeBase.id.in_(kb_ids), KnowledgeBase.is_active.is_(True))
            )
        ).all()
    )
    return [kid for kid in kb_ids if kid in active]


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
