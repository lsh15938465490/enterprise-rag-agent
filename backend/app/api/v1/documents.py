"""文档上传、下载、删除、重新解析。上传后会异步切块并写入向量库。"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok, page_data
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.db.models import Document, DocStatus, User
from app.db.session import get_db
from app.schemas.dto import DocumentDTO
from app.services.acl import get_kb, require_read, require_write
from app.services.document_pipeline import process_document
from app.services.qdrant_store import delete_by_document
from app.services.storage import abs_path, delete_file, save_bytes
from app.workers.tasks import parse_document as parse_task

router = APIRouter(tags=["documents"])

ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md"}


def _dto(doc: Document) -> dict:
    return DocumentDTO.model_validate(doc).model_dump(mode="json")


async def _enqueue(doc_id: UUID) -> None:
    if settings.INLINE_DOCUMENT_PIPELINE:
        asyncio.create_task(process_document(doc_id))
        return
    parse_task.delay(str(doc_id))


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_docs(
    request: Request,
    kb_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: DocStatus | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await get_kb(db, kb_id, user.tenant_id)
    await require_read(db, user, kb)
    stmt = select(Document).where(Document.knowledge_base_id == kb.id)
    count_stmt = select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb.id)
    if status is not None:
        stmt = stmt.where(Document.status == status)
        count_stmt = count_stmt.where(Document.status == status)
    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.scalars(stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    ).all()
    return ok(request, page_data([_dto(r) for r in rows], total, page, page_size))


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_doc(
    request: Request,
    kb_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await get_kb(db, kb_id, user.tenant_id)
    await require_write(db, user, kb)
    filename = file.filename or "file"
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in ALLOWED_EXT:
        raise AppError(40022, "不支持的文件类型", 422)
    data = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise AppError(40022, "文件超过大小限制", 422)
    from uuid import uuid4

    doc_id = uuid4()
    storage_key, checksum = save_bytes(str(user.tenant_id), str(kb.id), str(doc_id), filename, data)
    doc = Document(
        id=doc_id,
        tenant_id=user.tenant_id,
        knowledge_base_id=kb.id,
        uploaded_by=user.id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        file_size=len(data),
        storage_key=storage_key,
        status=DocStatus.uploaded,
        checksum_sha256=checksum,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    await _enqueue(doc.id)
    return ok(request, _dto(doc), 202)


@router.get("/documents/{doc_id}")
async def get_doc(
    request: Request,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await db.scalar(select(Document).where(Document.id == doc_id, Document.tenant_id == user.tenant_id))
    if doc is None:
        raise AppError(40004, "资源不存在", 404)
    kb = await get_kb(db, doc.knowledge_base_id, user.tenant_id)
    await require_read(db, user, kb)
    return ok(request, _dto(doc))


@router.get("/documents/{doc_id}/file")
async def download_doc(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await db.scalar(select(Document).where(Document.id == doc_id, Document.tenant_id == user.tenant_id))
    if doc is None:
        raise AppError(40004, "资源不存在", 404)
    kb = await get_kb(db, doc.knowledge_base_id, user.tenant_id)
    await require_read(db, user, kb)
    path = abs_path(doc.storage_key)
    if not path.exists():
        raise AppError(40004, "资源不存在", 404)
    return FileResponse(path, filename=doc.filename, media_type=doc.content_type)


@router.post("/documents/{doc_id}/reprocess")
async def reprocess(
    request: Request,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await db.scalar(select(Document).where(Document.id == doc_id, Document.tenant_id == user.tenant_id))
    if doc is None:
        raise AppError(40004, "资源不存在", 404)
    kb = await get_kb(db, doc.knowledge_base_id, user.tenant_id)
    await require_write(db, user, kb)
    doc.status = DocStatus.uploaded
    doc.error_message = None
    await db.commit()
    await _enqueue(doc.id)
    return ok(request, _dto(doc), 202)


@router.delete("/documents/{doc_id}")
async def delete_doc(
    request: Request,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await db.scalar(select(Document).where(Document.id == doc_id, Document.tenant_id == user.tenant_id))
    if doc is None:
        raise AppError(40004, "资源不存在", 404)
    kb = await get_kb(db, doc.knowledge_base_id, user.tenant_id)
    await require_write(db, user, kb)
    await delete_by_document(kb.qdrant_collection, doc.id)
    delete_file(doc.storage_key)
    await db.delete(doc)
    await db.commit()
    return ok(request, {"deleted": True})
