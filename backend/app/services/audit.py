"""权限等关键操作写入 audit_logs。"""

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, User


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


async def write_audit(
    db: AsyncSession,
    *,
    actor: User,
    action: str,
    resource_type: str,
    resource_id: UUID | None = None,
    extra: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=actor.tenant_id,
            user_id=actor.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=_client_ip(request),
            extra=extra,
        )
    )
