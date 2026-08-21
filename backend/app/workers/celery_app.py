"""后台任务队列。文档多、解析慢时用 Celery worker，而不是卡在网页请求里。"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "enterprise_rag",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.task_routes = {
    "app.workers.tasks.parse_document": {"queue": "parse"},
    "app.workers.tasks.embed_document": {"queue": "embed"},
}


@celery_app.task(name="app.workers.tasks.parse_document")
def parse_document(document_id: str) -> None:
    import asyncio

    from app.services.document_pipeline import process_document

    asyncio.run(process_document(__import__("uuid").UUID(document_id)))
