"""
把长文切成约 800 字一块，相邻块重叠 120 字，避免一句话被切断后搜不到。
query_lexemes：把用户问题切成中文词，给检索用。
"""

from dataclasses import dataclass
import logging

TARGET_SIZE = 800
OVERLAP = 120
MIN_SIZE = 50
logger = logging.getLogger(__name__)
_jieba_unavailable_logged = False


@dataclass
class ChunkDraft:
    content: str
    content_seg: str
    token_count: int
    page_number: int | None
    heading: str | None
    chunk_index: int


def _seg(text: str) -> str:
    try:
        import jieba

        return " ".join(jieba.cut(text))
    except Exception:
        global _jieba_unavailable_logged
        if not _jieba_unavailable_logged:
            logger.debug("jieba 不可用，使用原文作为分词", exc_info=True)
            _jieba_unavailable_logged = True
        return text


def query_lexemes(query: str) -> list[str]:
    text = (query or "").strip()
    if not text:
        return []
    try:
        import jieba

        raw = [t.strip() for t in jieba.lcut(text) if t.strip()]
    except Exception:
        raw = [text]
    out: list[str] = []
    for token in raw:
        if token in {"的", "了", "是", "和", "与", "及", "等", "在"}:
            continue
        if len(token) >= 2 or token.isascii():
            out.append(token)
    return out or [text]


def _cut_window(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + TARGET_SIZE, n)
        if end < n:
            window = text[start:end]
            split_at = max(window.rfind("\n\n"), window.rfind("。"))
            if split_at >= TARGET_SIZE // 3:
                end = start + split_at + 1
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= n:
            break
        start = max(end - OVERLAP, start + 1)
    return parts


def chunk_blocks(blocks: list[tuple[str, int | None, str | None]]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    idx = 0
    for content, page, heading in blocks:
        for piece in _cut_window(content):
            if len(piece) < MIN_SIZE:
                continue
            drafts.append(
                ChunkDraft(
                    content=piece,
                    content_seg=_seg(piece),
                    token_count=len(piece),
                    page_number=page,
                    heading=heading,
                    chunk_index=idx,
                )
            )
            idx += 1
    return drafts
