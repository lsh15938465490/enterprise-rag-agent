"""开发环境自动创建租户 demo / 用户 admin。生产环境（APP_ENV=prod）不会执行。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import Tenant, User, UserRole

DEV_ADMIN_PASSWORD = "Admin@123456"


async def seed_dev_data(session: AsyncSession) -> None:
    if settings.APP_ENV == "prod":
        return

    existing = await session.scalar(select(Tenant).where(Tenant.slug == "demo"))
    if existing is not None:
        return

    tenant = Tenant(name="Demo Corp", slug="demo", is_active=True)
    session.add(tenant)
    await session.flush()

    admin = User(
        tenant_id=tenant.id,
        username="admin",
        email="admin@demo.local",
        password_hash=hash_password(DEV_ADMIN_PASSWORD),
        role=UserRole.tenant_admin,
        is_active=True,
    )
    session.add(admin)
    await session.commit()
