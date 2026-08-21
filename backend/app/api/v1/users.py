"""租户内用户管理：列表、创建、改角色/禁用。仅管理员。"""

import re

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok, page_data
from app.core.deps import require_roles
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.db.models import User, UserRole
from app.db.session import get_db
from app.schemas.dto import UserCreateIn, UserDTO, UserPatchIn

router = APIRouter(prefix="/users", tags=["users"])

PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def _check_password(password: str) -> None:
    if not PASSWORD_RE.match(password):
        raise AppError(40022, "密码至少 8 位且包含字母和数字", 422)


@router.get("")
async def list_users(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.tenant_admin)),
):
    stmt = select(User).where(User.tenant_id == admin.tenant_id)
    count_stmt = select(func.count()).select_from(User).where(User.tenant_id == admin.tenant_id)
    if keyword:
        like = f"%{keyword}%"
        filt = or_(User.username.ilike(like), User.email.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)
    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.scalars(stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    ).all()
    items = [UserDTO.model_validate(u).model_dump(mode="json") for u in rows]
    return ok(request, page_data(items, total, page, page_size))


@router.post("")
async def create_user(
    request: Request,
    body: UserCreateIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.tenant_admin)),
):
    _check_password(body.password)
    if body.role == "super_admin" and admin.role != UserRole.super_admin:
        raise AppError(40003, "无权限", 403)
    exists = await db.scalar(
        select(User).where(
            User.tenant_id == admin.tenant_id,
            or_(User.username == body.username, User.email == str(body.email)),
        )
    )
    if exists:
        raise AppError(40901, "用户名或邮箱已存在", 409)
    user = User(
        tenant_id=admin.tenant_id,
        username=body.username,
        email=str(body.email),
        password_hash=hash_password(body.password),
        role=UserRole(body.role),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ok(request, UserDTO.model_validate(user).model_dump(mode="json"), 201)


@router.patch("/{user_id}")
async def patch_user(
    request: Request,
    user_id: str,
    body: UserPatchIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.tenant_admin)),
):
    user = await db.scalar(select(User).where(User.id == user_id, User.tenant_id == admin.tenant_id))
    if user is None:
        raise AppError(40004, "资源不存在", 404)
    if body.password:
        _check_password(body.password)
        user.password_hash = hash_password(body.password)
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.role is not None:
        if body.role == "super_admin" and admin.role != UserRole.super_admin:
            raise AppError(40003, "无权限", 403)
        user.role = UserRole(body.role)
    await db.commit()
    await db.refresh(user)
    return ok(request, UserDTO.model_validate(user).model_dump(mode="json"))
