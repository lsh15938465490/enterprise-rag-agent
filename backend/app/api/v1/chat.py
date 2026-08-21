"""
聊天接口。RAG 模式：先检索再让模型根据片段回答；Agent 模式：走 LangGraph 多步工具。
用 SSE（Server-Sent Events）把字一个一个推到浏览器。
"""

import json
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.db.models import (
    Conversation,
    ConversationKnowledgeBase,
    ConversationMode,
    Message,
    MessageCitation,
    MessageRole,
    User,
)
from app.db.session import get_db
from app.schemas.dto import ChatIn, MessageDTO
from app.services.agent_graph import run_multi_agent
from app.services.llm_deepseek import SYSTEM_PROMPT, build_user_prompt, stream_chat
from app.services.rag_pipeline import retrieve

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)
UNCOVERED = "当前知识库未覆盖该问题。"
# 语义分大约在 0.05~1 时才用这个门槛；关键词融合分很小，不能拿它当「没搜到」。
SCORE_THRESHOLD = 0.2


def _sse(event: str, data: dict) -> str:
    """拼一条 SSE 文本：event 名字 + data JSON。浏览器按这个一块块解析。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/completions")
async def completions(
    request: Request,
    body: ChatIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """问答入口。只能聊自己的会话；Agent 模式走另一条函数。"""
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == body.conversation_id,
            Conversation.user_id == user.id,
            Conversation.tenant_id == user.tenant_id,
        )
    )
    if conv is None:
        raise AppError(40004, "资源不存在", 404)
    kb_ids = list(
        await db.scalars(
            select(ConversationKnowledgeBase.knowledge_base_id).where(
                ConversationKnowledgeBase.conversation_id == conv.id
            )
        )
    )
    user_msg = Message(conversation_id=conv.id, role=MessageRole.user, content=body.question)
    db.add(user_msg)
    await db.flush()
    assistant_id = uuid4()

    if conv.mode == ConversationMode.agent:
        return await _agent_completions(request, body, db, user, conv, kb_ids, assistant_id)

    hits = await retrieve(db, user.tenant_id, kb_ids, body.question)
    if not hits:
        uncovered = True
    elif hits[0].score < SCORE_THRESHOLD and 0.05 <= hits[0].score <= 1.0:
        # 融合分约 0.01~0.03，不能当语义分；仅对像余弦/交叉编码器的分数做门槛。
        uncovered = True
    else:
        uncovered = False
    contexts = []
    if not uncovered:
        for item in hits:
            contexts.append(
                {
                    "filename": item.filename,
                    "page": item.chunk.page_number,
                    "heading": item.chunk.heading,
                    "content": item.chunk.content,
                }
            )
    history = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
    ).all()
    history = list(reversed(history))
    llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history[:-1]:
        if m.role in {MessageRole.user, MessageRole.assistant}:
            llm_messages.append({"role": m.role.value, "content": m.content})
    if uncovered:
        llm_messages.append({"role": "user", "content": f"问题：{body.question}\n\n【检索结果】\n（无）"})
    else:
        llm_messages.append({"role": "user", "content": build_user_prompt(body.question, contexts)})

    async def event_stream():
        yield _sse("meta", {"message_id": str(assistant_id)})
        citations_payload = []
        if uncovered:
            text = UNCOVERED
            for ch in text:
                yield _sse("delta", {"text": ch})
            full = text
        else:
            for item in hits:
                payload = {
                    "chunk_id": str(item.chunk.id),
                    "filename": item.filename,
                    "page_number": item.chunk.page_number,
                    "score": item.score,
                    "snippet": item.chunk.content[:240],
                }
                citations_payload.append((item, payload))
                yield _sse("citation", payload)
            full_parts: list[str] = []
            try:
                async for delta in stream_chat(llm_messages, temperature=0.3):
                    full_parts.append(delta)
                    yield _sse("delta", {"text": delta})
            except Exception:
                logger.exception("DeepSeek 流式调用失败 conversation_id=%s", conv.id)
                yield _sse("error", {"code": 50010, "message": "DeepSeek 超时"})
                return
            full = "".join(full_parts)
        assistant = Message(id=assistant_id, conversation_id=conv.id, role=MessageRole.assistant, content=full)
        db.add(assistant)
        if not uncovered:
            for rank, (item, _) in enumerate(citations_payload, start=1):
                db.add(
                    MessageCitation(
                        message_id=assistant_id,
                        chunk_id=item.chunk.id,
                        score=item.score,
                        rank=rank,
                    )
                )
        await db.commit()
        yield _sse("done", {"message_id": str(assistant_id), "prompt_tokens": 0, "completion_tokens": 0})

    if body.stream:
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    return await _collect_non_stream(event_stream, request, db, assistant_id)


async def _agent_completions(request, body, db, user, conv, kb_ids, assistant_id):
    """多步工具调用：先跑图，再把工具事件和最终答案推给前端。"""
    async def event_stream():
        yield _sse("meta", {"message_id": str(assistant_id)})
        try:
            result = await run_multi_agent(question=body.question, db=db, user=user, kb_ids=kb_ids)
        except Exception:
            logger.exception("Agent 调用失败 conversation_id=%s", conv.id)
            yield _sse("error", {"code": 50010, "message": "Agent / DeepSeek 调用失败"})
            return
        for ev in result.get("events") or []:
            yield _sse(ev.get("event") or "tool", ev.get("data") or {})
        answer = result.get("final_answer") or "未能生成答案。"
        for ch in answer:
            yield _sse("delta", {"text": ch})
        assistant = Message(id=assistant_id, conversation_id=conv.id, role=MessageRole.assistant, content=answer)
        db.add(assistant)
        for rank, cite in enumerate(result.get("citations") or [], start=1):
            try:
                db.add(
                    MessageCitation(
                        message_id=assistant_id,
                        chunk_id=UUID(str(cite["chunk_id"])),
                        score=float(cite.get("score") or 0),
                        rank=rank,
                    )
                )
            except (ValueError, TypeError, KeyError):
                logger.warning("跳过无效 citation=%s", cite, exc_info=True)
                continue
        await db.commit()
        yield _sse("done", {"message_id": str(assistant_id), "prompt_tokens": 0, "completion_tokens": 0})

    if body.stream:
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    return await _collect_non_stream(event_stream, request, db, assistant_id)


async def _collect_non_stream(event_stream, request, db, assistant_id):
    """非流式客户端：把 SSE 在服务端跑完，最后一次性返回完整助手消息。"""
    last_error: dict | None = None
    async for chunk in event_stream():
        if chunk.startswith("event: error"):
            last_error = {"raw": chunk}
    if last_error:
        logger.error("非流式聊天失败 assistant_id=%s payload=%s", assistant_id, last_error)
        raise AppError(50010, "模型调用失败", 502)
    assistant = await db.scalar(select(Message).where(Message.id == assistant_id))
    if assistant is None:
        raise AppError(50001, "内部错误", 500)
    from app.api.v1.conversations import _citations_for

    data = MessageDTO(
        id=assistant.id,
        role="assistant",
        content=assistant.content,
        citations=await _citations_for(db, assistant.id),
        created_at=assistant.created_at,
    ).model_dump(mode="json")
    return ok(request, data)
