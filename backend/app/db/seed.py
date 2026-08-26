"""开发环境：无部门超级管理员 adminliu；部门01 admin01/user01；部门02 admin02/user02。生产环境不执行。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.limits import PLATFORM_TENANT_SLUG, SUPER_ADMIN_USERNAME
from app.core.security import hash_password
from app.db.models import Tenant, User, UserRole

DEV_ADMIN_PASSWORD = "Admin@123456"


async def _ensure_user(
    session: AsyncSession,
    tenant_id,
    username: str,
    email: str,
    role: UserRole,
) -> None:
    """没有这个用户名就创建，已有则纠正角色；不改密码。"""
    if tenant_id is None:
        exists = await session.scalar(select(User).where(User.username == username, User.tenant_id.is_(None)))
    else:
        exists = await session.scalar(select(User).where(User.tenant_id == tenant_id, User.username == username))
    if exists is not None:
        exists.role = role
        exists.is_active = True
        exists.email = email
        if username == SUPER_ADMIN_USERNAME:
            exists.tenant_id = None
        return
    session.add(
        User(
            tenant_id=tenant_id,
            username=username,
            email=email,
            password_hash=hash_password(DEV_ADMIN_PASSWORD),
            role=role,
            is_active=True,
        )
    )


async def _rename_dept_admin(
    session: AsyncSession,
    tenant_id,
    old_username: str,
    new_username: str,
    email: str,
) -> None:
    """把旧的部门 admin 迁成 admin01/admin02。"""
    target = await session.scalar(select(User).where(User.tenant_id == tenant_id, User.username == new_username))
    source = await session.scalar(select(User).where(User.tenant_id == tenant_id, User.username == old_username))
    if source is not None and target is None:
        source.username = new_username
        source.email = email
        source.role = UserRole.tenant_admin
        source.is_active = True
        return
    if target is not None:
        target.role = UserRole.tenant_admin
        target.is_active = True
        target.email = email
        return
    await _ensure_user(session, tenant_id, new_username, email, UserRole.tenant_admin)


async def seed_dev_data(session: AsyncSession) -> None:
    """保证超级管理员不属于部门，各部门有各自的管理员与普通用户。"""
    if settings.APP_ENV == "prod":
        return

    platform = await session.scalar(select(Tenant).where(Tenant.slug == PLATFORM_TENANT_SLUG))
    if platform is None:
        platform = Tenant(name="超级管理员", slug=PLATFORM_TENANT_SLUG, is_active=True)
        session.add(platform)
        await session.flush()
    else:
        platform.name = "超级管理员"

    tenant = await session.scalar(select(Tenant).where(Tenant.slug == "demo"))
    if tenant is None:
        tenant = Tenant(name="部门01", slug="demo", is_active=True)
        session.add(tenant)
        await session.flush()
    else:
        tenant.name = "部门01"

    other = await session.scalar(select(Tenant).where(Tenant.slug == "acme"))
    if other is None:
        other = Tenant(name="部门02", slug="acme", is_active=True)
        session.add(other)
        await session.flush()
    else:
        other.name = "部门02"

    liu = await session.scalar(select(User).where(User.username == SUPER_ADMIN_USERNAME))
    if liu is not None:
        liu.tenant_id = None
        liu.role = UserRole.super_admin
        liu.is_active = True
        liu.email = "adminliu@platform.local"
    else:
        await _ensure_user(session, None, SUPER_ADMIN_USERNAME, "adminliu@platform.local", UserRole.super_admin)

    await _rename_dept_admin(session, tenant.id, "admin", "admin01", "admin01@demo.local")
    await _ensure_user(session, tenant.id, "user01", "user01@demo.local", UserRole.member)

    await _rename_dept_admin(session, other.id, "admin", "admin02", "admin02@acme.local")
    await _ensure_user(session, other.id, "user02", "user02@acme.local", UserRole.member)
    await session.commit()
