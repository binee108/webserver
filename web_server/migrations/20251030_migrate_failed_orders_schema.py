"""
Migrate FailedOrder schema to Phase 1-3 design

@FEAT:immediate-order-execution @COMP:migration @TYPE:core

이 마이그레이션은 failed_orders 테이블을 Phase 1-3 설계에 맞게 변경합니다:
- 기존 order_payload JSON에서 개별 컬럼으로 주문 정보 추출 (quantity, price, stop_price)
- 컬럼명 정규화 (failure_reason → reason, error_message → exchange_error)
- 불필요한 구 컬럼 제거 (user_id, account_id, pending_order_id 등)
- 기존 데이터 보존 (있다면)

Revision ID: 20251030_failed_orders
Revises: 20251008_create_order_queue_tables
Create Date: 2025-10-30
"""

from sqlalchemy import text
import json


def upgrade(engine):
    """Upgrade database schema to Phase 1-3 design"""

    conn = engine.connect()
    trans = conn.begin()

    try:
        print("🔄 Step 1: 신규 컬럼 추가 (nullable=True)")

        # 1. Add new columns (all nullable initially for safe migration)
        conn.execute(text("""
            ALTER TABLE failed_orders
            ADD COLUMN IF NOT EXISTS quantity NUMERIC(20, 8),
            ADD COLUMN IF NOT EXISTS price NUMERIC(20, 8),
            ADD COLUMN IF NOT EXISTS stop_price NUMERIC(20, 8),
            ADD COLUMN IF NOT EXISTS reason VARCHAR(100),
            ADD COLUMN IF NOT EXISTS exchange_error TEXT,
            ADD COLUMN IF NOT EXISTS status VARCHAR(20),
            ADD COLUMN IF NOT EXISTS webhook_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS order_params JSON
        """))

        print("✅ Step 1 완료")
        print("\n🔄 Step 2: 기존 데이터 마이그레이션")

        # 2. Migrate existing data
        # Fetch all existing records
        result = conn.execute(text("""
            SELECT id, order_payload, failure_reason, error_message, recovery_status
            FROM failed_orders
        """))

        failed_orders = result.fetchall()
        print(f"📦 마이그레이션 대상: {len(failed_orders)}개 레코드")

        for fo in failed_orders:
            fo_id = fo[0]
            order_payload = fo[1]
            failure_reason = fo[2]
            error_message = fo[3]
            recovery_status = fo[4]

            # Parse order_payload JSON
            payload = {}
            if order_payload:
                if isinstance(order_payload, str):
                    try:
                        payload = json.loads(order_payload)
                    except json.JSONDecodeError:
                        print(f"⚠️ ID {fo_id}: JSON 파싱 실패, 빈 딕셔너리 사용")
                        payload = {}
                elif isinstance(order_payload, dict):
                    payload = order_payload

            # Extract order parameters from JSON
            # Handle both direct fields and nested structures
            quantity = payload.get('quantity') or payload.get('qty') or 0
            price = payload.get('price')
            stop_price = payload.get('stopPrice') or payload.get('stop_price')

            # Map old columns to new ones
            reason = failure_reason or '알 수 없는 오류'
            exchange_error_val = error_message
            status = recovery_status or 'pending_retry'

            # Copy order_payload to order_params (rename)
            order_params_val = order_payload if order_payload else None

            # Update record
            conn.execute(text("""
                UPDATE failed_orders
                SET quantity = :quantity,
                    price = :price,
                    stop_price = :stop_price,
                    reason = :reason,
                    exchange_error = :exchange_error,
                    status = :status,
                    order_params = :order_params
                WHERE id = :id
            """), {
                'id': fo_id,
                'quantity': quantity,
                'price': price,
                'stop_price': stop_price,
                'reason': reason,
                'exchange_error': exchange_error_val,
                'status': status,
                'order_params': json.dumps(payload) if payload else None
            })

            print(f"  ✅ ID {fo_id}: quantity={quantity}, price={price}, status={status}")

        print("✅ Step 2 완료")
        print("\n🔄 Step 3: NOT NULL 제약조건 추가 (필수 컬럼만)")

        # 3. Add NOT NULL constraints for required fields
        # symbol, side, order_type are already NOT NULL
        conn.execute(text("""
            ALTER TABLE failed_orders
            ALTER COLUMN quantity SET NOT NULL,
            ALTER COLUMN reason SET NOT NULL,
            ALTER COLUMN status SET NOT NULL,
            ALTER COLUMN order_params SET NOT NULL
        """))

        # Set default values for status if not set
        conn.execute(text("""
            ALTER TABLE failed_orders
            ALTER COLUMN status SET DEFAULT 'pending_retry'
        """))

        print("✅ Step 3 완료")
        print("\n🔄 Step 4: 구 컬럼 제거")

        # 4. Drop old columns (no longer needed)
        conn.execute(text("""
            ALTER TABLE failed_orders
            DROP COLUMN IF EXISTS user_id,
            DROP COLUMN IF EXISTS account_id,
            DROP COLUMN IF EXISTS pending_order_id,
            DROP COLUMN IF EXISTS open_order_id,
            DROP COLUMN IF EXISTS exchange_order_id,
            DROP COLUMN IF EXISTS failure_stage,
            DROP COLUMN IF EXISTS failure_reason,
            DROP COLUMN IF EXISTS error_message,
            DROP COLUMN IF EXISTS recovery_status,
            DROP COLUMN IF EXISTS last_exchange_status,
            DROP COLUMN IF EXISTS order_payload,
            DROP COLUMN IF EXISTS max_retry,
            DROP COLUMN IF EXISTS next_retry_at,
            DROP COLUMN IF EXISTS last_attempt_at,
            DROP COLUMN IF EXISTS resolved_at
        """))

        print("✅ Step 4 완료")
        print("\n🔄 Step 5: 인덱스 재생성")

        # 5. Recreate indexes (if needed)
        # Drop old indexes that might conflict
        conn.execute(text("""
            DROP INDEX IF EXISTS idx_failed_strategy_symbol;
            DROP INDEX IF EXISTS idx_failed_status;
            DROP INDEX IF EXISTS idx_failed_retry
        """))

        # Create new indexes matching models.py
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_failed_strategy_symbol
            ON failed_orders(strategy_account_id, symbol);

            CREATE INDEX IF NOT EXISTS idx_failed_status
            ON failed_orders(status, created_at);

            CREATE INDEX IF NOT EXISTS idx_failed_retry
            ON failed_orders(retry_count)
        """))

        print("✅ Step 5 완료")

        # Commit transaction
        trans.commit()
        print("\n✅ 마이그레이션 완료!")

        # Display final schema
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'failed_orders'
            ORDER BY ordinal_position
        """))

        print("\n📊 최종 스키마:")
        for row in result:
            print(f"  {row[0]:30} {row[1]:20} {'NULL' if row[2] == 'YES' else 'NOT NULL':10} {row[3] or ''}")

    except Exception as e:
        trans.rollback()
        print(f"\n❌ 마이그레이션 실패: {e}")
        raise
    finally:
        conn.close()


def downgrade(engine):
    """Rollback migration to original schema"""

    conn = engine.connect()
    trans = conn.begin()

    try:
        print("🔄 Rollback 시작: 원래 스키마로 복원")

        # 1. Add back old columns
        print("Step 1: 구 컬럼 복원")
        conn.execute(text("""
            ALTER TABLE failed_orders
            ADD COLUMN IF NOT EXISTS user_id INTEGER,
            ADD COLUMN IF NOT EXISTS account_id INTEGER,
            ADD COLUMN IF NOT EXISTS pending_order_id INTEGER,
            ADD COLUMN IF NOT EXISTS open_order_id INTEGER,
            ADD COLUMN IF NOT EXISTS exchange_order_id VARCHAR(120),
            ADD COLUMN IF NOT EXISTS failure_stage VARCHAR(20),
            ADD COLUMN IF NOT EXISTS failure_reason VARCHAR(120),
            ADD COLUMN IF NOT EXISTS error_message TEXT,
            ADD COLUMN IF NOT EXISTS recovery_status VARCHAR(30),
            ADD COLUMN IF NOT EXISTS last_exchange_status VARCHAR(30),
            ADD COLUMN IF NOT EXISTS order_payload JSON,
            ADD COLUMN IF NOT EXISTS max_retry INTEGER,
            ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP
        """))

        # 2. Migrate data back (best effort)
        print("Step 2: 데이터 복원")
        result = conn.execute(text("""
            SELECT id, reason, exchange_error, status, order_params
            FROM failed_orders
        """))

        for row in result:
            fo_id = row[0]
            reason = row[1]
            exchange_error = row[2]
            status = row[3]
            order_params = row[4]

            conn.execute(text("""
                UPDATE failed_orders
                SET failure_reason = :failure_reason,
                    error_message = :error_message,
                    recovery_status = :recovery_status,
                    order_payload = :order_payload,
                    failure_stage = 'execution',
                    max_retry = 5
                WHERE id = :id
            """), {
                'id': fo_id,
                'failure_reason': reason,
                'error_message': exchange_error,
                'recovery_status': status,
                'order_payload': order_params
            })

        # 3. Drop new columns
        print("Step 3: 신규 컬럼 제거")
        conn.execute(text("""
            ALTER TABLE failed_orders
            DROP COLUMN IF EXISTS quantity,
            DROP COLUMN IF EXISTS price,
            DROP COLUMN IF EXISTS stop_price,
            DROP COLUMN IF EXISTS reason,
            DROP COLUMN IF EXISTS exchange_error,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS webhook_id,
            DROP COLUMN IF EXISTS order_params
        """))

        # 4. Add back NOT NULL constraints
        print("Step 4: 제약조건 복원")
        conn.execute(text("""
            ALTER TABLE failed_orders
            ALTER COLUMN failure_stage SET NOT NULL,
            ALTER COLUMN recovery_status SET NOT NULL,
            ALTER COLUMN retry_count SET NOT NULL,
            ALTER COLUMN max_retry SET NOT NULL
        """))

        trans.commit()
        print("✅ Rollback 완료")

    except Exception as e:
        trans.rollback()
        print(f"❌ Rollback 실패: {e}")
        raise
    finally:
        conn.close()
