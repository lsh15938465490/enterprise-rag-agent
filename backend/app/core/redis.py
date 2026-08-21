"""
连 Redis。主要用来把已登出的 refresh 令牌拉黑。

Redis 挂了也不致命：退回成进程内存集合（多进程/重启后会丢）。
"""

import logging

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)
_memory_blacklist: set[str] = set()
_client: Redis | None = None


async def get_redis() -> Redis | None:
    """拿到 Redis 客户端；连不上返回 None，调用方改用内存兜底。"""
    global _client
    if _client is None:
        _client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, decode_responses=True)
    try:
        await _client.ping()
        return _client
    except Exception:
        logger.warning("Redis 不可用，刷新令牌黑名单将使用进程内集合")
        return None


async def blacklist_jti(jti: str, ttl_seconds: int) -> None:
    """登出：把这条 refresh 的身份证记下，过期时间和 refresh 有效期一致。"""
    client = await get_redis()
    key = f"bl:refresh:{jti}"
    if client is not None:
        await client.setex(key, ttl_seconds, "1")
        return
    _memory_blacklist.add(jti)


async def is_jti_blacklisted(jti: str) -> bool:
    """刷新令牌前先问：这张票是不是已经退出登录了。"""
    if jti in _memory_blacklist:
        return True
    client = await get_redis()
    if client is None:
        return False
    return bool(await client.exists(f"bl:refresh:{jti}"))
