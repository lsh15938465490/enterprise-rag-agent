"""行为埋点：登录、提问等。只落库，无前端看板。"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.limits import PLATFORM_TENANT_SLUG
from app.db.models import AnalyticsEvent, Conversation, Document, DocStatus, KnowledgeBase, Tenant, User
from app.services.acl import is_super_admin

# 北京时间（中国标准时）。IANA 主名称是 Asia/Shanghai，与北京同一时区。
BEIJING = ZoneInfo("Asia/Shanghai")
PG_BEIJING_TZ = "Asia/Shanghai"


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


async def summary_for_tenant(db: AsyncSession, tenant_id: UUID | None) -> dict[str, Any]:
    if tenant_id is None:
        return {"by_event_type": [], "total": 0}
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


def _tenant_scope(column, user: User, tenant_id: UUID | None) -> ColumnElement | None:
    if is_super_admin(user):
        if tenant_id is None:
            return None
        return column == tenant_id
    return column == user.tenant_id


def _doc_scope(user: User, tenant_id: UUID | None) -> ColumnElement | None:
    return _tenant_scope(Document.tenant_id, user, tenant_id)


def _conv_scope(user: User, tenant_id: UUID | None) -> ColumnElement | None:
    return _tenant_scope(Conversation.tenant_id, user, tenant_id)


def _beijing_today_start() -> datetime:
    return datetime.now(BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)


async def _count_created_today(db: AsyncSession, model, created_at, filt: ColumnElement | None) -> int:
    today_start_utc = _beijing_today_start().astimezone(timezone.utc)
    stmt = select(func.count()).select_from(model).where(created_at >= today_start_utc)
    if filt is not None:
        stmt = stmt.where(filt)
    return int(await db.scalar(stmt) or 0)


async def _last_7_days(db: AsyncSession, model, created_at, filt: ColumnElement | None) -> list[dict[str, Any]]:
    today_start = _beijing_today_start()
    week_start = (today_start - timedelta(days=6)).astimezone(timezone.utc)
    day_expr = func.date(func.timezone(PG_BEIJING_TZ, created_at))
    stmt = select(day_expr, func.count()).select_from(model).where(created_at >= week_start)
    if filt is not None:
        stmt = stmt.where(filt)
    rows = {str(d): int(c) for d, c in (await db.execute(stmt.group_by(day_expr))).all()}
    out = []
    for i in range(6, -1, -1):
        day = (today_start - timedelta(days=i)).date().isoformat()
        out.append({"date": day, "count": rows.get(day, 0)})
    return out


async def upload_dashboard(db: AsyncSession, user: User, tenant_id: UUID | None = None) -> dict[str, Any]:
    """现存文档/会话、今日上传与新建会话、近 7 天趋势（按北京时区自然日）。"""
    filt = _doc_scope(user, tenant_id)
    base = select(func.count()).select_from(Document)
    if filt is not None:
        base = base.where(filt)
    existing = int(await db.scalar(base) or 0)

    ready_stmt = select(func.count()).select_from(Document).where(Document.status == DocStatus.ready)
    failed_stmt = select(func.count()).select_from(Document).where(Document.status == DocStatus.failed)
    if filt is not None:
        ready_stmt = ready_stmt.where(filt)
        failed_stmt = failed_stmt.where(filt)
    ready = int(await db.scalar(ready_stmt) or 0)
    failed = int(await db.scalar(failed_stmt) or 0)
    processing = max(existing - ready - failed, 0)

    kb_stmt = select(func.count()).select_from(KnowledgeBase)
    if is_super_admin(user):
        if tenant_id is not None:
            kb_stmt = kb_stmt.where(KnowledgeBase.tenant_id == tenant_id)
    else:
        kb_stmt = kb_stmt.where(KnowledgeBase.tenant_id == user.tenant_id)
    knowledge_bases = int(await db.scalar(kb_stmt) or 0)

    today = await _count_created_today(db, Document, Document.created_at, filt)
    last_7_days = await _last_7_days(db, Document, Document.created_at, filt)

    conv_filt = _conv_scope(user, tenant_id)
    conv_base = select(func.count()).select_from(Conversation)
    if conv_filt is not None:
        conv_base = conv_base.where(conv_filt)
    conversations = int(await db.scalar(conv_base) or 0)
    conversations_today = await _count_created_today(db, Conversation, Conversation.created_at, conv_filt)
    conversations_last_7_days = await _last_7_days(db, Conversation, Conversation.created_at, conv_filt)
    conversations_week = sum(d["count"] for d in conversations_last_7_days)

    by_tenant: list[dict[str, Any]] = []
    if is_super_admin(user) and tenant_id is None:
        doc_sub = (
            select(
                Document.tenant_id,
                Document.uploaded_by,
                func.count(Document.id).label("docs"),
            ).group_by(Document.tenant_id, Document.uploaded_by)
        ).subquery()
        conv_sub = (
            select(
                Conversation.tenant_id,
                Conversation.user_id,
                func.count(Conversation.id).label("convs"),
            ).group_by(Conversation.tenant_id, Conversation.user_id)
        ).subquery()
        tenant_rows = (
            await db.execute(
                select(
                    Tenant.name,
                    Tenant.slug,
                    User.username,
                    func.coalesce(doc_sub.c.docs, 0),
                    func.coalesce(conv_sub.c.convs, 0),
                )
                .select_from(Tenant)
                .join(
                    User,
                    or_(
                        User.tenant_id == Tenant.id,
                        and_(User.tenant_id.is_(None), Tenant.slug == PLATFORM_TENANT_SLUG),
                    ),
                )
                .outerjoin(
                    doc_sub,
                    and_(doc_sub.c.tenant_id == Tenant.id, doc_sub.c.uploaded_by == User.id),
                )
                .outerjoin(
                    conv_sub,
                    and_(conv_sub.c.tenant_id == Tenant.id, conv_sub.c.user_id == User.id),
                )
                .where(Tenant.is_active.is_(True))
                .order_by(Tenant.name.asc(), User.username.asc())
            )
        ).all()
        by_tenant = [
            {
                "tenant_name": name,
                "tenant_slug": slug,
                "username": username,
                "existing": int(docs),
                "conversations": int(convs),
            }
            for name, slug, username, docs, convs in tenant_rows
        ]

    return {
        "existing": existing,
        "total": existing,
        "ready": ready,
        "failed": failed,
        "processing": processing,
        "knowledge_bases": knowledge_bases,
        "today": today,
        "last_7_days": last_7_days,
        "conversations": conversations,
        "conversations_today": conversations_today,
        "conversations_week": conversations_week,
        "conversations_last_7_days": conversations_last_7_days,
        "by_tenant": by_tenant,
    }
