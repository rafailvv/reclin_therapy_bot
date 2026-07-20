"""Initial models

Revision ID: 0001_initial_models
Revises:
Create Date: 2025-07-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial_models'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # База уже существует, ничего не создаём
    pass


def downgrade() -> None:
    # И при откате — ничего не трогаем
    pass
