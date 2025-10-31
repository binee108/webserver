"""Add cancel_queue and strategy_order_logs tables

Revision ID: d35d6b140919
Revises: 
Create Date: 2025-10-31 20:34:52.329987

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd35d6b140919'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create cancel_queue table
    op.create_table(
        'cancel_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['open_orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        op.f('ix_cancel_queue_status'),
        'cancel_queue',
        ['status'],
        unique=False
    )
    op.create_index(
        op.f('ix_cancel_queue_next_retry_at'),
        'cancel_queue',
        ['next_retry_at'],
        unique=False
    )

    # Create strategy_order_logs table
    op.create_table(
        'strategy_order_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column('execution_results', sa.JSON(), nullable=False),
        sa.Column('total_accounts', sa.Integer(), nullable=False),
        sa.Column('successful_accounts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_accounts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PROCESSING'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        op.f('ix_strategy_order_logs_strategy_id'),
        'strategy_order_logs',
        ['strategy_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_strategy_order_logs_status'),
        'strategy_order_logs',
        ['status'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop strategy_order_logs table
    op.drop_index(op.f('ix_strategy_order_logs_status'), table_name='strategy_order_logs')
    op.drop_index(op.f('ix_strategy_order_logs_strategy_id'), table_name='strategy_order_logs')
    op.drop_table('strategy_order_logs')

    # Drop cancel_queue table
    op.drop_index(op.f('ix_cancel_queue_next_retry_at'), table_name='cancel_queue')
    op.drop_index(op.f('ix_cancel_queue_status'), table_name='cancel_queue')
    op.drop_table('cancel_queue')
