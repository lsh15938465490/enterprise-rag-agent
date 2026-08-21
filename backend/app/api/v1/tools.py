"""列出 Agent 能调用的工具白名单（天气、知识库统计、只读 SQL）。"""

from fastapi import APIRouter, Depends, Request

from app.api.v1.helpers import ok
from app.core.deps import get_current_user
from app.db.models import User
from app.tools.registry import list_tools

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def tools(request: Request, _user: User = Depends(get_current_user)):
    """必须登录才能看工具列表，避免未登录探测系统能力。"""
    return ok(request, list_tools())
