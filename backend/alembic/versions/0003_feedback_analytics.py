"""会话置顶之后：点赞点踩表、行为埋点表、反馈枚举。

Revision ID: 0003_feedback_analytics
Revises: 0002_conv_pin
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_feedback_analytics"
down_revision: Union[str, None] = "0002_conv_pin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE feedback_rating AS ENUM ('like', 'dislike');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;

        CREATE TABLE IF NOT EXISTS message_feedbacks (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            message_id      UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            rating          feedback_rating NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (message_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS analytics_events (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID,
            user_id         UUID,
            event_type      VARCHAR(64) NOT NULL,
            resource_type   VARCHAR(64),
            resource_id     UUID,
            extra           JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_analytics_tenant_time
            ON analytics_events (tenant_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS ix_analytics_type ON analytics_events (event_type);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS analytics_events;
        DROP TABLE IF EXISTS message_feedbacks;
        DROP TYPE IF EXISTS feedback_rating;
    """)
