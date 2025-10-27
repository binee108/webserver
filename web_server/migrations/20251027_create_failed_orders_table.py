"""
마이그레이션: failed_orders 테이블 생성 (Phase 1: Immediate Order Execution)

@FEAT:immediate-order-execution @COMP:migration @TYPE:core

목적:
- 거래소 API 호출 실패로 즉시 실행되지 못한 주문 기록
- 배치 주문 처리 시 우선순위 기반 재시도 지원

의존성:
- strategy_accounts 테이블 (외래키 참조)
- 이전 마이그레이션: 20251008_create_order_queue_tables.py

변경사항:
- failed_orders 테이블 생성 (11개 컬럼)
- 복합 인덱스 3개 생성 (조회 성능 최적화)

롤백:
- downgrade() 메서드로 안전한 롤백 지원
- failed_orders 테이블 및 모든 인덱스 자동 제거

실행 방법:
1. 자동 마이그레이션: python run.py migrate (예상 완료)
2. 수동 실행: python migrations/20251027_create_failed_orders_table.py
3. SQL 직접 실행: \i migrations/20251027_create_failed_orders_table.py (psql)

작성일: 2025-10-27
기능: immediate-order-execution
"""

from sqlalchemy import text


def upgrade(engine):
    """
    실패한 주문 기록 테이블 생성

    테이블:
    1. failed_orders: 실패한 주문 기록 및 재시도 관리
    """
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print('🚀 실패한 주문 기록 테이블 생성 시작...')

            # 기존 테이블 확인
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'failed_orders'
            """))
            existing_count = result.scalar()

            if existing_count > 0:
                print('✅ failed_orders 테이블이 이미 존재합니다.')
                trans.rollback()
                return

            # ============================================
            # 1. FailedOrder 테이블 생성
            # ============================================
            print('📝 failed_orders 테이블 생성 중...')
            conn.execute(text("""
                CREATE TABLE failed_orders (
                    -- 식별자
                    id SERIAL PRIMARY KEY,
                    strategy_account_id INTEGER NOT NULL REFERENCES strategy_accounts(id) ON DELETE CASCADE,

                    -- 주문 정보
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    order_type VARCHAR(20) NOT NULL,
                    quantity DECIMAL(20, 8) NOT NULL,
                    price DECIMAL(20, 8),
                    stop_price DECIMAL(20, 8),
                    market_type VARCHAR(10) NOT NULL,

                    -- 실패 정보
                    reason VARCHAR(100) NOT NULL,
                    exchange_error TEXT,
                    order_params JSONB NOT NULL,

                    -- 재시도 관리
                    status VARCHAR(20) DEFAULT 'pending_retry' NOT NULL,
                    retry_count INTEGER DEFAULT 0 NOT NULL,

                    -- 메타데이터
                    webhook_id VARCHAR(100),
                    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
                );
            """))
            print('✅ failed_orders 테이블 생성 완료')

            # ============================================
            # 2. 인덱스 생성
            # ============================================
            print('📊 failed_orders 인덱스 생성 중...')

            # strategy_account_id와 symbol 기반 조회 인덱스
            conn.execute(text("""
                CREATE INDEX idx_failed_strategy_symbol
                ON failed_orders(strategy_account_id, symbol);
            """))
            print('✅ idx_failed_strategy_symbol 생성 완료')

            # 상태 및 생성일 기반 조회 인덱스 (재시도 대기 주문 조회)
            conn.execute(text("""
                CREATE INDEX idx_failed_status
                ON failed_orders(status, created_at);
            """))
            print('✅ idx_failed_status 생성 완료')

            # 재시도 횟수 기반 조회 인덱스 (최대 재시도 초과 필터링)
            conn.execute(text("""
                CREATE INDEX idx_failed_retry
                ON failed_orders(retry_count);
            """))
            print('✅ idx_failed_retry 생성 완료')

            # ============================================
            # 3. 커밋
            # ============================================
            trans.commit()
            print('✅ failed_orders 테이블 생성 및 인덱스 설정 완료')

        except Exception as e:
            trans.rollback()
            print(f'❌ 마이그레이션 실패: {e}')
            raise


def downgrade(engine):
    """
    실패한 주문 기록 테이블 제거 (롤백)
    """
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print('🔄 failed_orders 테이블 제거 시작...')

            # 테이블 존재 확인
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'failed_orders'
            """))
            existing_count = result.scalar()

            if existing_count == 0:
                print('⚠️ failed_orders 테이블이 존재하지 않습니다.')
                trans.rollback()
                return

            # 인덱스 제거 (순서 중요 - 인덱스 먼저)
            print('📊 failed_orders 인덱스 제거 중...')
            conn.execute(text("DROP INDEX IF EXISTS idx_failed_retry;"))
            conn.execute(text("DROP INDEX IF EXISTS idx_failed_status;"))
            conn.execute(text("DROP INDEX IF EXISTS idx_failed_strategy_symbol;"))
            print('✅ 인덱스 제거 완료')

            # 테이블 제거
            print('🗑️ failed_orders 테이블 제거 중...')
            conn.execute(text("DROP TABLE IF EXISTS failed_orders CASCADE;"))
            print('✅ failed_orders 테이블 제거 완료')

            trans.commit()
            print('✅ 롤백 완료')

        except Exception as e:
            trans.rollback()
            print(f'❌ 롤백 실패: {e}')
            raise


if __name__ == '__main__':
    """
    마이그레이션 스크립트 직접 실행 (테스트용)

    Usage:
        python migrations/20251027_create_failed_orders_table.py
    """
    import os
    import sys
    from sqlalchemy import create_engine

    # 프로젝트 루트 디렉토리를 Python 경로에 추가
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    # 환경 변수에서 데이터베이스 URL 가져오기
    from dotenv import load_dotenv
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print('❌ DATABASE_URL 환경 변수가 설정되지 않았습니다.')
        sys.exit(1)

    # 엔진 생성
    engine = create_engine(database_url)

    # 마이그레이션 실행
    print('=' * 60)
    print('FailedOrder 테이블 마이그레이션')
    print('=' * 60)
    upgrade(engine)
    print('=' * 60)
