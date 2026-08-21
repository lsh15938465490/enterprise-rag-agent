"""Qdrant 向量库：建集合、写入切块向量、按向量搜索、按文档删除。"""

import logging
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client() -> AsyncQdrantClient:
    kwargs: dict = {"url": settings.QDRANT_URL, "timeout": 10, "check_compatibility": False}
    if settings.QDRANT_API_KEY:
        kwargs["api_key"] = settings.QDRANT_API_KEY
    return AsyncQdrantClient(**kwargs)


async def ensure_collection(name: str, dim: int = 1024) -> None:
    client = _client()
    try:
        exists = await client.collection_exists(name)
        if not exists:
            await client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
    except Exception:
        logger.warning("Qdrant 不可用，跳过 create_collection name=%s", name, exc_info=True)
    finally:
        await client.close()


async def upsert_points(collection: str, points: list[PointStruct]) -> None:
    if not points:
        return
    client = _client()
    try:
        await client.upsert(collection_name=collection, points=points)
    except Exception:
        logger.warning("Qdrant upsert 失败 collection=%s", collection)
        raise
    finally:
        await client.close()


async def search(
    collections: list[str],
    vector: list[float],
    tenant_id: UUID,
    kb_ids: list[UUID],
    top_k: int = 40,
) -> list[tuple[UUID, float]]:
    client = _client()
    results: list[tuple[UUID, float]] = []
    try:
        for name in collections:
            try:
                resp = await client.query_points(
                    collection_name=name,
                    query=vector,
                    limit=top_k,
                    query_filter=Filter(
                        must=[
                            FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id))),
                        ]
                    ),
                )
                hits = resp.points
            except UnexpectedResponse:
                logger.warning("Qdrant 检索集合不存在或响应异常 collection=%s", name)
                continue
            except Exception:
                logger.warning("Qdrant 检索失败 collection=%s", name, exc_info=True)
                continue
            for hit in hits:
                payload = hit.payload or {}
                kb = payload.get("knowledge_base_id")
                if kb_ids and str(kb) not in {str(x) for x in kb_ids}:
                    continue
                cid = payload.get("chunk_id")
                if cid:
                    results.append((UUID(str(cid)), float(hit.score)))
    finally:
        await client.close()
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


async def delete_by_document(collection: str, document_id: UUID) -> None:
    client = _client()
    try:
        await client.delete(
            collection_name=collection,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))])
            ),
        )
    except Exception:
        logger.warning("Qdrant 删除失败 document_id=%s", document_id, exc_info=True)
    finally:
        await client.close()
