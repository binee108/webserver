"""
Add processing lock columns to open_orders table (Phase 2: Optimistic Locking)

Revision ID: 20251014_add_processing_lock
Create Date: 2025-10-14

Purpose:
- 낙관적 잠금(optimistic locking)으로 WebSocket과 Scheduler의 동시 처리 방지
- 프로세스 크래시 시 영구적으로 잠긴 주문 자동 복구 메커니즘

Changes:
- open_orders.is_processing: Boolean (기본값 FALSE) - 처리 중 플래그
- open_orders.processing_started_at: DateTime (nullable) - 처리 시작 시각
- 인덱스 추가: 빠른 조회를 위한 is_processing, processing_started_at 인덱스

@FEAT:order-tracking @COMP:migration @TYPE:core
"""
from sqlalchemy import text


def upgrade(engine):
    """Add is_processing and processing_started_at columns"""
    with engine.connect() as conn:
        # 1. is_processing 컬럼 추가 (기본값: FALSE)
        conn.execute(text("""
            ALTER TABLE open_orders
            ADD COLUMN IF NOT EXISTS is_processing BOOLEAN NOT NULL DEFAULT FALSE
        """))

        # 2. processing_started_at 컬럼 추가 (nullable)
        conn.execute(text("""
            ALTER TABLE open_orders
            ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP
        """))

        # 3. 인덱스 생성 (빠른 조회)
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_open_orders_processing
            ON open_orders (is_processing)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_open_orders_processing_started
            ON open_orders (processing_started_at)
        """))

        conn.commit()
        print("✅ Processing lock columns added successfully")


def downgrade(engine):
    """Remove processing lock columns"""
    with engine.connect() as conn:
        # 인덱스 제거
        conn.execute(text("""
            DROP INDEX IF EXISTS idx_open_orders_processing_started
        """))

        conn.execute(text("""
            DROP INDEX IF EXISTS idx_open_orders_processing
        """))

        # 컬럼 제거
        conn.execute(text("""
            ALTER TABLE open_orders
            DROP COLUMN IF EXISTS processing_started_at
        """))

        conn.execute(text("""
            ALTER TABLE open_orders
            DROP COLUMN IF EXISTS is_processing
        """))

        conn.commit()
        print("✅ Processing lock columns removed successfully")
