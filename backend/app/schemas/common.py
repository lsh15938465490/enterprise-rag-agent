"""和前端约定的信封、健康检查字段（OpenAPI 文档也会用到）。"""

from typing import Any

from pydantic import BaseModel, Field


class Envelope(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None
    request_id: str = "-"


class HealthData(BaseModel):
    status: str
    postgres: bool
    qdrant: bool
    redis: bool
