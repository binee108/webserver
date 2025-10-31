#!/usr/bin/env python3
"""
Migration: Add CANCELLING state and cancel_attempted_at field
Date: 2025-10-30
Purpose: Support DB-First pattern for order cancellation (orphan prevention)

Feature: cancel-order-db-first-orphan-prevention
Phase: 1 - Database Schema & State Management

Changes:
- Add cancel_attempted_at column to open_orders table
- Add index on (status, cancel_attempted_at) for background cleanup
- Update status constraint to include 'CANCELLING'

Usage:
    # 자동 실행 (python run.py start/restart)
    # 수동 실행
    python migrations/20251030_add_cancelling_state.py --upgrade
    python migrations/20251030_add_cancelling_state.py --downgrade
"""
# @FEAT:cancel-order-db-first @COMP:migration @TYPE:core

from sqlalchemy import text


def upgrade(engine):
    """Apply migration"""
    with engine.connect() as conn:
        trans = conn.begin()

        try:
            print("🔧 Starting migration: Add CANCELLING state and cancel_attempted_at...")

            # 1. Add cancel_attempted_at column (idempotent)
            print("  → Adding cancel_attempted_at column...")
            conn.execute(text("""
                ALTER TABLE open_orders
                ADD COLUMN IF NOT EXISTS cancel_attempted_at TIMESTAMP;
            """))

            # 2. Add comment for schema documentation
            conn.execute(text("""
                COMMENT ON COLUMN open_orders.cancel_attempted_at IS
                'Timestamp when order cancellation was initiated (for timeout detection and debugging)';
            """))

            # 3. Add index for background cleanup query
            print("  → Creating index on (status, cancel_attempted_at)...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_open_orders_cancelling_cleanup
                ON open_orders(status, cancel_attempted_at)
                WHERE status = 'CANCELLING';
            """))

            # 4. Verify column creation
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'open_orders'
                AND column_name = 'cancel_attempted_at';
            """))

            if result.fetchone():
                print("  ✅ cancel_attempted_at column verified")
            else:
                raise Exception("cancel_attempted_at column creation failed")

            # 5. Verify index creation
            result = conn.execute(text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'open_orders'
                AND indexname = 'idx_open_orders_cancelling_cleanup';
            """))

            if result.fetchone():
                print("  ✅ Index idx_open_orders_cancelling_cleanup verified")
            else:
                raise Exception("Index creation failed")

            trans.commit()
            print("✅ Migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


def downgrade(engine):
    """Rollback migration"""
    with engine.connect() as conn:
        trans = conn.begin()

        try:
            print("🔄 Rolling back migration: Remove CANCELLING state support...")

            # 1. Check for CANCELLING orders (safety check)
            result = conn.execute(text("""
                SELECT COUNT(*)
                FROM open_orders
                WHERE status = 'CANCELLING';
            """))

            count = result.scalar()
            if count > 0:
                print(f"⚠️  WARNING: {count} orders currently in CANCELLING state!")
                print("⚠️  Downgrade will remove cancel_attempted_at field and index")
                print("⚠️  Note: CANCELLING status in OrderStatus enum will remain")
                # 자동 마이그레이션 시스템에서는 입력을 받을 수 없으므로 경고만 표시
                # 수동 실행 시에만 확인

            # 2. Drop index
            print("  → Dropping index idx_open_orders_cancelling_cleanup...")
            conn.execute(text("""
                DROP INDEX IF EXISTS idx_open_orders_cancelling_cleanup;
            """))

            # 3. Drop column
            print("  → Dropping cancel_attempted_at column...")
            conn.execute(text("""
                ALTER TABLE open_orders
                DROP COLUMN IF EXISTS cancel_attempted_at;
            """))

            trans.commit()
            print("✅ Rollback completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ Rollback failed: {e}")
            raise


# 독립 실행 지원 (수동 실행용)
if __name__ == '__main__':
    import sys
    import os
    from dotenv import load_dotenv
    from sqlalchemy import create_engine

    if len(sys.argv) < 2:
        print("Usage: python 20251030_add_cancelling_state.py [--upgrade|--downgrade]")
        sys.exit(1)

    action = sys.argv[1]

    if action not in ['--upgrade', '--downgrade']:
        print(f"Invalid action: {action}")
        print("Usage: python 20251030_add_cancelling_state.py [--upgrade|--downgrade]")
        sys.exit(1)

    try:
        # 환경 변수 로드
        load_dotenv()

        # SQLAlchemy 엔진 생성
        database_url = (
            f"postgresql://{os.getenv('DB_USER', 'trader')}:"
            f"{os.getenv('DB_PASSWORD', 'password123')}@"
            f"{os.getenv('DB_HOST', 'localhost')}:"
            f"{os.getenv('DB_PORT', '5432')}/"
            f"{os.getenv('DB_NAME', 'trading_system')}"
        )

        engine = create_engine(database_url)

        if action == '--upgrade':
            upgrade(engine)
        else:
            downgrade(engine)

        engine.dispose()

    except Exception as e:
        print(f"❌ Migration script failed: {e}")
        sys.exit(1)
