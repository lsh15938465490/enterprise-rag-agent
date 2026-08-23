"""系统配置只读查询：容量阈值、当前大模型（不含密钥）。无前端配置页。"""

from fastapi import APIRouter, Depends, Request

from app.api.v1.helpers import ok
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.limits import max_conversations_per_user, max_documents_per_kb, max_knowledge_bases_per_tenant
from app.db.models import User

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/limits")
async def get_limits(request: Request, _user: User = Depends(get_current_user)):
    return ok(
        request,
        {
            "max_conversations_per_user": max_conversations_per_user(),
            "max_knowledge_bases_per_tenant": max_knowledge_bases_per_tenant(),
            "max_documents_per_kb": max_documents_per_kb(),
            "max_upload_mb": settings.MAX_UPLOAD_MB,
            "login_max_failed_attempts": settings.LOGIN_MAX_FAILED_ATTEMPTS,
            "login_lock_minutes": settings.LOGIN_LOCK_MINUTES,
        },
    )


@router.get("/llm")
async def get_llm(request: Request, _user: User = Depends(get_current_user)):
    return ok(
        request,
        {
            "provider": settings.LLM_PROVIDER,
            "base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "configured": bool(settings.llm_api_key),
        },
    )
