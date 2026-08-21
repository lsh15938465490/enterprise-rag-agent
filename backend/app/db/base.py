"""SQLAlchemy 基类导出，给 Alembic 发现所有表。"""

from app.db.models import Base

__all__ = ["Base"]
