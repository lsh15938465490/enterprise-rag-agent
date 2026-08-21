"""Agent 工具注册表：只有白名单里的名字才能被模型调用，防止乱执行。"""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User, UserRole
from app.tools.kb_stats import query_kb_stats
from app.tools.sql_query import assert_readonly_select
from app.tools.weather import get_weather

TOOL_CATALOG = [
    {"name": "get_weather", "description": "查询城市天气", "enabled": True},
    {"name": "query_kb_stats", "description": "当前租户知识库与文档数量", "enabled": True},
    {"name": "run_readonly_sql", "description": "只读 SQL（默认关闭）", "enabled": settings.ENABLE_READONLY_SQL_TOOL},
]


def list_tools() -> list[dict[str, Any]]:
    items = list(TOOL_CATALOG)
    items[-1]["enabled"] = settings.ENABLE_READONLY_SQL_TOOL
    return items


async def run_tool(
    *,
    name: str,
    args: dict[str, Any],
    db: AsyncSession,
    tenant_id: UUID,
    user: User,
) -> str:
    if name not in {t["name"] for t in TOOL_CATALOG}:
        return f"未知工具：{name}"
    if name == "get_weather":
        return await get_weather(str(args.get("city") or "北京"))
    if name == "query_kb_stats":
        return await query_kb_stats(db, tenant_id)
    if name == "run_readonly_sql":
        if not settings.ENABLE_READONLY_SQL_TOOL:
            return "run_readonly_sql 未启用"
        if user.role not in {UserRole.tenant_admin, UserRole.super_admin}:
            return "仅租户管理员可执行只读 SQL"
        try:
            sql = assert_readonly_select(str(args.get("sql") or ""))
        except ValueError as exc:
            return f"SQL 拒绝：{exc}"
        try:
            import asyncio

            async def _run():
                result = await db.execute(text(sql))
                return [list(r) for r in result.fetchmany(50)]

            rows = await asyncio.wait_for(_run(), timeout=3)
            return f"行数 {len(rows)}：{rows}"
        except TimeoutError:
            return "SQL 执行超时"
        except Exception as exc:
            return f"SQL 执行失败：{exc}"
    return f"未实现工具：{name}"
