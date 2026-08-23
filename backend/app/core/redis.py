"""
连 Redis。主要用来把已登出的 refresh 令牌拉黑。

Redis 挂了也不致命：退回成进程内存集合（多进程/重启后会丢）。
"""

import logging
import time

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)
_memory_blacklist: set[str] = set()
_memory_kv: dict[str, tuple[str, float]] = {}
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


def _purge_memory_kv(now: float) -> None:
    expired = [k for k, (_, exp) in _memory_kv.items() if exp <= now]
    for k in expired:
        _memory_kv.pop(k, None)


async def kv_get(key: str) -> str | None:
    """带 TTL 的键值读取；Redis 不可用时用进程内存。"""
    now = time.time()
    _purge_memory_kv(now)
    mem = _memory_kv.get(key)
    if mem is not None and mem[1] > now:
        return mem[0]
    client = await get_redis()
    if client is None:
        return None
    val = await client.get(key)
    return str(val) if val is not None else None


async def kv_setex(key: str, ttl_seconds: int, value: str) -> None:
    ttl_seconds = max(1, int(ttl_seconds))
    client = await get_redis()
    if client is not None:
        await client.setex(key, ttl_seconds, value)
        return
    _memory_kv[key] = (value, time.time() + ttl_seconds)


async def kv_incr(key: str, ttl_seconds: int) -> int:
    """计数 +1；键不存在时同时设置过期。"""
    ttl_seconds = max(1, int(ttl_seconds))
    client = await get_redis()
    if client is not None:
        n = int(await client.incr(key))
        if n == 1:
            await client.expire(key, ttl_seconds)
        return n
    now = time.time()
    _purge_memory_kv(now)
    prev = _memory_kv.get(key)
    if prev is None or prev[1] <= now:
        _memory_kv[key] = ("1", now + ttl_seconds)
        return 1
    n = int(prev[0]) + 1
    _memory_kv[key] = (str(n), prev[1])
    return n


async def kv_delete(*keys: str) -> None:
    for key in keys:
        _memory_kv.pop(key, None)
    client = await get_redis()
    if client is not None and keys:
        await client.delete(*keys)
