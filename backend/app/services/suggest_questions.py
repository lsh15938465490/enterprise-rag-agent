"""根据知识库切块生成引导问题，给空会话页展示。"""

import json
import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Chunk, Document, DocStatus
from app.services.llm_deepseek import complete_chat

logger = logging.getLogger(__name__)


def _as_question(text: str) -> str:
    """标题转成问句；已经是问句就原样用。"""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = t[:48]
    if not t:
        return ""
    if t.endswith("？") or t.endswith("?"):
        return t if t.endswith("？") else t[:-1] + "？"
    return f"{t}包括哪些要点？"


def _heuristic(rows: list[tuple[str | None, str, str]]) -> list[str]:
    """用标题和文件名拼 3 个互不相同的问题，不依赖大模型。"""
    seen: set[str] = set()
    out: list[str] = []
    for heading, content, filename in rows:
        cand = ""
        if heading:
            cand = _as_question(heading)
        elif content:
            snippet = re.sub(r"\s+", " ", content.strip())[:28]
            if snippet:
                cand = f"文档中「{snippet}」是什么意思？"
        elif filename:
            cand = f"「{filename}」这份资料主要讲什么？"
        if cand and cand not in seen:
            seen.add(cand)
            out.append(cand)
        if len(out) >= 3:
            return out
    return out


async def suggest_questions(db: AsyncSession, tenant_id: UUID, kb_ids: list[UUID]) -> list[str]:
    """从已就绪文档的切块里取摘录，优先让模型出题，失败则用标题启发式。"""
    if not kb_ids:
        return []
    rows = (
        await db.execute(
            select(Chunk.heading, Chunk.content, Document.filename)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.tenant_id == tenant_id,
                Chunk.knowledge_base_id.in_(kb_ids),
                Document.status == DocStatus.ready,
            )
            .order_by(Chunk.chunk_index.asc())
            .limit(40)
        )
    ).all()
    fallback = _heuristic([(r[0], r[1] or "", r[2] or "") for r in rows])
    if not settings.DEEPSEEK_API_KEY or not rows:
        return fallback[:3]

    excerpts: list[str] = []
    for heading, content, filename in rows[:12]:
        piece = (heading or "") + " " + (content or "")[:180]
        excerpts.append(f"来源:{filename} {piece.strip()}")
    prompt = "\n".join(excerpts)[:2500]
    try:
        raw = await complete_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "根据摘录生成恰好 3 个中文引导问题。只输出 JSON 字符串数组，"
                        "不要 Markdown。问题必须能根据摘录回答，不要编造制度或数字。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
        parsed = json.loads(cleaned)
        qs = [str(x).strip() for x in parsed if str(x).strip()]
        if len(qs) >= 3:
            return qs[:3]
    except Exception:
        logger.warning("引导问题模型生成失败，改用标题启发式", exc_info=True)
    return fallback[:3]
