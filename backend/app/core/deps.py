"""
登录校验：从请求头 Authorization: Bearer <token> 认出当前用户。

接口写 Depends(get_current_user) 就表示「必须先登录」。
"""

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.redis import is_jti_blacklisted
from app.core.security import decode_token
from app.db.models import User, UserRole
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """校验 access token，返回当前登录用户；失败抛 401。"""
    if credentials is None or not credentials.credentials:
        raise AppError(40001, "未登录", 401)
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise AppError(40001, "认证失败", 401) from None
    if payload.get("type") != "access":
        raise AppError(40001, "认证失败", 401)
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError):
        raise AppError(40001, "认证失败", 401) from None
    raw_tid = str(payload.get("tenant_id") or "")
    stmt = select(User).where(User.id == user_id)
    if raw_tid:
        try:
            stmt = stmt.where(User.tenant_id == uuid.UUID(raw_tid))
        except ValueError:
            raise AppError(40001, "认证失败", 401) from None
    else:
        stmt = stmt.where(User.tenant_id.is_(None))
    user = await db.scalar(stmt)
    if user is None or not user.is_active:
        raise AppError(40001, "认证失败", 401)
    return user


def require_roles(*roles: UserRole):
    """限制角色。例如只有租户管理员能管用户。超级管理员始终放行。"""
    async def _inner(user: User = Depends(get_current_user)) -> User:
        if user.role != UserRole.super_admin and user.role not in roles:
            raise AppError(40003, "无权限", 403)
        return user

    return _inner
