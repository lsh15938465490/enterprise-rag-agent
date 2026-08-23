"""登录失败次数与账号锁定（Redis，不可用时进程内存）。锁定时仍返回统一登录失败文案。"""

from app.core.config import settings
from app.core.redis import kv_delete, kv_get, kv_incr, kv_setex

LOGIN_FAIL_MSG = "用户名或密码错误"


def _fail_key(tenant_slug: str, username: str) -> str:
    return f"login:fail:{tenant_slug}:{username.lower()}"


def _lock_key(tenant_slug: str, username: str) -> str:
    return f"login:lock:{tenant_slug}:{username.lower()}"


def _window_seconds() -> int:
    return max(60, settings.LOGIN_LOCK_MINUTES * 60)


async def is_locked(tenant_slug: str, username: str) -> bool:
    return await kv_get(_lock_key(tenant_slug, username)) is not None


async def record_failure(tenant_slug: str, username: str) -> None:
    n = await kv_incr(_fail_key(tenant_slug, username), _window_seconds())
    if n >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
        await kv_setex(_lock_key(tenant_slug, username), _window_seconds(), "1")
        await kv_delete(_fail_key(tenant_slug, username))


async def clear_failures(tenant_slug: str, username: str) -> None:
    await kv_delete(_fail_key(tenant_slug, username), _lock_key(tenant_slug, username))
