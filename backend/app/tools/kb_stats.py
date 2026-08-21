"""统计当前租户有多少知识库、多少文档，给 Agent 回答「库里有多少资料」。"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, KnowledgeBase


async def query_kb_stats(db: AsyncSession, tenant_id: UUID) -> str:
    """只统计当前租户，不会把别的公司数据算进来。"""
    kb_count = int(
        await db.scalar(
            select(func.count()).select_from(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id)
        )
        or 0
    )
    doc_count = int(
        await db.scalar(select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)) or 0
    )
    return f"当前租户知识库 {kb_count} 个，文档 {doc_count} 份。"
