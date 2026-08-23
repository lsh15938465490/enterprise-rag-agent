"""租户内用户管理：列表、创建、改角色/禁用。仅管理员。"""

import re

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok, page_data
from app.core.deps import require_roles
from app.core.exceptions import AppError
from app.core.limits import SUPER_ADMIN_USERNAME
from app.core.security import hash_password
from app.db.models import AuditLog, User, UserRole
from app.db.session import get_db
from app.schemas.dto import UserCreateIn, UserDTO, UserPatchIn
from app.services.audit import write_audit

router = APIRouter(prefix="/users", tags=["users"])

PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def _is_protected_super_admin(user: User) -> bool:
    """最高管理者账号不能降级、不能禁用。"""
    return user.username == SUPER_ADMIN_USERNAME or user.role == UserRole.super_admin


def _check_password(password: str) -> None:
    """创建/改密时再拦一层：至少 8 位，且字母、数字都要有。"""
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
    """分页列出本租户用户，可用用户名或邮箱模糊搜索。"""
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
    """新建账号。不能越权创建超级管理员；用户名/邮箱在本租户内不能重复。"""
    _check_password(body.password)
    if body.role == "super_admin" and admin.role != UserRole.super_admin:
        raise AppError(40003, "无权限", 403)
    if body.username == SUPER_ADMIN_USERNAME:
        raise AppError(40003, "不能创建最高管理者账号", 403)
    exists = await db.scalar(
        select(User).where(User.tenant_id == admin.tenant_id, User.username == body.username)
    )
    if exists:
        raise AppError(40901, "用户名已存在", 409)
    exists = await db.scalar(
        select(User).where(User.tenant_id == admin.tenant_id, User.email == str(body.email))
    )
    if exists:
        raise AppError(40901, "邮箱已存在", 409)
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
    """改密码、启用/禁用、改角色。只能改本租户的人。角色/启用变更写入操作日志。"""
    user = await db.scalar(select(User).where(User.id == user_id, User.tenant_id == admin.tenant_id))
    if user is None:
        raise AppError(40004, "资源不存在", 404)
    if _is_protected_super_admin(user):
        if body.is_active is False:
            raise AppError(40003, "最高管理者不能禁用", 403)
        if body.role is not None and body.role != "super_admin":
            raise AppError(40003, "最高管理者不能变为普通用户", 403)
    old_role = user.role.value
    old_active = user.is_active
    if body.password:
        _check_password(body.password)
        user.password_hash = hash_password(body.password)
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.role is not None:
        if body.role == "super_admin" and admin.role != UserRole.super_admin:
            raise AppError(40003, "无权限", 403)
        user.role = UserRole(body.role)
    if body.role is not None and user.role.value != old_role:
        await write_audit(
            db,
            actor=admin,
            action="user.role_change",
            resource_type="user",
            resource_id=user.id,
            extra={"from": old_role, "to": user.role.value, "target_username": user.username},
            request=request,
        )
    if body.is_active is not None and user.is_active != old_active:
        await write_audit(
            db,
            actor=admin,
            action="user.active_change",
            resource_type="user",
            resource_id=user.id,
            extra={"from": old_active, "to": user.is_active, "target_username": user.username},
            request=request,
        )
    await db.commit()
    await db.refresh(user)
    return ok(request, UserDTO.model_validate(user).model_dump(mode="json"))


@router.get("/audit-logs")
async def list_user_audit_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.tenant_admin)),
):
    """权限变更操作日志（无前端页面）。"""
    stmt = select(AuditLog).where(
        AuditLog.tenant_id == admin.tenant_id,
        AuditLog.resource_type == "user",
    )
    count_stmt = select(func.count()).select_from(AuditLog).where(
        AuditLog.tenant_id == admin.tenant_id,
        AuditLog.resource_type == "user",
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.scalars(
            stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    items = [
        {
            "id": str(r.id),
            "action": r.action,
            "resource_id": str(r.resource_id) if r.resource_id else None,
            "actor_user_id": str(r.user_id) if r.user_id else None,
            "ip": str(r.ip) if r.ip else None,
            "extra": r.extra,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return ok(request, page_data(items, total, page, page_size))
