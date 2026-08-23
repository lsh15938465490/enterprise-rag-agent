"""开发环境自动创建租户 demo、最高管理者 adminliu、普通用户 user。生产环境不会执行。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.limits import SUPER_ADMIN_USERNAME
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
    """没有这个用户名就创建，已有则不改密码。"""
    exists = await session.scalar(select(User).where(User.tenant_id == tenant_id, User.username == username))
    if exists is not None:
        if username == SUPER_ADMIN_USERNAME:
            exists.role = UserRole.super_admin
            exists.is_active = True
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


async def seed_dev_data(session: AsyncSession) -> None:
    """保证 demo 租户、最高管理者 adminliu、普通用户 user 存在。"""
    if settings.APP_ENV == "prod":
        return

    tenant = await session.scalar(select(Tenant).where(Tenant.slug == "demo"))
    if tenant is None:
        tenant = Tenant(name="Demo Corp", slug="demo", is_active=True)
        session.add(tenant)
        await session.flush()

    old_admin = await session.scalar(select(User).where(User.tenant_id == tenant.id, User.username == "admin"))
    new_admin = await session.scalar(
        select(User).where(User.tenant_id == tenant.id, User.username == SUPER_ADMIN_USERNAME)
    )
    if old_admin is not None and new_admin is None:
        old_admin.username = SUPER_ADMIN_USERNAME
        old_admin.email = "adminliu@demo.local"
        old_admin.role = UserRole.super_admin
        old_admin.is_active = True
    else:
        await _ensure_user(
            session, tenant.id, SUPER_ADMIN_USERNAME, "adminliu@demo.local", UserRole.super_admin
        )

    await _ensure_user(session, tenant.id, "user", "user@demo.local", UserRole.member)
    await session.commit()
