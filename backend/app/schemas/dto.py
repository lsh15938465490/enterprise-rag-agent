"""接口入参/出参的形状。Pydantic 会自动校验类型和长度，不合格直接 422。"""

from datetime import datetime
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

Role = Literal["super_admin", "tenant_admin", "kb_editor", "member"]
DocStatus = Literal["uploaded", "parsing", "parsed", "embedding", "ready", "failed"]
ConvMode = Literal["rag", "agent"]
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


class UserDTO(BaseModel):
    id: UUID
    tenant_id: UUID
    username: str
    email: str
    role: Role
    is_active: bool = True

    model_config = {"from_attributes": True}


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
    password: str = Field(min_length=8, max_length=128)
    role: Role

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if not PASSWORD_RE.match(value):
            raise ValueError("密码至少 8 位且包含字母和数字")
        return value


class UserPatchIn(BaseModel):
    is_active: bool | None = None
    role: Role | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str | None) -> str | None:
        if value is not None and not PASSWORD_RE.match(value):
            raise ValueError("密码至少 8 位且包含字母和数字")
        return value


class KnowledgeBaseCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


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
    """改标题或置顶。字段不传表示不改。"""
    title: str | None = Field(default=None, min_length=1, max_length=256)
    is_pinned: bool | None = None


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
    messages: list[MessageDTO] | None = None


class ChatIn(BaseModel):
    """提问请求。stream=true 时走 SSE。"""
    conversation_id: UUID
    question: str = Field(min_length=1, max_length=8000)
    stream: bool = True
