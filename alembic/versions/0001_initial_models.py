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
    # создаём таблицу users
    op.create_table(
        'users',
        sa.Column('telegram_id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('fio', sa.String(length=255), nullable=False),
        sa.Column('specialization', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('invite_link', sa.String(length=512), nullable=False),
        sa.Column(
            'registered_at',
            sa.DateTime(),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False
        ),
    )


def downgrade() -> None:
    # при откате дропаем таблицу
    op.drop_table('users')
