"""Add users table with default admin.

Revision ID: 006
Revises: 005
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import bcrypt
import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "operator", name="userrole"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    password_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode("utf-8")
    op.execute(
        sa.text(
            "INSERT INTO users (email, password_hash, role, is_active) "
            "VALUES (:email, :password_hash, :role, :is_active)"
        ).bindparams(
            email="admin@example.com",
            password_hash=password_hash,
            role="admin",
            is_active=True,
        )
    )


def downgrade() -> None:
    op.drop_table("users")
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
