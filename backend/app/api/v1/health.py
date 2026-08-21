"""探活：分别 ping 数据库、Redis、Qdrant，给运维看哪台挂了。"""

import logging

import httpx
from fastapi import APIRouter, Request
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.core.exceptions import envelope, get_request_id
from app.db.session import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _check_postgres() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.debug("健康检查 postgres 失败", exc_info=True)
        return False


async def _check_redis() -> bool:
    client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    try:
        return bool(await client.ping())
    except Exception:
        logger.debug("健康检查 redis 失败", exc_info=True)
        return False
    finally:
        await client.aclose()


async def _check_qdrant() -> bool:
    url = settings.QDRANT_URL.rstrip("/") + "/readyz"
    headers = {}
    if settings.QDRANT_API_KEY:
        headers["api-key"] = settings.QDRANT_API_KEY
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url, headers=headers)
            return resp.status_code < 500
    except Exception:
        logger.debug("健康检查 qdrant 失败", exc_info=True)
        return False


@router.get("/health")
async def health(request: Request) -> dict:
    postgres = await _check_postgres()
    redis_ok = await _check_redis()
    qdrant = await _check_qdrant()
    ok = postgres and redis_ok and qdrant
    data = {
        "status": "ok" if ok else "degraded",
        "postgres": postgres,
        "qdrant": qdrant,
        "redis": redis_ok,
    }
    return envelope(data=data, request_id=get_request_id(request))
