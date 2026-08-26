"""登录 / 刷新令牌 / 登出 / 当前用户信息。"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.core.limits import PLATFORM_TENANT_SLUG, SUPER_ADMIN_USERNAME
from app.core.redis import blacklist_jti, is_jti_blacklisted
from app.core.security import create_token, decode_token, verify_password
from app.db.models import Tenant, User
from app.db.session import get_db
from app.schemas.dto import LoginIn, RefreshIn, TokenOut, UserDTO
from app.services.acl import is_super_admin
from app.services.analytics import record_event
from app.services.login_history import record_login
from app.services.login_lock import LOGIN_FAIL_MSG, clear_failures, is_locked, record_failure
import jwt

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


async def _user_payload(db: AsyncSession, user: User) -> dict:
    data = UserDTO.model_validate(user).model_dump(mode="json")
    if user.tenant_id is None:
        data["tenant_slug"] = None
        data["tenant_name"] = None
        return data
    tenant = await db.scalar(select(Tenant).where(Tenant.id == user.tenant_id))
    data["tenant_slug"] = tenant.slug if tenant else None
    data["tenant_name"] = tenant.name if tenant else None
    return data


def _token_payload(user: User, profile: dict) -> dict:
    """登录成功后同时签发短令牌（access）和长令牌（refresh），并带上用户资料。"""
    access, _ = create_token(user.id, user.tenant_id, "access")
    refresh, _ = create_token(user.id, user.tenant_id, "refresh")
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserDTO.model_validate(profile),
    ).model_dump(mode="json")


def _tenant_items(rows: list[Tenant]) -> list[dict]:
    return [{"id": str(t.id), "slug": t.slug, "name": t.name} for t in rows]


@router.get("/tenants")
async def list_tenants(request: Request, db: AsyncSession = Depends(get_db)):
    """登录页用：列出可选部门。"""
    rows = (
        await db.scalars(
            select(Tenant)
            .where(Tenant.is_active.is_(True), Tenant.slug != PLATFORM_TENANT_SLUG)
            .order_by(Tenant.name.asc())
        )
    ).all()
    return ok(request, _tenant_items(rows))


@router.get("/workspace-tenants")
async def list_workspace_tenants(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """登录后选所属租户：超级管理员可见「超级管理员」+ 各部门。"""
    stmt = select(Tenant).where(Tenant.is_active.is_(True))
    if not is_super_admin(user):
        stmt = stmt.where(Tenant.slug != PLATFORM_TENANT_SLUG)
        if user.tenant_id is not None:
            stmt = stmt.where(Tenant.id == user.tenant_id)
    rows = (
        await db.scalars(
            stmt.order_by(case((Tenant.slug == PLATFORM_TENANT_SLUG, 0), else_=1), Tenant.name.asc())
        )
    ).all()
    return ok(request, _tenant_items(rows))


@router.post("/login")
async def login(request: Request, body: LoginIn, db: AsyncSession = Depends(get_db)):
    """校验部门 + 用户名 + 密码。adminliu 不校验所选部门。"""
    username = body.username.strip()
    platform_login = username.lower() == SUPER_ADMIN_USERNAME.lower() or body.tenant_slug == PLATFORM_TENANT_SLUG
    lock_slug = PLATFORM_TENANT_SLUG if platform_login else body.tenant_slug
    if await is_locked(lock_slug, username):
        raise AppError(40001, LOGIN_FAIL_MSG, 401)
    if platform_login:
        user = await db.scalar(
            select(User).where(
                func.lower(User.username) == username.lower(),
                User.tenant_id.is_(None),
                User.is_active.is_(True),
            )
        )
        if user is None or not verify_password(body.password, user.password_hash):
            await record_failure(lock_slug, username)
            raise AppError(40001, LOGIN_FAIL_MSG, 401)
    else:
        tenant = await db.scalar(select(Tenant).where(Tenant.slug == body.tenant_slug, Tenant.is_active.is_(True)))
        if tenant is None:
            raise AppError(40001, LOGIN_FAIL_MSG, 401)
        user = await db.scalar(select(User).where(User.tenant_id == tenant.id, User.username == username))
        if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
            await record_failure(body.tenant_slug, username)
            raise AppError(40001, LOGIN_FAIL_MSG, 401)
    await clear_failures(lock_slug, username)
    await record_login(db, user, request.headers.get("user-agent"))
    await record_event(db, user=user, event_type="login", resource_type="user", resource_id=user.id)
    profile = await _user_payload(db, user)
    await db.commit()
    return ok(request, _token_payload(user, profile))


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
    profile = await _user_payload(db, user)
    return ok(request, _token_payload(user, profile))


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
async def me(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """返回当前登录人信息，给前端顶栏显示用户名、判断是否管理员。"""
    return ok(request, await _user_payload(db, user))
