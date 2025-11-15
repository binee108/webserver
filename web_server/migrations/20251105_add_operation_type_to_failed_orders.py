"""
Add operation_type and original_order_id columns to failed_orders table

@FEAT:immediate-order-execution @COMP:migration @TYPE:core

이 마이그레이션은 failed_orders 테이블에 Phase 2 기능을 위한 컬럼을 추가합니다:
- operation_type: 주문 생성 실패(CREATE)와 주문 취소 실패(CANCEL) 구분
- original_order_id: 취소 실패 시 거래소 주문 ID 저장

Purpose:
  주문 실패 추적 시스템(orphan-order-prevention)을 위해 실패 원인별로 다양한 정보 관리

Dependencies:
  Requires: 20251030_migrate_failed_orders_schema.py (Phase 1 스키마 필수)

Idempotency:
  이미 컬럼이 존재하면 마이그레이션을 스킵합니다.
  재실행 시 안전합니다.

Rollback:
  downgrade() 함수로 완벽한 롤백을 지원합니다.

Revision ID: 20251105_operation_type
Revises: 20251030_migrate_failed_orders_schema
Create Date: 2025-11-05
"""

from sqlalchemy import text


def upgrade(engine):
    """
    Add operation_type and original_order_id columns to failed_orders

    Columns:
      operation_type: VARCHAR(20) NOT NULL DEFAULT 'CREATE'
        - 'CREATE': 주문 생성 실패
        - 'CANCEL': 주문 취소 실패
        - Indexed for quick filtering by operation type

      original_order_id: VARCHAR(100) NULLABLE
        - 취소 실패 시 거래소에서 이미 생성된 주문 ID
        - 주문 생성 실패 시 NULL

    Flow:
      1. Idempotency 체크: 컬럼 존재 여부 확인
      2. operation_type 추가
      3. original_order_id 추가
      4. operation_type에 인덱스 생성
      5. 최종 스키마 출력
    """

    conn = engine.connect()
    trans = conn.begin()

    try:
        # Check table existence
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'failed_orders'
            );
        """))
        if not result.scalar():
            print('ℹ️  failed_orders table not found. Skipping (initial install).')
            trans.rollback()
            conn.close()
            return

        print("🔄 Step 1: operation_type, original_order_id 컬럼 존재 확인")

        # Idempotency: Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'failed_orders'
            AND column_name IN ('operation_type', 'original_order_id')
        """))
        existing_columns = [row[0] for row in result]

        if 'operation_type' in existing_columns and 'original_order_id' in existing_columns:
            print("✅ operation_type, original_order_id 컬럼이 이미 존재합니다. 마이그레이션 스킵.")
            trans.rollback()
            return

        print("📝 Step 2: operation_type 컬럼 추가 중...")
        if 'operation_type' not in existing_columns:
            conn.execute(text("""
                ALTER TABLE failed_orders
                ADD COLUMN operation_type VARCHAR(20) NOT NULL DEFAULT 'CREATE'
            """))
            print("✅ operation_type 컬럼 추가 완료")

        print("📝 Step 3: original_order_id 컬럼 추가 중...")
        if 'original_order_id' not in existing_columns:
            conn.execute(text("""
                ALTER TABLE failed_orders
                ADD COLUMN original_order_id VARCHAR(100)
            """))
            print("✅ original_order_id 컬럼 추가 완료")

        print("📝 Step 4: idx_failed_operation_type 인덱스 생성 중...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_failed_operation_type
            ON failed_orders(operation_type)
        """))
        print("✅ 인덱스 생성 완료")

        # Commit transaction
        trans.commit()
        print("\n🎉 failed_orders 테이블 마이그레이션 완료!")

        # Display final schema
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'failed_orders'
            ORDER BY ordinal_position
        """))

        print("\n📊 최종 스키마:")
        for row in result:
            nullable_str = 'NULL' if row[2] == 'YES' else 'NOT NULL'
            default_str = row[3] or ''
            print(f"  {row[0]:30} {row[1]:20} {nullable_str:10} {default_str}")

    except Exception as e:
        trans.rollback()
        print(f"\n❌ 마이그레이션 실패: {e}")
        raise
    finally:
        conn.close()


def downgrade(engine):
    """
    Remove operation_type and original_order_id columns from failed_orders

    Rollback Flow:
      1. idx_failed_operation_type 인덱스 제거
      2. operation_type 컬럼 제거
      3. original_order_id 컬럼 제거

    Notes:
      - DROP COLUMN IF EXISTS를 사용하여 idempotent 롤백 지원
      - 기존 데이터는 완전히 제거됩니다
      - Phase 1 (20251030_migrate_failed_orders_schema)로 롤백됩니다
    """

    conn = engine.connect()
    trans = conn.begin()

    try:
        print("🔄 Rollback 시작: operation_type, original_order_id 컬럼 제거")

        print("🔄 Step 1: idx_failed_operation_type 인덱스 제거 중...")
        conn.execute(text("""
            DROP INDEX IF EXISTS idx_failed_operation_type
        """))
        print("✅ 인덱스 제거 완료")

        print("🔄 Step 2: operation_type 컬럼 제거 중...")
        conn.execute(text("""
            ALTER TABLE failed_orders
            DROP COLUMN IF EXISTS operation_type
        """))
        print("✅ operation_type 컬럼 제거 완료")

        print("🔄 Step 3: original_order_id 컬럼 제거 중...")
        conn.execute(text("""
            ALTER TABLE failed_orders
            DROP COLUMN IF EXISTS original_order_id
        """))
        print("✅ original_order_id 컬럼 제거 완료")

        trans.commit()
        print("\n🎉 failed_orders 테이블 롤백 완료!")

    except Exception as e:
        trans.rollback()
        print(f"\n❌ 롤백 실패: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    from sqlalchemy import create_engine

    # Database URL from environment or default
    DATABASE_URL = "postgresql://trader:password123@postgres:5432/trading_system"

    print("=" * 60)
    print("🔧 Add operation_type and original_order_id Migration")
    print("=" * 60)
    print(f"\n📍 Database: {DATABASE_URL}\n")

    try:
        engine = create_engine(DATABASE_URL)
        upgrade(engine)
        print("\n" + "=" * 60)
        print("✅ 마이그레이션 성공!")
        print("=" * 60)
        sys.exit(0)
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ 마이그레이션 실패: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        engine.dispose()
