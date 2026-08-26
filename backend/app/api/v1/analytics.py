"""行为埋点写入与汇总查询。无前端看板。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok, page_data
from app.core.deps import get_current_user, require_roles
from app.core.exceptions import AppError
from app.db.models import AnalyticsEvent, User, UserRole
from app.db.session import get_db
from app.schemas.dto import AnalyticsEventIn
from app.services.acl import is_super_admin
from app.services.analytics import record_event, summary_for_tenant, upload_dashboard

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


@router.get("/uploads")
async def upload_stats(
    request: Request,
    tenant_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.tenant_admin)),
):
    """上传统计页：文档与新建会话存量、今日、近 7 天。超级管理员可按 tenant_id 筛选。"""
    scope = None
    if tenant_id:
        if not is_super_admin(user):
            raise AppError(40003, "无权限", 403)
        try:
            scope = UUID(tenant_id)
        except ValueError:
            raise AppError(40022, "租户无效", 422)
    return ok(request, await upload_dashboard(db, user, scope))


@router.get("/summary")
async def analytics_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(request, await summary_for_tenant(db, user.tenant_id))
