"""超级管理员可无部门；登录历史 tenant_id 可空。

Revision ID: 0005_platform_super_admin
Revises: 0004_login_histories
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_platform_super_admin"
down_revision: Union[str, None] = "0004_login_histories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN tenant_id DROP NOT NULL;")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_platform_username
        ON users (username) WHERE tenant_id IS NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_platform_email
        ON users (email) WHERE tenant_id IS NULL;
    """)
    op.execute("ALTER TABLE login_histories ALTER COLUMN tenant_id DROP NOT NULL;")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_users_platform_email;")
    op.execute("DROP INDEX IF EXISTS ux_users_platform_username;")
    op.execute("ALTER TABLE login_histories ALTER COLUMN tenant_id SET NOT NULL;")
    op.execute("ALTER TABLE users ALTER COLUMN tenant_id SET NOT NULL;")
