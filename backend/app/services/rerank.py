"""交叉编码器精排。模型没装时退回融合分，保证系统还能回答。"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def rerank(query: str, candidates: list[tuple[object, str, float]], top_n: int = 8) -> list[tuple[object, float]]:
    """对候选段落打「和问题有多相关」的分，只留最相关的几条给大模型。"""
    if not candidates:
        return []
    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(settings.RERANK_MODEL_NAME)
        pairs = [(query, text) for _, text, _ in candidates]
        scores = model.predict(pairs)
        ranked = sorted(
            [(cand[0], float(score)) for cand, score in zip(candidates, scores, strict=False)],
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:top_n]
    except Exception:
        logger.warning("Rerank 模型不可用，回退到融合分", exc_info=True)
        return [(cid, score) for cid, _, score in candidates[:top_n]]
