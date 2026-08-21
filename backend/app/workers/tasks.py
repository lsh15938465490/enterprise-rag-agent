"""对外导出 Celery 任务名，方便 worker 启动时加载。"""

from app.workers.celery_app import celery_app, parse_document

__all__ = ["celery_app", "parse_document"]
