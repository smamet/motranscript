"""Add default_lang to sources."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sources ADD COLUMN default_lang "
        "ENUM('kreol', 'fr', 'en', 'mix') NOT NULL DEFAULT 'mix'"
    )


def downgrade() -> None:
    op.drop_column("sources", "default_lang")
