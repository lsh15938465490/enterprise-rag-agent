"""RRF：把「向量排名」和「关键词排名」合成一个分数，两边都排前面的段落更靠前。"""

from collections import defaultdict
from uuid import UUID


def rrf(
    dense: list[tuple[UUID, float]],
    sparse: list[tuple[UUID, float]],
    k: int = 60,
) -> list[tuple[UUID, float]]:
    scores: dict[UUID, float] = defaultdict(float)
    for rank, (chunk_id, _) in enumerate(dense, start=1):
        scores[chunk_id] += 1.0 / (k + rank)
    for rank, (chunk_id, _) in enumerate(sparse, start=1):
        scores[chunk_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
