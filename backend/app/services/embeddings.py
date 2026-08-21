"""
把文字变成一串数字（向量），才能在 Qdrant 里按「意思相近」搜索。
没装 sentence_transformers 时用哈希凑 1024 维，能跑但不准。
"""

import hashlib
import logging
import struct

from app.core.config import settings
from app.services.storage import l2_normalize

DIM = 1024
logger = logging.getLogger(__name__)


def _hash_vec(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw: list[float] = []
    seed = digest
    while len(raw) < DIM:
        seed = hashlib.sha256(seed).digest()
        for i in range(0, 32, 4):
            raw.append(struct.unpack(">i", seed[i : i + 4])[0] / 2**31)
    return l2_normalize(raw[:DIM])


class EmbeddingClient:
    def __init__(self) -> None:
        self.backend = settings.EMBEDDING_BACKEND

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.backend == "sentence_transformers":
            try:
                return await self._st(texts)
            except Exception:
                logger.warning("sentence_transformers 不可用，回退到 hash embedding", exc_info=True)
                return [_hash_vec(t) for t in texts]
        return [_hash_vec(t) for t in texts]

    async def _st(self, texts: list[str]) -> list[list[float]]:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        vectors = model.encode(texts, batch_size=32, normalize_embeddings=False)
        return [l2_normalize(v.tolist()) for v in vectors]
