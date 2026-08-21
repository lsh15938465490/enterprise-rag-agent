"""第一版数据库结构：租户、用户、知识库、文档切块、会话消息、审计日志，以及中文全文检索触发器。"""

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""
        CREATE TYPE user_role AS ENUM ('super_admin', 'tenant_admin', 'kb_editor', 'member');
        CREATE TYPE doc_status AS ENUM ('uploaded', 'parsing', 'parsed', 'embedding', 'ready', 'failed');
        CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');
        CREATE TYPE conversation_mode AS ENUM ('rag', 'agent');
    """)
    op.execute("""
        CREATE TABLE tenants (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR(128) NOT NULL,
            slug            VARCHAR(64) NOT NULL UNIQUE,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            username        VARCHAR(64) NOT NULL,
            email           VARCHAR(255) NOT NULL,
            password_hash   VARCHAR(255) NOT NULL,
            role            user_role NOT NULL DEFAULT 'member',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, username),
            UNIQUE (tenant_id, email)
        );
        CREATE INDEX ix_users_tenant ON users(tenant_id);

        CREATE TABLE knowledge_bases (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            name            VARCHAR(128) NOT NULL,
            description     TEXT,
            embedding_model VARCHAR(128) NOT NULL DEFAULT 'bge-m3',
            embedding_dim   INT NOT NULL DEFAULT 1024,
            qdrant_collection VARCHAR(128) NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_by      UUID NOT NULL REFERENCES users(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, name),
            UNIQUE (qdrant_collection)
        );

        CREATE TABLE knowledge_base_acl (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            can_read        BOOLEAN NOT NULL DEFAULT TRUE,
            can_write       BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE (knowledge_base_id, user_id)
        );

        CREATE TABLE documents (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            uploaded_by     UUID NOT NULL REFERENCES users(id),
            filename        VARCHAR(512) NOT NULL,
            content_type    VARCHAR(128) NOT NULL,
            file_size       BIGINT NOT NULL,
            storage_key     VARCHAR(1024) NOT NULL,
            status          doc_status NOT NULL DEFAULT 'uploaded',
            error_message   TEXT,
            page_count      INT,
            checksum_sha256 CHAR(64),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_docs_kb_status ON documents(knowledge_base_id, status);

        CREATE TABLE chunks (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            chunk_index     INT NOT NULL,
            content         TEXT NOT NULL,
            content_seg     TEXT,
            token_count     INT NOT NULL,
            page_number     INT,
            heading         VARCHAR(512),
            search_tsv      TSVECTOR,
            qdrant_point_id UUID NOT NULL,
            UNIQUE (document_id, chunk_index)
        );
        CREATE INDEX ix_chunks_tsv ON chunks USING GIN (search_tsv);
        CREATE INDEX ix_chunks_kb ON chunks(knowledge_base_id);

        CREATE TABLE conversations (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            user_id         UUID NOT NULL REFERENCES users(id),
            title           VARCHAR(256) NOT NULL DEFAULT '新对话',
            mode            conversation_mode NOT NULL DEFAULT 'rag',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_conv_user ON conversations(user_id, updated_at DESC);

        CREATE TABLE conversation_knowledge_bases (
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            PRIMARY KEY (conversation_id, knowledge_base_id)
        );

        CREATE TABLE messages (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            message_role NOT NULL,
            content         TEXT NOT NULL DEFAULT '',
            tool_name       VARCHAR(64),
            tool_call_id    VARCHAR(128),
            token_usage     JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_msg_conv ON messages(conversation_id, created_at);

        CREATE TABLE message_citations (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id      UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            chunk_id        UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            score           DOUBLE PRECISION NOT NULL,
            rank            INT NOT NULL
        );

        CREATE TABLE audit_logs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID,
            user_id         UUID,
            action          VARCHAR(64) NOT NULL,
            resource_type   VARCHAR(64) NOT NULL,
            resource_id     UUID,
            ip              INET,
            extra           JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_audit_tenant_time ON audit_logs(tenant_id, created_at DESC);
    """)
    op.execute("""
        CREATE FUNCTION chunks_tsv_trigger() RETURNS trigger AS $$
        BEGIN
          NEW.search_tsv := to_tsvector('simple', coalesce(NEW.content_seg, NEW.content, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_chunks_tsv BEFORE INSERT OR UPDATE OF content, content_seg ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_tsv_trigger();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsv_trigger")
    op.execute("""
        DROP TABLE IF EXISTS audit_logs;
        DROP TABLE IF EXISTS message_citations;
        DROP TABLE IF EXISTS messages;
        DROP TABLE IF EXISTS conversation_knowledge_bases;
        DROP TABLE IF EXISTS conversations;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS documents;
        DROP TABLE IF EXISTS knowledge_base_acl;
        DROP TABLE IF EXISTS knowledge_bases;
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS tenants;
        DROP TYPE IF EXISTS conversation_mode;
        DROP TYPE IF EXISTS message_role;
        DROP TYPE IF EXISTS doc_status;
        DROP TYPE IF EXISTS user_role;
    """)
