"""登录 / 刷新令牌 / 登出 / 当前用户信息。"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.core.redis import blacklist_jti, is_jti_blacklisted
from app.core.security import create_token, decode_token, verify_password
from app.db.models import Tenant, User
from app.db.session import get_db
from app.schemas.dto import LoginIn, RefreshIn, TokenOut, UserDTO
from app.services.analytics import record_event
from app.services.login_lock import LOGIN_FAIL_MSG, clear_failures, is_locked, record_failure
import jwt

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _token_payload(user: User) -> dict:
    """登录成功后同时签发短令牌（access）和长令牌（refresh），并带上用户资料。"""
    access, _ = create_token(user.id, user.tenant_id, "access")
    refresh, _ = create_token(user.id, user.tenant_id, "refresh")
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserDTO.model_validate(user),
    ).model_dump(mode="json")


@router.post("/login")
async def login(request: Request, body: LoginIn, db: AsyncSession = Depends(get_db)):
    """校验租户 + 用户名 + 密码。失败与锁定均返回同一句话，避免被人试出「用户是否存在」。"""
    tenant = await db.scalar(select(Tenant).where(Tenant.slug == body.tenant_slug, Tenant.is_active.is_(True)))
    if tenant is None:
        raise AppError(40001, LOGIN_FAIL_MSG, 401)
    if await is_locked(body.tenant_slug, body.username):
        raise AppError(40001, LOGIN_FAIL_MSG, 401)
    user = await db.scalar(select(User).where(User.tenant_id == tenant.id, User.username == body.username))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        await record_failure(body.tenant_slug, body.username)
        raise AppError(40001, LOGIN_FAIL_MSG, 401)
    await clear_failures(body.tenant_slug, body.username)
    await record_event(db, user=user, event_type="login", resource_type="user", resource_id=user.id)
    await db.commit()
    return ok(request, _token_payload(user))


@router.post("/refresh")
async def refresh(request: Request, body: RefreshIn, db: AsyncSession = Depends(get_db)):
    """用 refresh 换一对新令牌。已登出（黑名单）或伪造的 token 一律当认证失败。"""
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise AppError(40001, "认证失败", 401) from None
    if payload.get("type") != "refresh":
        raise AppError(40001, "认证失败", 401)
    jti = str(payload.get("jti") or "")
    if not jti or await is_jti_blacklisted(jti):
        raise AppError(40001, "认证失败", 401)
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError):
        raise AppError(40001, "认证失败", 401) from None
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise AppError(40001, "认证失败", 401)
    return ok(request, _token_payload(user))


@router.post("/logout")
async def logout(request: Request, body: RefreshIn):
    """把 refresh 的 jti 拉黑。token 本身无效也返回成功，避免重复点退出时报错。"""
    try:
        payload = decode_token(body.refresh_token)
        jti = str(payload.get("jti") or "")
        if jti:
            await blacklist_jti(jti, settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    except jwt.PyJWTError:
        logger.info("logout 收到无效 refresh_token，按已登出处理")
    return ok(request, {"logged_out": True})


@router.get("/me")
async def me(request: Request, user: User = Depends(get_current_user)):
    """返回当前登录人信息，给前端顶栏显示用户名、判断是否管理员。"""
    return ok(request, UserDTO.model_validate(user).model_dump(mode="json"))
