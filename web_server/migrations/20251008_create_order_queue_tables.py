"""
주문 대기열 시스템 테이블 생성 (Phase 1)

목적:
- 거래소 열린 주문 제한에 대응하는 대기열 시스템 구축
- PendingOrder: 제한 초과로 대기 중인 주문
- OrderFillEvent: 주문 체결 이벤트 로그 (재정렬 트리거)

변경사항:
- pending_orders 테이블 생성
- order_fill_events 테이블 생성
- 관련 인덱스 생성

작성일: 2025-10-08
참고: /Users/binee/Desktop/quant/webserver/docs/order_queue_system_plan.md
"""

from sqlalchemy import text


def upgrade(engine):
    """
    주문 대기열 시스템 테이블 생성

    테이블:
    1. pending_orders: 대기열 주문
    2. order_fill_events: 체결 이벤트
    """
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print('🚀 주문 대기열 시스템 테이블 생성 시작...')

            # 기존 테이블 확인 (부분 마이그레이션 상태 감지)
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name IN ('pending_orders', 'order_fill_events')
            """))
            existing_count = result.scalar()

            if existing_count == 2:
                print('✅ 테이블이 이미 존재합니다.')
                trans.rollback()
                return
            elif existing_count == 1:
                raise Exception('⚠️ 부분 마이그레이션 상태 감지 - 수동 확인 필요')

            # 아래는 기존 테이블 생성 로직...

        # ============================================
        # 1. PendingOrder 테이블 생성
        # ============================================
        print('📝 pending_orders 테이블 생성 중...')
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pending_orders (
                -- 식별자
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                strategy_account_id INTEGER NOT NULL REFERENCES strategy_accounts(id) ON DELETE CASCADE,

                -- 주문 정보
                symbol VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                order_type VARCHAR(20) NOT NULL,
                price DECIMAL(20, 8),
                stop_price DECIMAL(20, 8),
                quantity DECIMAL(20, 8) NOT NULL,

                -- 우선순위 계산
                priority INTEGER NOT NULL,
                sort_price DECIMAL(20, 8),

                -- 메타데이터
                market_type VARCHAR(10) NOT NULL,
                reason VARCHAR(50) NOT NULL DEFAULT 'QUEUE_LIMIT',
                retry_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # 인덱스 생성
        print('📊 pending_orders 인덱스 생성 중...')
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pending_account_symbol
            ON pending_orders(account_id, symbol);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pending_priority_sort
            ON pending_orders(account_id, symbol, priority, sort_price DESC, created_at ASC);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pending_strategy
            ON pending_orders(strategy_account_id);
        """))

        # ============================================
        # 2. OrderFillEvent 테이블 생성
        # ============================================
        print('📝 order_fill_events 테이블 생성 중...')
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS order_fill_events (
                -- 식별자
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                strategy_account_id INTEGER NOT NULL REFERENCES strategy_accounts(id) ON DELETE CASCADE,

                -- 주문 정보
                exchange_order_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                order_type VARCHAR(20) NOT NULL,

                -- 체결 정보
                filled_quantity DECIMAL(20, 8) NOT NULL,
                average_price DECIMAL(20, 8),
                status VARCHAR(20) NOT NULL,

                -- 이벤트 메타데이터
                event_time TIMESTAMP NOT NULL,
                processed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # 인덱스 생성
        print('📊 order_fill_events 인덱스 생성 중...')
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fill_order_id
            ON order_fill_events(exchange_order_id);
        """))

        # 부분 인덱스: processed = FALSE인 레코드만 인덱싱 (PostgreSQL 최적화)
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fill_unprocessed_time
            ON order_fill_events(event_time DESC)
            WHERE processed = FALSE;
        """))

        # 전체 인덱스 (호환성 유지)
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fill_processed
            ON order_fill_events(processed, event_time);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fill_account_symbol
            ON order_fill_events(account_id, symbol);
        """))

            # 트랜잭션 커밋
            trans.commit()
            print('✅ 주문 대기열 시스템 테이블 생성 완료!')
            print('')
            print('생성된 테이블:')
            print('  - pending_orders (인덱스 3개)')
            print('  - order_fill_events (인덱스 4개)')

        except Exception as e:
            # 트랜잭션 롤백
            trans.rollback()
            print(f'❌ 마이그레이션 실패: {e}')
            raise


def downgrade(engine):
    """
    주문 대기열 시스템 테이블 삭제

    주의사항:
    - 모든 대기열 데이터가 삭제됩니다
    - 체결 이벤트 로그가 삭제됩니다
    """
    with engine.connect() as conn:
        print('🗑️  주문 대기열 시스템 테이블 삭제 시작...')

        # 테이블 삭제 (인덱스는 자동으로 삭제됨)
        print('📝 order_fill_events 테이블 삭제 중...')
        conn.execute(text('DROP TABLE IF EXISTS order_fill_events CASCADE;'))

        print('📝 pending_orders 테이블 삭제 중...')
        conn.execute(text('DROP TABLE IF EXISTS pending_orders CASCADE;'))

        conn.commit()
        print('✅ 주문 대기열 시스템 테이블 삭제 완료!')


if __name__ == '__main__':
    """
    독립 실행 예시:

    from app import create_app, db
    app = create_app()
    with app.app_context():
        from migrations.20251008_create_order_queue_tables import upgrade
        upgrade(db.engine)
    """
    print("이 스크립트는 Flask 애플리케이션 컨텍스트에서 실행되어야 합니다.")
    print("")
    print("사용 예시:")
    print("  from app import create_app, db")
    print("  app = create_app()")
    print("  with app.app_context():")
    print("      from migrations.20251008_create_order_queue_tables import upgrade")
    print("      upgrade(db.engine)")
