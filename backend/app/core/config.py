"""
从 .env 读取配置。

改密码、数据库地址、DeepSeek Key 都写在项目根目录 .env 里，不要写进代码。
"""

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 固定读仓库根目录 .env，不依赖启动时的当前工作目录。
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """全部环境变量。名称必须和 .env 里的键一致。"""
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    APP_ENV: str = "dev"
    PROJECT_NAME: str = "enterprise-rag-agent"
    APP_SECRET_KEY: str = "change-me-to-32bytes-min-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DATABASE_URL: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    EMBEDDING_BACKEND: str = "sentence_transformers"
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-m3"
    RERANK_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"

    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_MB: int = 50

    WEATHER_API_KEY: str = ""
    ENABLE_READONLY_SQL_TOOL: bool = False

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost"
    INLINE_DOCUMENT_PIPELINE: bool = True
    AGENT_MAX_ITERATIONS: int = 10

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origin_list(self) -> list[str]:
        """把逗号分隔的前端地址拆成列表，给浏览器跨域白名单用。"""
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Alembic 迁移用同步驱动，把 asyncpg 换成 psycopg。"""
        return self.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg", 1)

    def assert_safe_for_env(self) -> None:
        """生产环境禁止继续用示例密钥和默认数据库口令。"""
        if self.APP_ENV == "prod" and self.APP_SECRET_KEY in {"", "change-me-to-32bytes-min-secret-key"}:
            raise RuntimeError("生产环境必须设置高强度 APP_SECRET_KEY")
        if self.APP_ENV == "prod" and "rag:rag@" in self.DATABASE_URL:
            raise RuntimeError("生产环境禁止使用默认数据库口令")


settings = Settings()
