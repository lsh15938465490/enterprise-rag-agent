"""行为埋点写入与汇总查询。无前端看板。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok, page_data
from app.core.deps import get_current_user
from app.db.models import AnalyticsEvent, User
from app.db.session import get_db
from app.schemas.dto import AnalyticsEventIn
from app.services.analytics import record_event, summary_for_tenant

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/events")
async def create_event(
    request: Request,
    body: AnalyticsEventIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await record_event(
        db,
        user=user,
        event_type=body.event_type,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        extra=body.extra,
    )
    await db.commit()
    return ok(request, {"recorded": True}, 201)


@router.get("/events")
async def list_events(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(AnalyticsEvent).where(AnalyticsEvent.tenant_id == user.tenant_id)
    if event_type:
        stmt = stmt.where(AnalyticsEvent.event_type == event_type)
    count_stmt = select(func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.tenant_id == user.tenant_id)
    if event_type:
        count_stmt = count_stmt.where(AnalyticsEvent.event_type == event_type)
    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.scalars(
            stmt.order_by(AnalyticsEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    items = [
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "resource_type": r.resource_type,
            "resource_id": str(r.resource_id) if r.resource_id else None,
            "user_id": str(r.user_id) if r.user_id else None,
            "extra": r.extra,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return ok(request, page_data(items, total, page, page_size))


@router.get("/summary")
async def analytics_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(request, await summary_for_tenant(db, user.tenant_id))
