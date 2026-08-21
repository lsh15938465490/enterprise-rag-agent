"""
Agent 大脑：模型每次只输出 JSON（retrieve / execute / finish），图最多循环 AGENT_MAX_ITERATIONS 轮。
制度类问题应先 retrieve，不要直接瞎编。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, TypedDict
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.db.models import User
from app.services.llm_deepseek import REACT_SYSTEM, complete_chat
from app.services.rag_pipeline import retrieve
from app.tools.registry import run_tool

logger = logging.getLogger(__name__)

ActionName = Literal["retrieve", "execute", "finish"]


class AgentState(TypedDict, total=False):
    question: str
    scratchpad: str
    iteration: int
    action: ActionName
    action_input: dict[str, Any]
    thought: str
    final_answer: str
    citations: list[dict[str, Any]]
    events: list[dict[str, Any]]


JSON_RE = re.compile(r"\{.*\}", re.S)


def _parse_plan(raw: str) -> dict[str, Any]:
    text = raw.strip()
    match = JSON_RE.search(text)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Agent 计划 JSON 解析失败 raw=%s", raw[:300])
        return {"thought": raw[:200], "action": "retrieve", "action_input": {"query": ""}}
    action = data.get("action") or "retrieve"
    if action not in {"retrieve", "execute", "finish"}:
        action = "retrieve"
    inp = data.get("action_input") or {}
    if not isinstance(inp, dict):
        inp = {"query": str(inp)}
    return {"thought": str(data.get("thought") or ""), "action": action, "action_input": inp}


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return (config or {}).get("configurable") or {}


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    iteration = int(state.get("iteration") or 0)
    events = list(state.get("events") or [])
    if iteration >= settings.AGENT_MAX_ITERATIONS:
        events.append({"event": "tool", "data": {"name": "supervisor", "status": "done", "content": "达到最大迭代 10 轮，停止"}})
        return {
            "iteration": iteration,
            "action": "finish",
            "final_answer": state.get("final_answer") or "已达到最大推理轮次，请简化问题后重试。",
            "events": events,
        }
    question = state["question"]
    scratch = state.get("scratchpad") or "（尚无观察）"
    raw = await complete_chat(
        [
            {"role": "system", "content": REACT_SYSTEM},
            {
                "role": "user",
                "content": f"问题：{question}\n\n已有过程：\n{scratch}\n\n当前轮次：{iteration + 1}/{settings.AGENT_MAX_ITERATIONS}",
            },
        ],
        temperature=0.2,
    )
    plan = _parse_plan(raw)
    events.append(
        {
            "event": "tool",
            "data": {
                "name": "react_supervisor",
                "status": "done",
                "content": f"Thought: {plan['thought']}; Action: {plan['action']}",
            },
        }
    )
    patch: dict[str, Any] = {
        "iteration": iteration + 1,
        "thought": plan["thought"],
        "action": plan["action"],
        "action_input": plan["action_input"],
        "events": events,
        "scratchpad": scratch + f"\nThought: {plan['thought']}\nAction: {plan['action']}",
    }
    if plan["action"] == "finish":
        patch["final_answer"] = str(plan["action_input"].get("answer") or plan["thought"] or "已完成。")
    return patch


async def retrieve_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    cfg = _cfg(config)
    db = cfg["db"]
    user: User = cfg["user"]
    kb_ids: list[UUID] = cfg["kb_ids"]
    query = str((state.get("action_input") or {}).get("query") or state["question"])
    events = list(state.get("events") or [])
    events.append({"event": "tool", "data": {"name": "retrieve_agent", "status": "running", "content": query}})
    hits = await retrieve(db, user.tenant_id, kb_ids, query)
    citations = []
    lines = []
    for i, item in enumerate(hits, start=1):
        payload = {
            "chunk_id": str(item.chunk.id),
            "document_id": str(item.chunk.document_id),
            "filename": item.filename,
            "page_number": item.chunk.page_number,
            "heading": item.chunk.heading,
            "score": item.score,
            "snippet": item.chunk.content[:240],
        }
        citations.append(payload)
        events.append({"event": "citation", "data": payload})
        lines.append(f"[S{i}] {item.filename} {item.chunk.content[:400]}")
    observation = "\n".join(lines) if lines else "知识库无命中"
    events.append({"event": "tool", "data": {"name": "retrieve_agent", "status": "done", "content": observation[:500]}})
    scratch = (state.get("scratchpad") or "") + f"\nObservation(retrieve): {observation[:1500]}"
    return {"events": events, "citations": citations, "scratchpad": scratch}


async def execute_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    cfg = _cfg(config)
    db = cfg["db"]
    user: User = cfg["user"]
    inp = state.get("action_input") or {}
    name = str(inp.get("tool") or "")
    events = list(state.get("events") or [])
    events.append({"event": "tool", "data": {"name": name or "execute_agent", "status": "running", "content": json.dumps(inp, ensure_ascii=False)}})
    result = await run_tool(name=name, args=inp, db=db, tenant_id=user.tenant_id, user=user)
    events.append({"event": "tool", "data": {"name": name or "execute_agent", "status": "done", "content": result}})
    scratch = (state.get("scratchpad") or "") + f"\nObservation({name}): {result}"
    return {"events": events, "scratchpad": scratch}


def route_supervisor(state: AgentState) -> str:
    return state.get("action") or "finish"


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("execute", execute_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {"retrieve": "retrieve", "execute": "execute", "finish": END},
    )
    graph.add_edge("retrieve", "supervisor")
    graph.add_edge("execute", "supervisor")
    return graph.compile()


agent_graph = build_agent_graph()


async def run_multi_agent(*, question: str, db, user: User, kb_ids: list[UUID]) -> AgentState:
    initial: AgentState = {
        "question": question,
        "scratchpad": "",
        "iteration": 0,
        "action": "retrieve",
        "action_input": {},
        "final_answer": "",
        "citations": [],
        "events": [],
    }
    result = await agent_graph.ainvoke(
        initial,
        config={
            "recursion_limit": settings.AGENT_MAX_ITERATIONS * 2 + 2,
            "configurable": {"db": db, "user": user, "kb_ids": kb_ids},
        },
    )
    return result
