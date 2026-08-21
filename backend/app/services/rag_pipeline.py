"""
检索流水线（RAG 的 R）：
1) 向量库找语义相近的段落；2) 数据库按中文词找；3) RRF 融合；4) 可选重排序。
没有命中就会让聊天接口回复「知识库未覆盖」。
"""

import logging
import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocStatus, KnowledgeBase
from app.services.chunker import query_lexemes
from app.services.embeddings import EmbeddingClient
from app.services.qdrant_store import search as qdrant_search
from app.services.rerank import rerank
from app.services.rrf import rrf

logger = logging.getLogger(__name__)


class RetrievedChunk:
    def __init__(self, chunk: Chunk, filename: str, score: float):
        self.chunk = chunk
        self.filename = filename
        self.score = score


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _tsquery_string(query: str) -> str | None:
    lexemes = query_lexemes(query)
    if not lexemes:
        return None
    cleaned: list[str] = []
    for item in lexemes:
        token = re.sub(r"[^\w\u4e00-\u9fff]+", "", item, flags=re.UNICODE)
        if token:
            cleaned.append(token)
    if not cleaned:
        return None
    return " | ".join(cleaned)


async def _ilike_search(
    db: AsyncSession,
    tenant_id: UUID,
    kb_ids: list[UUID],
    query: str,
    top_k: int,
) -> list[tuple[UUID, float]]:
    terms = query_lexemes(query) or [query.strip()]
    likes = [f"%{_escape_like(term)}%" for term in terms if term]
    if not likes:
        return []
    conds = [Chunk.content.ilike(like) for like in likes]
    ids = (
        await db.scalars(
            select(Chunk.id)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.tenant_id == tenant_id,
                Chunk.knowledge_base_id.in_(kb_ids),
                Document.status == DocStatus.ready,
                or_(*conds),
            )
            .limit(top_k)
        )
    ).all()
    return [(cid, 1.0 / (i + 1)) for i, cid in enumerate(ids)]


async def keyword_search(
    db: AsyncSession,
    tenant_id: UUID,
    kb_ids: list[UUID],
    query: str,
    top_k: int = 40,
) -> list[tuple[UUID, float]]:
    if not kb_ids:
        return []
    tsq_text = _tsquery_string(query)
    if tsq_text:
        tsq = func.to_tsquery("simple", tsq_text)
        stmt = (
            select(Chunk.id, func.ts_rank(Chunk.search_tsv, tsq).label("rank"))
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.tenant_id == tenant_id,
                Chunk.knowledge_base_id.in_(kb_ids),
                Document.status == DocStatus.ready,
                Chunk.search_tsv.op("@@")(tsq),
            )
            .order_by(func.ts_rank(Chunk.search_tsv, tsq).desc())
            .limit(top_k)
        )
        try:
            rows = (await db.execute(stmt)).all()
            if rows:
                return [(row[0], float(row[1])) for row in rows]
        except Exception:
            logger.warning("全文检索失败，回退到 ILIKE query=%s", query[:80], exc_info=True)
    return await _ilike_search(db, tenant_id, kb_ids, query, top_k)


async def retrieve(
    db: AsyncSession,
    tenant_id: UUID,
    kb_ids: list[UUID],
    query: str,
) -> list[RetrievedChunk]:
    embedder = EmbeddingClient()
    qvec = (await embedder.embed_texts([query]))[0]
    collections = (
        await db.scalars(
            select(KnowledgeBase.qdrant_collection).where(
                KnowledgeBase.id.in_(kb_ids), KnowledgeBase.tenant_id == tenant_id
            )
        )
    ).all()
    dense = await qdrant_search(list(collections), qvec, tenant_id, kb_ids, top_k=40)
    sparse = await keyword_search(db, tenant_id, kb_ids, query, top_k=40)
    fused = rrf(dense, sparse, k=60)[:40]
    if not fused:
        return []
    chunk_ids = [cid for cid, _ in fused]
    chunks = (
        await db.scalars(select(Chunk).where(Chunk.id.in_(chunk_ids), Chunk.tenant_id == tenant_id))
    ).all()
    by_id = {c.id: c for c in chunks}
    docs = (
        await db.scalars(select(Document).where(Document.id.in_({c.document_id for c in chunks})))
    ).all()
    filename = {d.id: d.filename for d in docs}
    candidates = []
    fused_score = {cid: score for cid, score in fused}
    for cid in chunk_ids:
        chunk = by_id.get(cid)
        if chunk is None:
            continue
        candidates.append((cid, chunk.content, fused_score[cid]))
    ranked = await rerank(query, candidates, top_n=8)
    out: list[RetrievedChunk] = []
    for cid, score in ranked:
        chunk = by_id[cid]
        out.append(RetrievedChunk(chunk, filename.get(chunk.document_id, ""), score))
    return out
