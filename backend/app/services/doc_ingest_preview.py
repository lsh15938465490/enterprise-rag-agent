"""上传解析完成后：切块数量、Agent 示例问题、召回是否偏弱。"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document
from app.services.rag_pipeline import retrieve
from app.services.suggest_questions import suggest_questions

LOW_RECALL_THRESHOLD = 0.2


async def ingest_preview(db: AsyncSession, doc: Document) -> dict:
    """给文档上传页：切块数 + 3 个可点击示例问题（含召回提示）。"""
    chunk_count = int(
        await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)) or 0
    )
    questions = await suggest_questions(db, doc.tenant_id, [doc.knowledge_base_id], document_id=doc.id)
    samples: list[dict] = []
    for text in questions[:3]:
        hits = await retrieve(db, doc.tenant_id, [doc.knowledge_base_id], text)
        from_doc = [h for h in hits if h.chunk.document_id == doc.id]
        score = float(from_doc[0].score) if from_doc else (float(hits[0].score) if hits else 0.0)
        if not from_doc:
            low_recall = True
        elif 0.05 <= score <= 1.0 and score < LOW_RECALL_THRESHOLD:
            low_recall = True
        else:
            low_recall = False
        samples.append({"question": text, "score": round(score, 4), "low_recall": low_recall})
    return {
        "document_id": str(doc.id),
        "filename": doc.filename,
        "chunk_count": chunk_count,
        "questions": samples,
    }
