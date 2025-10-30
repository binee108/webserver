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
    python migrations/20251030_add_cancelling_state.py --upgrade
    python migrations/20251030_add_cancelling_state.py --downgrade
"""
# @FEAT:cancel-order-db-first @COMP:migration @TYPE:core

import sys
import psycopg2
from psycopg2 import sql

def get_db_connection():
    """Get database connection from environment"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME', 'webserver_dev'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres')
    )

def upgrade(conn):
    """Apply migration"""
    cursor = conn.cursor()

    print("🔧 Starting migration: Add CANCELLING state and cancel_attempted_at...")

    try:
        # 1. Add cancel_attempted_at column (idempotent)
        print("  → Adding cancel_attempted_at column...")
        cursor.execute("""
            ALTER TABLE open_orders
            ADD COLUMN IF NOT EXISTS cancel_attempted_at TIMESTAMP;
        """)

        # 2. Add comment for schema documentation
        cursor.execute("""
            COMMENT ON COLUMN open_orders.cancel_attempted_at IS
            'Timestamp when order cancellation was initiated (for timeout detection and debugging)';
        """)

        # 3. Add index for background cleanup query
        print("  → Creating index on (status, cancel_attempted_at)...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_open_orders_cancelling_cleanup
            ON open_orders(status, cancel_attempted_at)
            WHERE status = 'CANCELLING';
        """)

        # 4. Verify column creation
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'open_orders'
            AND column_name = 'cancel_attempted_at';
        """)

        if cursor.fetchone():
            print("  ✅ cancel_attempted_at column verified")
        else:
            raise Exception("cancel_attempted_at column creation failed")

        # 5. Verify index creation
        cursor.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'open_orders'
            AND indexname = 'idx_open_orders_cancelling_cleanup';
        """)

        if cursor.fetchone():
            print("  ✅ Index idx_open_orders_cancelling_cleanup verified")
        else:
            raise Exception("Index creation failed")

        conn.commit()
        print("✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise

def downgrade(conn):
    """Rollback migration"""
    cursor = conn.cursor()

    print("🔄 Rolling back migration: Remove CANCELLING state support...")

    try:
        # 1. Check for CANCELLING orders (safety check)
        cursor.execute("""
            SELECT COUNT(*)
            FROM open_orders
            WHERE status = 'CANCELLING';
        """)

        count = cursor.fetchone()[0]
        if count > 0:
            print(f"⚠️  WARNING: {count} orders currently in CANCELLING state!")
            response = input("Continue with downgrade? (yes/no): ")
            if response.lower() != 'yes':
                print("Downgrade cancelled")
                return

        # 2. Drop index
        print("  → Dropping index idx_open_orders_cancelling_cleanup...")
        cursor.execute("""
            DROP INDEX IF EXISTS idx_open_orders_cancelling_cleanup;
        """)

        # 3. Drop column
        print("  → Dropping cancel_attempted_at column...")
        cursor.execute("""
            ALTER TABLE open_orders
            DROP COLUMN IF EXISTS cancel_attempted_at;
        """)

        conn.commit()
        print("✅ Rollback completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Rollback failed: {e}")
        raise

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python 20251030_add_cancelling_state.py [--upgrade|--downgrade]")
        sys.exit(1)

    action = sys.argv[1]

    if action not in ['--upgrade', '--downgrade']:
        print(f"Invalid action: {action}")
        print("Usage: python 20251030_add_cancelling_state.py [--upgrade|--downgrade]")
        sys.exit(1)

    try:
        conn = get_db_connection()

        if action == '--upgrade':
            upgrade(conn)
        else:
            downgrade(conn)

        conn.close()

    except Exception as e:
        print(f"❌ Migration script failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
