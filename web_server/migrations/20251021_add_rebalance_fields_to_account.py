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
def upgrade():
    """Add rebalance tracking fields to Account table"""
    import psycopg2
    import os
    from pathlib import Path

    # .env 파일 로드
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    # DATABASE_URL에서 연결 정보 추출
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL 환경 변수가 설정되지 않았습니다")

    # psycopg2 형식으로 변환 (postgresql:// -> postgres://)
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgres://', 1)

    # Docker 호스트명을 localhost로 변경 (로컬 실행 시)
    database_url = database_url.replace('postgres:5432', 'localhost:5432')
    # DB 이름 수정 (trading_dev -> trading_system)
    database_url = database_url.replace('/trading_dev', '/trading_system')

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        # 1. previous_total_capital 컬럼 추가
        cursor.execute("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS previous_total_capital FLOAT
        """)
        print("✅ accounts.previous_total_capital 컬럼 추가 완료")

        # 2. last_rebalance_at 컬럼 추가
        cursor.execute("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS last_rebalance_at TIMESTAMP
        """)
        print("✅ accounts.last_rebalance_at 컬럼 추가 완료")

        # 3. 컬럼 코멘트 추가
        cursor.execute("""
            COMMENT ON COLUMN accounts.previous_total_capital IS '재할당 시점 총 자산 (USDT)';
        """)
        cursor.execute("""
            COMMENT ON COLUMN accounts.last_rebalance_at IS '마지막 재할당 시각 (UTC)';
        """)
        print("✅ 컬럼 코멘트 추가 완료")

        conn.commit()
        print("✅ 마이그레이션 완료 - 자본 재할당 필드 추가")

    except Exception as e:
        conn.rollback()
        print(f"❌ 마이그레이션 실패: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


# @FEAT:capital-reallocation @COMP:migration @TYPE:core
def downgrade():
    """Remove rebalance tracking fields from Account table"""
    import psycopg2
    import os
    from pathlib import Path

    # .env 파일 로드
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL 환경 변수가 설정되지 않았습니다")

    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgres://', 1)

    # Docker 호스트명을 localhost로 변경 (로컬 실행 시)
    database_url = database_url.replace('postgres:5432', 'localhost:5432')
    # DB 이름 수정 (trading_dev -> trading_system)
    database_url = database_url.replace('/trading_dev', '/trading_system')

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        # 1. last_rebalance_at 컬럼 제거
        cursor.execute("""
            ALTER TABLE accounts
            DROP COLUMN IF EXISTS last_rebalance_at
        """)
        print("✅ accounts.last_rebalance_at 컬럼 제거 완료")

        # 2. previous_total_capital 컬럼 제거
        cursor.execute("""
            ALTER TABLE accounts
            DROP COLUMN IF EXISTS previous_total_capital
        """)
        print("✅ accounts.previous_total_capital 컬럼 제거 완료")

        conn.commit()
        print("✅ 롤백 완료 - 자본 재할당 필드 제거")

    except Exception as e:
        conn.rollback()
        print(f"❌ 롤백 실패: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("사용법: python 20251021_add_rebalance_fields_to_account.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'upgrade':
        upgrade()
    elif command == 'downgrade':
        downgrade()
    else:
        print(f"❌ 알 수 없는 명령: {command}")
        sys.exit(1)
