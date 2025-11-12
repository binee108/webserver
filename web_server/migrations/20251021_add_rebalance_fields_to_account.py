"""
Add previous_total_capital and last_rebalance_at to Account

마이그레이션 ID: 20251021_add_rebalance_fields_to_account
목적: 자본 재할당 트리거 조건 개선 (시간 기반 → 잔고 변화 기반)
생성일: 2025-10-21

변경 사항:
- Account 테이블에 previous_total_capital 컬럼 추가 (Float, nullable)
- Account 테이블에 last_rebalance_at 컬럼 추가 (DateTime, nullable)

업그레이드:
- 두 컬럼 추가 (기존 데이터는 NULL 유지)
- capital_allocation_service가 최초 실행 시 처리

다운그레이드:
- 두 컬럼 제거
"""

# @FEAT:capital-reallocation @COMP:migration @TYPE:core
from sqlalchemy import text


def upgrade(engine):
    """Add rebalance tracking fields to Account table

    안전성 개선:
    - 테이블 존재 여부 확인 (초기 설치 시 건너뛰기)
    - SQLAlchemy engine 사용으로 표준화
    """
    with engine.connect() as conn:
        # 테이블 존재 여부 확인
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'accounts'
            );
        """))
        table_exists = result.scalar()

        if not table_exists:
            print('ℹ️  accounts 테이블이 없습니다. 건너뜁니다 (초기 설치).')
            return

        # 1. previous_total_capital 컬럼 추가
        conn.execute(text("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS previous_total_capital FLOAT
        """))
        print("✅ accounts.previous_total_capital 컬럼 추가 완료")

        # 2. last_rebalance_at 컬럼 추가
        conn.execute(text("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS last_rebalance_at TIMESTAMP
        """))
        print("✅ accounts.last_rebalance_at 컬럼 추가 완료")

        # 3. 컬럼 코멘트 추가
        conn.execute(text("""
            COMMENT ON COLUMN accounts.previous_total_capital IS '재할당 시점 총 자산 (USDT)';
        """))
        conn.execute(text("""
            COMMENT ON COLUMN accounts.last_rebalance_at IS '마지막 재할당 시각 (UTC)';
        """))
        print("✅ 컬럼 코멘트 추가 완료")

        conn.commit()
        print("✅ 마이그레이션 완료 - 자본 재할당 필드 추가")


def downgrade(engine):
    """Remove rebalance tracking fields from Account table"""
    with engine.connect() as conn:
        # 테이블 존재 여부 확인
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'accounts'
            );
        """))
        table_exists = result.scalar()

        if not table_exists:
            print('ℹ️  accounts 테이블이 없습니다. 건너뜁니다.')
            return

        # 1. last_rebalance_at 컬럼 제거
        conn.execute(text("""
            ALTER TABLE accounts
            DROP COLUMN IF EXISTS last_rebalance_at
        """))
        print("✅ accounts.last_rebalance_at 컬럼 제거 완료")

        # 2. previous_total_capital 컬럼 제거
        conn.execute(text("""
            ALTER TABLE accounts
            DROP COLUMN IF EXISTS previous_total_capital
        """))
        print("✅ accounts.previous_total_capital 컬럼 제거 완료")

        conn.commit()
        print("✅ 롤백 완료 - 자본 재할당 필드 제거")
