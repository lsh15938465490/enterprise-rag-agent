"""登录历史：设备名解析、落库、按用户取最近 20 条。"""

from collections import defaultdict
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LoginHistory, User

SHANGHAI = ZoneInfo("Asia/Shanghai")  # 北京时间（中国标准时）


def format_login_time(dt: datetime) -> str:
    """展示成 2026/8/25 08:05:03。"""
    local = dt.astimezone(SHANGHAI) if dt.tzinfo else dt.replace(tzinfo=SHANGHAI)
    return f"{local.year}/{local.month}/{local.day} {local:%H:%M:%S}"


def device_name_from_ua(user_agent: str | None) -> str:
    ua = user_agent or ""
    if "Windows" in ua:
        os_name = "Windows"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua:
        os_name = "iPhone"
    elif "iPad" in ua:
        os_name = "iPad"
    elif "Mac OS" in ua or "Macintosh" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "未知系统"
    if "Edg/" in ua:
        browser = "Edge"
    elif "Chrome/" in ua and "Chromium" not in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua and "Chrome" not in ua:
        browser = "Safari"
    else:
        browser = "浏览器"
    return f"{os_name} {browser}"


async def record_login(db: AsyncSession, user: User, user_agent: str | None) -> None:
    db.add(
        LoginHistory(
            tenant_id=user.tenant_id,
            user_id=user.id,
            device_name=device_name_from_ua(user_agent)[:128],
            user_agent=(user_agent or "")[:512] or None,
        )
    )


def _row_payload(row: LoginHistory) -> dict:
    return {"logged_at": format_login_time(row.logged_at), "device_name": row.device_name}


async def login_summaries(db: AsyncSession, user_ids: list[UUID]) -> dict[UUID, dict]:
    """每个用户最近 20 条登录，供列表页一次带出。"""
    empty = {"last_login_at": None, "login_count": 0, "logins": []}
    if not user_ids:
        return {}
    rows = (
        await db.scalars(
            select(LoginHistory)
            .where(LoginHistory.user_id.in_(user_ids))
            .order_by(LoginHistory.logged_at.desc())
        )
    ).all()
    grouped: dict[UUID, list[LoginHistory]] = defaultdict(list)
    counts: dict[UUID, int] = defaultdict(int)
    for row in rows:
        counts[row.user_id] += 1
        bucket = grouped[row.user_id]
        if len(bucket) < 20:
            bucket.append(row)
    out: dict[UUID, dict] = {}
    for uid in user_ids:
        items = grouped.get(uid) or []
        out[uid] = {
            "last_login_at": format_login_time(items[0].logged_at) if items else None,
            "login_count": counts.get(uid, 0),
            "logins": [_row_payload(x) for x in items],
        }
    return out
