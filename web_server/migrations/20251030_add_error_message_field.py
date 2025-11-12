"""
마이그레이션: OpenOrder 테이블에 error_message 필드 추가 (Phase 1: Database & Security Enhancements)

@FEAT:webhook-order @COMP:migration @TYPE:core

목적:
- 거래소 API 호출 실패 시 에러 메시지 저장
- 고아 주문 방지 분석에 사용될 에러 정보 기록
- 주문 실패 원인 디버깅 지원

의존성:
- open_orders 테이블 (Phase 5 이후 유일한 주문 추적 모델)
- 이전 마이그레이션: 20251027_create_failed_orders_table.py

변경사항:
- open_orders 테이블에 error_message 컬럼 추가 (TEXT, nullable)
- 데이터 타입: TEXT (최대 500자, 보안 처리된 메시지용)
- 기본값: NULL (기존 주문 영향 없음 - 백워드 호환성)

롤백:
- downgrade() 메서드로 안전한 롤백 지원
- error_message 컬럼 제거 (기존 데이터 손실 없음)

실행 방법:
1. 자동 마이그레이션: python run.py migrate (예상 완료)
2. 수동 실행: python migrations/20251030_add_error_message_field.py
3. SQL 직접 실행: \\i migrations/20251030_add_error_message_field.py (psql)

작성일: 2025-10-30
기능: webhook-order (고아 주문 방지를 위한 기반 구축)
"""

from sqlalchemy import text


def upgrade(engine):
    """
    OpenOrder 테이블에 error_message 필드 추가

    필드 설명:
    - error_message: 거래소 API 실패 시 반환된 에러 메시지 (보안 처리됨)
      - 타입: TEXT (최대 500자)
      - sanitize_error_message() 함수로 민감 정보 제거 후 저장
      - NULL 가능 (기존 주문 영향 없음)
    """
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Check table existence
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'open_orders'
                );
            """))
            if not result.scalar():
                print('ℹ️  open_orders table not found. Skipping (initial install).')
                trans.rollback()
                return

            print('🚀 OpenOrder 테이블 error_message 필드 추가 시작...')

            # 기존 필드 확인
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'open_orders'
                AND column_name = 'error_message'
            """))
            existing_count = result.scalar()

            if existing_count > 0:
                print('✅ error_message 필드가 이미 존재합니다.')
                trans.rollback()
                return

            # ============================================
            # 1. error_message 필드 추가
            # ============================================
            print('📝 open_orders 테이블에 error_message 필드 추가 중...')
            conn.execute(text("""
                ALTER TABLE open_orders
                ADD COLUMN error_message TEXT NULL;
            """))
            print('✅ error_message 필드 추가 완료')

            # ============================================
            # 2. 필드 설명 추가 (PostgreSQL COMMENT)
            # ============================================
            print('📚 error_message 필드 설명 추가 중...')
            conn.execute(text("""
                COMMENT ON COLUMN open_orders.error_message IS
                'Sanitized error message from exchange API failures (max 500 chars) - Phase 1 (2025-10-30)';
            """))
            print('✅ 필드 설명 추가 완료')

            # ============================================
            # 3. 커밋
            # ============================================
            trans.commit()
            print('✅ error_message 필드 추가 완료')

        except Exception as e:
            trans.rollback()
            print(f'❌ 마이그레이션 실패: {e}')
            raise


def downgrade(engine):
    """
    error_message 필드 제거 (롤백)
    """
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print('🔄 error_message 필드 제거 시작...')

            # 필드 존재 확인
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'open_orders'
                AND column_name = 'error_message'
            """))
            existing_count = result.scalar()

            if existing_count == 0:
                print('⚠️ error_message 필드가 존재하지 않습니다.')
                trans.rollback()
                return

            # 필드 제거
            print('🗑️ error_message 필드 제거 중...')
            conn.execute(text("""
                ALTER TABLE open_orders
                DROP COLUMN error_message;
            """))
            print('✅ error_message 필드 제거 완료')

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
        python migrations/20251030_add_error_message_field.py
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
    print('OpenOrder error_message 필드 마이그레이션')
    print('=' * 60)
    upgrade(engine)
    print('=' * 60)
