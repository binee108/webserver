"""
Add UNIQUE constraint to trades table for idempotency

Revision ID: 20251014_add_trade_unique_constraint
Create Date: 2025-10-14 16:00:00
Purpose: Prevent duplicate Trade records from race conditions

Background:
- WebSocket and Scheduler can process the same LIMIT order fill concurrently
- Application-level duplicate check has a race condition window (~50-200ms)
- Database-level UNIQUE constraint provides atomic duplicate prevention

Changes:
- Add UNIQUE constraint on (strategy_account_id, exchange_order_id)
- This ensures one Trade record per order per account
- IntegrityError will be raised on duplicate attempts (handled in application code)

Related Issue: #Critical-Issue-4 (Idempotency Not Guaranteed)
"""
import logging

logger = logging.getLogger(__name__)


def upgrade(connection):
    """Add UNIQUE constraint to trades table

    Args:
        connection: SQLAlchemy connection object
    """
    try:
        logger.info("🔧 Adding UNIQUE constraint to trades table...")

        # Check if constraint already exists (idempotent)
        check_sql = """
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name='trades'
          AND constraint_name='unique_order_per_account'
          AND constraint_type='UNIQUE';
        """

        result = connection.execute(check_sql)
        existing = result.fetchone()

        if existing:
            logger.info("✅ UNIQUE constraint 'unique_order_per_account' already exists, skipping")
            return

        # Add UNIQUE constraint
        alter_sql = """
        ALTER TABLE trades
        ADD CONSTRAINT unique_order_per_account
        UNIQUE (strategy_account_id, exchange_order_id);
        """

        connection.execute(alter_sql)
        logger.info("✅ Successfully added UNIQUE constraint 'unique_order_per_account'")

        # Verify constraint was added
        verify_result = connection.execute(check_sql)
        if not verify_result.fetchone():
            raise Exception("Constraint creation verification failed")

        logger.info("✅ Constraint verification passed")

    except Exception as e:
        logger.error(f"❌ Failed to add UNIQUE constraint: {e}", exc_info=True)
        raise


def downgrade(connection):
    """Remove UNIQUE constraint from trades table

    Args:
        connection: SQLAlchemy connection object
    """
    try:
        logger.info("🔧 Removing UNIQUE constraint from trades table...")

        # Check if constraint exists
        check_sql = """
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name='trades'
          AND constraint_name='unique_order_per_account'
          AND constraint_type='UNIQUE';
        """

        result = connection.execute(check_sql)
        existing = result.fetchone()

        if not existing:
            logger.info("✅ UNIQUE constraint 'unique_order_per_account' does not exist, skipping")
            return

        # Remove UNIQUE constraint
        drop_sql = """
        ALTER TABLE trades
        DROP CONSTRAINT IF EXISTS unique_order_per_account;
        """

        connection.execute(drop_sql)
        logger.info("✅ Successfully removed UNIQUE constraint 'unique_order_per_account'")

        # Verify constraint was removed
        verify_result = connection.execute(check_sql)
        if verify_result.fetchone():
            raise Exception("Constraint removal verification failed")

        logger.info("✅ Constraint removal verification passed")

    except Exception as e:
        logger.error(f"❌ Failed to remove UNIQUE constraint: {e}", exc_info=True)
        raise


def check_duplicate_trades(connection):
    """Check for existing duplicate trades before adding constraint

    This function helps identify data issues that would prevent constraint creation.

    Args:
        connection: SQLAlchemy connection object

    Returns:
        dict: {
            'has_duplicates': bool,
            'duplicate_count': int,
            'duplicates': list of (strategy_account_id, exchange_order_id, count)
        }
    """
    check_sql = """
    SELECT
        strategy_account_id,
        exchange_order_id,
        COUNT(*) as count
    FROM trades
    GROUP BY strategy_account_id, exchange_order_id
    HAVING COUNT(*) > 1
    ORDER BY count DESC
    LIMIT 10;
    """

    result = connection.execute(check_sql)
    duplicates = result.fetchall()

    return {
        'has_duplicates': len(duplicates) > 0,
        'duplicate_count': len(duplicates),
        'duplicates': [
            {
                'strategy_account_id': row[0],
                'exchange_order_id': row[1],
                'count': row[2]
            }
            for row in duplicates
        ]
    }


if __name__ == '__main__':
    """
    Standalone execution for manual migration

    Usage:
        python migrations/20251014_add_trade_unique_constraint.py
    """
    import sys
    import os

    # Add project root to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from app import create_app
    from app import db

    app = create_app()

    with app.app_context():
        connection = db.engine.connect()
        trans = connection.begin()

        try:
            # Check for duplicates first
            print("🔍 Checking for existing duplicate trades...")
            dup_info = check_duplicate_trades(connection)

            if dup_info['has_duplicates']:
                print(f"⚠️ Found {dup_info['duplicate_count']} duplicate trade groups:")
                for dup in dup_info['duplicates']:
                    print(f"   - strategy_account_id={dup['strategy_account_id']}, "
                          f"exchange_order_id={dup['exchange_order_id']}, "
                          f"count={dup['count']}")
                print("\n❌ Please clean up duplicate trades before adding UNIQUE constraint")
                print("   Cleanup SQL example:")
                print("""
                   DELETE FROM trades
                   WHERE id IN (
                       SELECT id
                       FROM (
                           SELECT id,
                                  ROW_NUMBER() OVER (
                                      PARTITION BY strategy_account_id, exchange_order_id
                                      ORDER BY timestamp
                                  ) as rn
                           FROM trades
                       ) t
                       WHERE t.rn > 1
                   );
                """)
                sys.exit(1)
            else:
                print("✅ No duplicate trades found, safe to add constraint")

            # Run migration
            print("\n🚀 Running upgrade migration...")
            upgrade(connection)

            trans.commit()
            print("\n✅ Migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            sys.exit(1)
        finally:
            connection.close()
