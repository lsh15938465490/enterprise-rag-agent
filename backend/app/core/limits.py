"""资源数量上限。数值来自 .env / 配置，业务代码只读 settings，不必改常量。"""

from app.core.config import settings

SUPER_ADMIN_USERNAME = "adminliu"


def max_conversations_per_user() -> int:
    return settings.MAX_CONVERSATIONS_PER_USER


def max_knowledge_bases_per_tenant() -> int:
    return settings.MAX_KNOWLEDGE_BASES_PER_TENANT


def max_documents_per_kb() -> int:
    return settings.MAX_DOCUMENTS_PER_KB


# 兼容旧引用名（默认值与配置一致，测试或未热更新场景仍以 settings 为准）
MAX_CONVERSATIONS_PER_USER = settings.MAX_CONVERSATIONS_PER_USER
MAX_KNOWLEDGE_BASES_PER_TENANT = settings.MAX_KNOWLEDGE_BASES_PER_TENANT
MAX_DOCUMENTS_PER_KB = settings.MAX_DOCUMENTS_PER_KB
