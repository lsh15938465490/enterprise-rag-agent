"""登录历史表。

Revision ID: 0004_login_histories
Revises: 0003_feedback_analytics
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_login_histories"
down_revision: Union[str, None] = "0003_feedback_analytics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS login_histories (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_name VARCHAR(128) NOT NULL DEFAULT '未知设备',
            user_agent  VARCHAR(512),
            logged_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_login_histories_user_time
            ON login_histories (user_id, logged_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS login_histories;")
