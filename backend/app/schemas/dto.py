"""接口入参/出参的形状。Pydantic 会自动校验类型和长度，不合格直接 422。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

Role = Literal["super_admin", "tenant_admin", "kb_editor", "member"]
DocStatus = Literal["uploaded", "parsing", "parsed", "embedding", "ready", "failed"]
ConvMode = Literal["rag", "agent"]


class UserDTO(BaseModel):
    id: UUID
    tenant_id: UUID | None = None
    username: str
    email: str
    role: Role
    is_active: bool = True
    tenant_slug: str | None = None
    tenant_name: str | None = None

    model_config = {"from_attributes": True}


class LoginRecordDTO(BaseModel):
    logged_at: str
    device_name: str


class UserListDTO(UserDTO):
    last_login_at: str | None = None
    login_count: int = 0
    logins: list[LoginRecordDTO] = []


class LoginIn(BaseModel):
    """登录请求体。"""
    tenant_slug: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=4096)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserDTO


class UserCreateIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    role: Role
    tenant_id: UUID | None = None


class UserPatchIn(BaseModel):
    is_active: bool | None = None
    role: Role | None = None
    password: str | None = Field(default=None, min_length=1, max_length=128)


class KnowledgeBaseCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    tenant_id: UUID | None = None


class KnowledgeBasePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class KnowledgeBaseDTO(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    embedding_model: str
    embedding_dim: int
    qdrant_collection: str
    is_active: bool
    created_by: UUID
    created_at: datetime
    tenant_slug: str | None = None
    tenant_name: str | None = None

    model_config = {"from_attributes": True}


class AclItemIn(BaseModel):
    user_id: UUID
    can_read: bool = True
    can_write: bool = False


class AclPutIn(BaseModel):
    items: list[AclItemIn] = Field(max_length=500)


class DocumentDTO(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    filename: str
    content_type: str
    file_size: int
    status: DocStatus
    error_message: str | None
    page_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreateIn(BaseModel):
    """新建会话：必须选知识库，id 不能重复。"""
    mode: ConvMode = "rag"
    knowledge_base_ids: list[UUID] = Field(min_length=1, max_length=20)
    title: str | None = Field(default=None, max_length=256)

    @field_validator("knowledge_base_ids")
    @classmethod
    def unique_kb_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("knowledge_base_ids 不能重复")
        return value


class ConversationPatchIn(BaseModel):
    """改标题、置顶或绑定知识库。字段不传表示不改。"""
    title: str | None = Field(default=None, min_length=1, max_length=256)
    is_pinned: bool | None = None
    knowledge_base_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("knowledge_base_ids")
    @classmethod
    def unique_kb_ids(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("knowledge_base_ids 不能重复")
        return value


class CitationDTO(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int | None
    heading: str | None
    score: float
    snippet: str


class MessageDTO(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    citations: list[CitationDTO] = []
    created_at: datetime


class ConversationDTO(BaseModel):
    id: UUID
    title: str
    mode: ConvMode
    knowledge_base_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
    is_pinned: bool = False
    owner_username: str = ""
    owner_kind: str = "普通用户"
    tenant_slug: str | None = None
    tenant_name: str | None = None
    messages: list[MessageDTO] | None = None


class ChatIn(BaseModel):
    """提问请求。stream=true 时走 SSE。"""
    conversation_id: UUID
    question: str = Field(min_length=1, max_length=8000)
    stream: bool = True


class GenerateDocumentIn(BaseModel):
    knowledge_base_id: UUID
    title: str = Field(min_length=1, max_length=200)
    requirements: str = Field(min_length=1, max_length=8000)
    stream: bool = True


class SaveGeneratedDocumentIn(BaseModel):
    knowledge_base_id: UUID
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200000)


class FeedbackIn(BaseModel):
    """点赞 like / 点踩 dislike；传 null 表示清除。"""
    rating: Literal["like", "dislike"] | None = None


class AnalyticsEventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    resource_type: str | None = Field(default=None, max_length=64)
    resource_id: UUID | None = None
    extra: dict | None = None
