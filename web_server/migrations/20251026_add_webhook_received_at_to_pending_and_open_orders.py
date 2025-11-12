"""
Add webhook_received_at column to PendingOrder and OpenOrder tables

Fixes: Infinite order loop bug caused by timestamp loss during PendingOrder ↔ OpenOrder transitions

Root Cause:
- PendingOrder created with created_at=T0 (webhook received)
- Rebalance converts to OpenOrder with created_at=T1 (conversion time, T0 lost!)
- Sorting by created_at causes order instability → infinite cancel/recreate loop

Solution:
- Add webhook_received_at column to preserve original webhook reception time
- Use webhook_received_at as primary sort key (not created_at)
- Add DB ID tie-breaker for deterministic ordering

Migration Strategy:
- Adds nullable column first (safe deployment)
- Backfills existing records (webhook_received_at = created_at)
- Sets NOT NULL constraint on PendingOrder after backfill
- OpenOrder remains nullable (supports non-webhook order creation paths)

Changed Files:
- models.py: PendingOrder.webhook_received_at (NOT NULL), OpenOrder.webhook_received_at (nullable)
- order_queue_manager.py: Pass webhook_received_at through enqueue/rebalance/move operations
- core.py: Extract webhook_received_at from timing_context
- order_manager.py: Pass webhook_received_at to create_open_order_record

Revision ID: 20251026_add_webhook_received_at
Created: 2025-10-26

@FEAT:order-tracking @COMP:migration @TYPE:core
"""
from sqlalchemy import text


def upgrade(engine):
    """Add webhook_received_at columns"""
    with engine.connect() as conn:
        # Check table existence
        result_pending = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'pending_orders'
            );
        """))
        result_open = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'open_orders'
            );
        """))

        if not result_pending.scalar() or not result_open.scalar():
            print('ℹ️  pending_orders or open_orders table not found. Skipping (initial install).')
            return

        # 1. pending_orders에 webhook_received_at 추가 (임시로 nullable)
        conn.execute(text("""
            ALTER TABLE pending_orders
            ADD COLUMN IF NOT EXISTS webhook_received_at TIMESTAMP
        """))

        # 2. open_orders에 webhook_received_at 추가 (nullable)
        conn.execute(text("""
            ALTER TABLE open_orders
            ADD COLUMN IF NOT EXISTS webhook_received_at TIMESTAMP
        """))

        # 3. 기존 레코드 backfill (created_at으로 초기화)
        conn.execute(text("""
            UPDATE pending_orders
            SET webhook_received_at = created_at
            WHERE webhook_received_at IS NULL
        """))

        conn.execute(text("""
            UPDATE open_orders
            SET webhook_received_at = created_at
            WHERE webhook_received_at IS NULL
        """))

        # 4. pending_orders.webhook_received_at을 NOT NULL로 변경
        conn.execute(text("""
            ALTER TABLE pending_orders
            ALTER COLUMN webhook_received_at SET NOT NULL
        """))

        conn.commit()
        print("✅ webhook_received_at columns added successfully")


def downgrade(engine):
    """Remove webhook_received_at columns"""
    with engine.connect() as conn:
        # 컬럼 제거
        conn.execute(text("""
            ALTER TABLE open_orders
            DROP COLUMN IF EXISTS webhook_received_at
        """))

        conn.execute(text("""
            ALTER TABLE pending_orders
            DROP COLUMN IF EXISTS webhook_received_at
        """))

        conn.commit()
        print("✅ webhook_received_at columns removed successfully")
