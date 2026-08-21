"""会话列表、新建会话、消息记录。一个会话必须先勾选知识库。"""

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok, page_data
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.db.models import (
    Chunk,
    Conversation,
    ConversationKnowledgeBase,
    ConversationMode,
    Document,
    KnowledgeBase,
    Message,
    MessageCitation,
    MessageRole,
    User,
)
from app.db.session import get_db
from app.schemas.dto import ConversationCreateIn, ConversationDTO, ConversationPatchIn, MessageDTO
from app.services.acl import require_read_many

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _kb_ids_map(db: AsyncSession, conv_ids: list[UUID]) -> dict[UUID, list[UUID]]:
    """一次查出多个会话绑定的知识库，避免列表页 N+1 查询。"""
    if not conv_ids:
        return {}
    rows = (
        await db.scalars(
            select(ConversationKnowledgeBase).where(ConversationKnowledgeBase.conversation_id.in_(conv_ids))
        )
    ).all()
    out: dict[UUID, list[UUID]] = defaultdict(list)
    for row in rows:
        out[row.conversation_id].append(row.knowledge_base_id)
    return out


async def _kb_ids(db: AsyncSession, conv_id: UUID) -> list[UUID]:
    """单个会话绑定了哪些知识库。"""
    return (await _kb_ids_map(db, [conv_id])).get(conv_id, [])


def _cite_dict(cite: MessageCitation, chunk: Chunk, doc: Document) -> dict:
    """把引用整理成前端来源卡片需要的字段。"""
    return {
        "chunk_id": str(chunk.id),
        "document_id": str(doc.id),
        "filename": doc.filename,
        "page_number": chunk.page_number,
        "heading": chunk.heading,
        "score": cite.score,
        "snippet": chunk.content[:240],
    }


async def _citations_map(db: AsyncSession, message_ids: list[UUID]) -> dict[UUID, list[dict]]:
    """一次 join 查出多条助手消息的引用。"""
    if not message_ids:
        return {}
    rows = (
        await db.execute(
            select(MessageCitation, Chunk, Document)
            .join(Chunk, Chunk.id == MessageCitation.chunk_id)
            .join(Document, Document.id == Chunk.document_id)
            .where(MessageCitation.message_id.in_(message_ids))
            .order_by(MessageCitation.message_id, MessageCitation.rank)
        )
    ).all()
    out: dict[UUID, list[dict]] = defaultdict(list)
    for cite, chunk, doc in rows:
        out[cite.message_id].append(_cite_dict(cite, chunk, doc))
    return out


def _msg_dto(msg: Message, citations: list[dict] | None = None) -> dict:
    """一条消息转成 JSON。"""
    return MessageDTO(
        id=msg.id,
        role=msg.role.value,
        content=msg.content,
        citations=citations or [],
        created_at=msg.created_at,
    ).model_dump(mode="json")


async def _citations_for(db: AsyncSession, message_id: UUID) -> list[dict]:
    """单条消息的引用（非流式聊天收尾会用到）。"""
    return (await _citations_map(db, [message_id])).get(message_id, [])


@router.get("")
async def list_convs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的会话列表（分页）。"""
    filt = (Conversation.user_id == user.id, Conversation.tenant_id == user.tenant_id)
    total = int(await db.scalar(select(func.count()).select_from(Conversation).where(*filt)) or 0)
    rows = (
        await db.scalars(
            select(Conversation)
            .where(*filt)
            .order_by(Conversation.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    kb_map = await _kb_ids_map(db, [c.id for c in rows])
    items = []
    for conv in rows:
        items.append(
            ConversationDTO(
                id=conv.id,
                title=conv.title,
                mode=conv.mode.value,
                knowledge_base_ids=kb_map.get(conv.id, []),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            ).model_dump(mode="json")
        )
    return ok(request, page_data(items, total, page, page_size))


@router.post("")
async def create_conv(
    request: Request,
    body: ConversationCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """新建会话：知识库必须存在、未停用，且当前用户可读。"""
    kbs = (
        await db.scalars(
            select(KnowledgeBase).where(
                KnowledgeBase.id.in_(body.knowledge_base_ids),
                KnowledgeBase.tenant_id == user.tenant_id,
                KnowledgeBase.is_active.is_(True),
            )
        )
    ).all()
    if len(kbs) != len(body.knowledge_base_ids):
        raise AppError(40004, "知识库不存在或已停用", 404)
    await require_read_many(db, user, list(kbs))
    conv = Conversation(
        tenant_id=user.tenant_id,
        user_id=user.id,
        title=body.title or "新对话",
        mode=ConversationMode(body.mode),
    )
    db.add(conv)
    await db.flush()
    for kb_id in body.knowledge_base_ids:
        db.add(ConversationKnowledgeBase(conversation_id=conv.id, knowledge_base_id=kb_id))
    await db.commit()
    await db.refresh(conv)
    return ok(
        request,
        ConversationDTO(
            id=conv.id,
            title=conv.title,
            mode=conv.mode.value,
            knowledge_base_ids=body.knowledge_base_ids,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        ).model_dump(mode="json"),
        201,
    )


@router.get("/{conv_id}")
async def get_conv(
    request: Request,
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """会话详情 + 最近消息（含引用）。只能看自己的。"""
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user.id, Conversation.tenant_id == user.tenant_id
        )
    )
    if conv is None:
        raise AppError(40004, "资源不存在", 404)
    msgs = (
        await db.scalars(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.asc()).limit(50)
        )
    ).all()
    cite_map = await _citations_map(
        db, [m.id for m in msgs if m.role == MessageRole.assistant]
    )
    packed = [
        _msg_dto(m, cite_map.get(m.id, []) if m.role == MessageRole.assistant else [])
        for m in msgs
    ]
    ids = await _kb_ids(db, conv.id)
    data = ConversationDTO(
        id=conv.id,
        title=conv.title,
        mode=conv.mode.value,
        knowledge_base_ids=ids,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=packed,
    ).model_dump(mode="json")
    return ok(request, data)


@router.get("/{conv_id}/messages")
async def list_messages(
    request: Request,
    conv_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """某个会话的消息分页。"""
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user.id, Conversation.tenant_id == user.tenant_id
        )
    )
    if conv is None:
        raise AppError(40004, "资源不存在", 404)
    total = int(
        await db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)) or 0
    )
    rows = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    cite_map = await _citations_map(db, [m.id for m in rows if m.role == MessageRole.assistant])
    items = [
        _msg_dto(m, cite_map.get(m.id, []) if m.role == MessageRole.assistant else [])
        for m in rows
    ]
    return ok(request, page_data(items, total, page, page_size))


@router.patch("/{conv_id}")
async def patch_conv(
    request: Request,
    conv_id: UUID,
    body: ConversationPatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """改会话标题。"""
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user.id, Conversation.tenant_id == user.tenant_id
        )
    )
    if conv is None:
        raise AppError(40004, "资源不存在", 404)
    if body.title:
        conv.title = body.title
    await db.commit()
    await db.refresh(conv)
    ids = await _kb_ids(db, conv.id)
    return ok(
        request,
        ConversationDTO(
            id=conv.id,
            title=conv.title,
            mode=conv.mode.value,
            knowledge_base_ids=ids,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        ).model_dump(mode="json"),
    )


@router.delete("/{conv_id}")
async def delete_conv(
    request: Request,
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除整个会话及其消息。"""
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user.id, Conversation.tenant_id == user.tenant_id
        )
    )
    if conv is None:
        raise AppError(40004, "资源不存在", 404)
    await db.delete(conv)
    await db.commit()
    return ok(request, {"deleted": True})
