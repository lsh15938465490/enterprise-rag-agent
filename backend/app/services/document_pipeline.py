"""文档处理流水线：读文件 → 切块入库 → 算向量 → 写入 Qdrant，最后状态变成 ready。"""

import logging
import uuid
from uuid import UUID

from qdrant_client.models import PointStruct
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocStatus, KnowledgeBase
from app.db.session import SessionLocal
from app.services.chunker import chunk_blocks
from app.services.embeddings import EmbeddingClient
from app.services.parsers import parse_file
from app.services.qdrant_store import delete_by_document, upsert_points
from app.services.storage import abs_path

logger = logging.getLogger(__name__)


async def process_document(document_id: UUID) -> None:
    """解析一篇文档的全过程。任一步失败会把 status 设为 failed 并记下原因。"""
    async with SessionLocal() as db:
        doc = await db.scalar(select(Document).where(Document.id == document_id))
        if doc is None:
            return
        kb = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.id == doc.knowledge_base_id))
        if kb is None:
            return
        doc.status = DocStatus.parsing
        doc.error_message = None
        await db.commit()
        try:
            path = abs_path(doc.storage_key)
            blocks = parse_file(path, doc.content_type, doc.filename)
            drafts = chunk_blocks([(b.content, b.page_number, b.heading) for b in blocks])
            if not drafts:
                raise ValueError("EMPTY_TEXT")
            await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
            chunks: list[Chunk] = []
            for draft in drafts:
                chunks.append(
                    Chunk(
                        tenant_id=doc.tenant_id,
                        document_id=doc.id,
                        knowledge_base_id=doc.knowledge_base_id,
                        chunk_index=draft.chunk_index,
                        content=draft.content,
                        content_seg=draft.content_seg,
                        token_count=draft.token_count,
                        page_number=draft.page_number,
                        heading=draft.heading,
                        qdrant_point_id=uuid.uuid4(),
                    )
                )
            db.add_all(chunks)
            doc.page_count = max((b.page_number or 0) for b in blocks) or None
            doc.status = DocStatus.parsed
            await db.commit()
            for c in chunks:
                await db.refresh(c)
            await _embed(db, doc, kb, chunks)
        except ValueError as exc:
            doc.status = DocStatus.failed
            doc.error_message = str(exc)
            await db.commit()
        except Exception:
            logger.exception("解析文档失败 document_id=%s", document_id)
            doc.status = DocStatus.failed
            doc.error_message = "PARSE_FAILED"
            await db.commit()


async def _embed(db: AsyncSession, doc: Document, kb: KnowledgeBase, chunks: list[Chunk]) -> None:
    """给所有切块算向量并 upsert 到 Qdrant，成功则 ready。"""
    doc.status = DocStatus.embedding
    await db.commit()
    try:
        await delete_by_document(kb.qdrant_collection, doc.id)
        embedder = EmbeddingClient()
        texts = [c.content for c in chunks]
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 32):
            vectors.extend(await embedder.embed_texts(texts[i : i + 32]))
        points = []
        for chunk, vec in zip(chunks, vectors, strict=True):
            points.append(
                PointStruct(
                    id=str(chunk.qdrant_point_id),
                    vector=vec,
                    payload={
                        "tenant_id": str(doc.tenant_id),
                        "knowledge_base_id": str(doc.knowledge_base_id),
                        "document_id": str(doc.id),
                        "chunk_id": str(chunk.id),
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "heading": chunk.heading,
                        "filename": doc.filename,
                    },
                )
            )
        await upsert_points(kb.qdrant_collection, points)
        doc.status = DocStatus.ready
        await db.commit()
    except Exception:
        logger.exception("向量化失败 document_id=%s", doc.id)
        doc.status = DocStatus.failed
        doc.error_message = "EMBED_FAILED"
        await db.commit()
