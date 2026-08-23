"""会话列表、新建会话、消息记录。一个会话必须先勾选知识库。"""

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok, page_data
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.core.limits import max_conversations_per_user
from app.db.models import (
    Chunk,
    Conversation,
    ConversationKnowledgeBase,
    ConversationMode,
    Document,
    FeedbackRating,
    KnowledgeBase,
    Message,
    MessageCitation,
    MessageFeedback,
    MessageRole,
    User,
    UserRole,
)
from app.db.session import get_db
from app.schemas.dto import ConversationCreateIn, ConversationDTO, ConversationPatchIn, FeedbackIn, MessageDTO
from app.services.acl import is_tenant_admin, require_read_many
from app.services.suggest_questions import suggest_questions

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


def _owner_kind(role: UserRole) -> str:
    """列表标签：管理者新建 vs 普通用户新建。"""
    if role in {UserRole.super_admin, UserRole.tenant_admin}:
        return "最高管理者" if role == UserRole.super_admin else "管理者"
    return "普通用户"


def _conv_scope(user: User):
    """管理者看本租户全部会话；普通用户只看自己建的。"""
    if is_tenant_admin(user):
        return (Conversation.tenant_id == user.tenant_id,)
    return (Conversation.user_id == user.id, Conversation.tenant_id == user.tenant_id)


async def _get_visible_conv(db: AsyncSession, conv_id: UUID, user: User) -> Conversation:
    """取会话。普通用户不能打开别人的；不存在和没权限都回 404。"""
    conv = await db.scalar(
        select(Conversation).where(Conversation.id == conv_id, Conversation.tenant_id == user.tenant_id)
    )
    if conv is None or (not is_tenant_admin(user) and conv.user_id != user.id):
        raise AppError(40004, "资源不存在", 404)
    return conv


async def _owners_map(db: AsyncSession, user_ids: list[UUID]) -> dict[UUID, User]:
    """一次查出会话创建人，避免列表 N+1。"""
    if not user_ids:
        return {}
    rows = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()
    return {u.id: u for u in rows}


def _conv_dto(
    conv: Conversation,
    knowledge_base_ids: list[UUID],
    messages: list[dict] | None = None,
    owner: User | None = None,
) -> dict:
    """会话转 JSON。列表和详情共用，避免漏字段。"""
    return ConversationDTO(
        id=conv.id,
        title=conv.title,
        mode=conv.mode.value,
        knowledge_base_ids=knowledge_base_ids,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        is_pinned=conv.is_pinned,
        owner_username=owner.username if owner else "",
        owner_kind=_owner_kind(owner.role) if owner else "普通用户",
        messages=messages,
    ).model_dump(mode="json")


@router.get("")
async def list_convs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """会话列表。普通用户只看自己的；管理者看本租户全部。"""
    filt = _conv_scope(user)
    total = int(await db.scalar(select(func.count()).select_from(Conversation).where(*filt)) or 0)
    rows = (
        await db.scalars(
            select(Conversation)
            .where(*filt)
            .order_by(
                Conversation.is_pinned.desc(),
                Conversation.pinned_at.desc().nulls_last(),
                Conversation.updated_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    kb_map = await _kb_ids_map(db, [c.id for c in rows])
    owners = await _owners_map(db, [c.user_id for c in rows])
    items = [_conv_dto(conv, kb_map.get(conv.id, []), owner=owners.get(conv.user_id)) for conv in rows]
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
    conv_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user.id, Conversation.tenant_id == user.tenant_id)
        )
        or 0
    )
    if conv_count >= max_conversations_per_user():
        raise AppError(40022, f"新对话最多 {max_conversations_per_user()} 个，请先删除后再创建", 422)
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
    return ok(request, _conv_dto(conv, body.knowledge_base_ids, owner=user), 201)


@router.get("/search")
async def search_convs(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按标题或消息正文关键词检索会话（无前端搜索框）。可见性与列表相同。"""
    like = f"%{q.strip()}%"
    scope = _conv_scope(user)
    matched_msg = exists().where(Message.conversation_id == Conversation.id, Message.content.ilike(like))
    filt = (*scope, or_(Conversation.title.ilike(like), matched_msg))
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
    owners = await _owners_map(db, [c.user_id for c in rows])
    items = [_conv_dto(conv, kb_map.get(conv.id, []), owner=owners.get(conv.user_id)) for conv in rows]
    return ok(request, page_data(items, total, page, page_size))


@router.get("/{conv_id}")
async def get_conv(
    request: Request,
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """会话详情 + 最近消息（含引用）。"""
    conv = await _get_visible_conv(db, conv_id, user)
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
    owner = (await _owners_map(db, [conv.user_id])).get(conv.user_id)
    return ok(request, _conv_dto(conv, ids, packed, owner=owner))


@router.get("/{conv_id}/export")
async def export_conv(
    request: Request,
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出会话 JSON（无前端导出按钮）。权限与打开会话相同。"""
    conv = await _get_visible_conv(db, conv_id, user)
    msgs = (
        await db.scalars(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.asc())
        )
    ).all()
    cite_map = await _citations_map(db, [m.id for m in msgs if m.role == MessageRole.assistant])
    packed = [
        _msg_dto(m, cite_map.get(m.id, []) if m.role == MessageRole.assistant else [])
        for m in msgs
    ]
    ids = await _kb_ids(db, conv.id)
    owner = (await _owners_map(db, [conv.user_id])).get(conv.user_id)
    return ok(
        request,
        {
            "conversation": _conv_dto(conv, ids, owner=owner),
            "messages": packed,
        },
    )


@router.get("/{conv_id}/suggested-questions")
async def suggested_questions(
    request: Request,
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """空会话用：根据绑定知识库已就绪文档，给出最多 3 条引导问题。"""
    conv = await _get_visible_conv(db, conv_id, user)
    kb_ids = await _kb_ids(db, conv.id)
    questions = await suggest_questions(db, user.tenant_id, kb_ids)
    return ok(request, {"questions": questions})


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
    conv = await _get_visible_conv(db, conv_id, user)
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
    """改会话标题或置顶。"""
    conv = await _get_visible_conv(db, conv_id, user)
    if body.title is not None:
        conv.title = body.title.strip()
        if not conv.title:
            raise AppError(40022, "标题不能为空", 422)
    if body.is_pinned is not None:
        conv.is_pinned = body.is_pinned
        conv.pinned_at = datetime.now(timezone.utc) if body.is_pinned else None
    await db.commit()
    await db.refresh(conv)
    ids = await _kb_ids(db, conv.id)
    owner = (await _owners_map(db, [conv.user_id])).get(conv.user_id)
    return ok(request, _conv_dto(conv, ids, owner=owner))


@router.delete("/{conv_id}")
async def delete_conv(
    request: Request,
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除整个会话及其消息。"""
    conv = await _get_visible_conv(db, conv_id, user)
    await db.delete(conv)
    await db.commit()
    return ok(request, {"deleted": True})


@router.put("/{conv_id}/messages/{message_id}/feedback")
async def put_feedback(
    request: Request,
    conv_id: UUID,
    message_id: UUID,
    body: FeedbackIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """点赞/点踩存储；rating 为空则清除。无前端按钮。"""
    conv = await _get_visible_conv(db, conv_id, user)
    msg = await db.scalar(select(Message).where(Message.id == message_id, Message.conversation_id == conv.id))
    if msg is None:
        raise AppError(40004, "资源不存在", 404)
    row = await db.scalar(
        select(MessageFeedback).where(MessageFeedback.message_id == msg.id, MessageFeedback.user_id == user.id)
    )
    if body.rating is None:
        if row is not None:
            await db.delete(row)
            await db.commit()
        return ok(request, {"message_id": str(msg.id), "rating": None})
    if row is None:
        row = MessageFeedback(
            tenant_id=user.tenant_id,
            message_id=msg.id,
            user_id=user.id,
            rating=FeedbackRating(body.rating),
        )
        db.add(row)
    else:
        row.rating = FeedbackRating(body.rating)
    await db.commit()
    await db.refresh(row)
    return ok(request, {"message_id": str(msg.id), "rating": row.rating.value})


@router.get("/{conv_id}/messages/{message_id}/feedback")
async def get_feedback(
    request: Request,
    conv_id: UUID,
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await _get_visible_conv(db, conv_id, user)
    msg = await db.scalar(select(Message).where(Message.id == message_id, Message.conversation_id == conv.id))
    if msg is None:
        raise AppError(40004, "资源不存在", 404)
    row = await db.scalar(
        select(MessageFeedback).where(MessageFeedback.message_id == msg.id, MessageFeedback.user_id == user.id)
    )
    return ok(request, {"message_id": str(msg.id), "rating": row.rating.value if row else None})
