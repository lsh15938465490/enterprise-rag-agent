"""AI 根据当前知识库检索结果流式生成 Markdown 文档，确认后入库解析。"""

import json
import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.documents import _dto, _enqueue, _persist_upload
from app.api.v1.helpers import ok
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.core.limits import max_documents_per_kb
from app.db.models import Document, User
from app.db.session import get_db
from app.schemas.dto import GenerateDocumentIn, SaveGeneratedDocumentIn
from app.services.acl import get_kb, require_write
from app.services.ai_document import GENERATE_DOC_SYSTEM, build_generate_prompt
from app.services.llm_deepseek import stream_chat
from app.services.rag_pipeline import retrieve
from app.services.storage import secure_filename

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _safe_md_name(title: str) -> str:
    base = secure_filename(title.rsplit(".", 1)[0] if title.lower().endswith(".md") else title)
    return f"{base or 'AI生成文档'}.md"


@router.post("/generate-document")
async def generate_document(
    request: Request,
    body: GenerateDocumentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await get_kb(db, body.knowledge_base_id, user)
    await require_write(db, user, kb)
    try:
        hits = await retrieve(db, kb.tenant_id, [kb.id], f"{body.title}\n{body.requirements}")
    except Exception:
        logger.exception("AI 创作检索失败 kb_id=%s", kb.id)
        raise AppError(50010, "检索失败，请稍后重试", 502)

    contexts = []
    citation_payloads = []
    for item in hits:
        contexts.append(
            {
                "filename": item.filename,
                "page": item.chunk.page_number,
                "heading": item.chunk.heading,
                "content": item.chunk.content,
            }
        )
        citation_payloads.append(
            {
                "chunk_id": str(item.chunk.id),
                "filename": item.filename,
                "page_number": item.chunk.page_number,
                "heading": item.chunk.heading,
                "score": item.score,
                "snippet": item.chunk.content[:240],
            }
        )

    llm_messages = [
        {"role": "system", "content": GENERATE_DOC_SYSTEM},
        {"role": "user", "content": build_generate_prompt(body.title, body.requirements, contexts)},
    ]
    cold_start = not hits

    async def event_stream():
        yield _sse("meta", {"cold_start": cold_start, "knowledge_base_id": str(kb.id)})
        for payload in citation_payloads:
            yield _sse("citation", payload)
        full_parts: list[str] = []
        try:
            async for delta in stream_chat(llm_messages, temperature=0.4, max_tokens=4096):
                full_parts.append(delta)
                yield _sse("delta", {"text": delta})
        except Exception:
            logger.exception("AI 创作模型调用失败 kb_id=%s", kb.id)
            yield _sse("error", {"code": 50010, "message": "模型调用失败"})
            return
        yield _sse("done", {"cold_start": cold_start, "length": len("".join(full_parts))})

    if body.stream:
        return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)

    chunks: list[str] = []
    citations: list[dict] = []
    async for raw in event_stream():
        if not raw.startswith("event:"):
            continue
        lines = raw.strip().split("\n")
        event = lines[0][6:].strip()
        data_line = next((ln for ln in lines if ln.startswith("data:")), "")
        payload = json.loads(data_line[5:]) if data_line else {}
        if event == "delta":
            chunks.append(payload.get("text") or "")
        elif event == "citation":
            citations.append(payload)
        elif event == "error":
            raise AppError(int(payload.get("code") or 50010), payload.get("message") or "模型调用失败", 502)
    return ok(request, {"content": "".join(chunks), "citations": citations, "cold_start": cold_start})


@router.post("/save-document")
async def save_document(
    request: Request,
    body: SaveGeneratedDocumentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await get_kb(db, body.knowledge_base_id, user)
    await require_write(db, user, kb)
    filename = _safe_md_name(body.title)
    dup = await db.scalar(
        select(Document.id).where(Document.knowledge_base_id == kb.id, Document.filename == filename)
    )
    if dup is not None:
        raise AppError(40022, "已经有相同名字的文档，请修改标题后重新保存", 422)
    doc_count = int(
        await db.scalar(select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb.id)) or 0
    )
    if doc_count >= max_documents_per_kb():
        raise AppError(40022, f"每个知识库最多上传 {max_documents_per_kb()} 份文档，请先删除后再保存", 422)
    data = body.content.encode("utf-8")
    doc = await _persist_upload(
        db,
        kb=kb,
        user=user,
        filename=filename,
        content_type="text/markdown",
        data=data,
    )
    await db.commit()
    await db.refresh(doc)
    await _enqueue(doc.id)
    return ok(request, _dto(doc), 202)
