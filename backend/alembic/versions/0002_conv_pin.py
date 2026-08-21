"""会话置顶：is_pinned / pinned_at。

Revision ID: 0002_conv_pin
Revises: 0001_initial
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_conv_pin"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE conversations
            ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMPTZ;
        CREATE INDEX IF NOT EXISTS ix_conv_user_pin
            ON conversations (user_id, is_pinned, pinned_at DESC NULLS LAST, updated_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_conv_user_pin")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS pinned_at")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS is_pinned")
