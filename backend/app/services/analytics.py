"""行为埋点：登录、提问等。只落库，无前端看板。"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent, User


async def record_event(
    db: AsyncSession,
    *,
    user: User | None,
    event_type: str,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    extra: dict[str, Any] | None = None,
    tenant_id: UUID | None = None,
) -> None:
    db.add(
        AnalyticsEvent(
            tenant_id=user.tenant_id if user else tenant_id,
            user_id=user.id if user else None,
            event_type=event_type[:64],
            resource_type=resource_type,
            resource_id=resource_id,
            extra=extra,
        )
    )


async def summary_for_tenant(db: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(AnalyticsEvent.event_type, func.count())
            .where(AnalyticsEvent.tenant_id == tenant_id)
            .group_by(AnalyticsEvent.event_type)
            .order_by(func.count().desc())
        )
    ).all()
    return {
        "by_event_type": [{"event_type": t, "count": int(c)} for t, c in rows],
        "total": sum(int(c) for _, c in rows),
    }
