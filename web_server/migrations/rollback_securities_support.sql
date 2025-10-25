-- ============================================
-- 증권 거래소 지원 롤백 스크립트
-- ============================================
-- 작성일: 2025-10-07
-- 목적: add_securities_support.sql 롤백
-- 주의: 데이터 손실 가능 (백업 필수)
-- ============================================

BEGIN;

RAISE NOTICE '';
RAISE NOTICE '⚠️ 증권 거래소 지원 롤백 시작';
RAISE NOTICE '⚠️ 모든 증권 관련 데이터가 삭제됩니다';
RAISE NOTICE '';

-- ============================================
-- 1. SecuritiesToken 테이블 삭제
-- ============================================

-- 1-1. 인덱스 명시적 삭제
DROP INDEX IF EXISTS idx_securities_token_account_id;
DROP INDEX IF EXISTS idx_securities_token_expires_at;
DROP INDEX IF EXISTS idx_securities_token_last_refreshed;
RAISE NOTICE '✅ securities_tokens 인덱스 삭제 완료';

-- 1-2. SecuritiesToken 테이블 삭제
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'securities_tokens'
    ) THEN
        DROP TABLE securities_tokens CASCADE;
        RAISE NOTICE '✅ securities_tokens 테이블 삭제 완료';
    ELSE
        RAISE NOTICE '⚠️ securities_tokens 테이블이 존재하지 않습니다';
    END IF;
END $$;

-- ============================================
-- 2. Account 테이블 컬럼 삭제
-- ============================================

-- 2-1. token_expires_at 컬럼 삭제
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'token_expires_at'
    ) THEN
        ALTER TABLE accounts DROP COLUMN token_expires_at;
        RAISE NOTICE '✅ accounts.token_expires_at 컬럼 삭제 완료';
    ELSE
        RAISE NOTICE '⚠️ accounts.token_expires_at 컬럼이 존재하지 않습니다';
    END IF;
END $$;

-- 2-2. access_token 컬럼 삭제
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'access_token'
    ) THEN
        ALTER TABLE accounts DROP COLUMN access_token;
        RAISE NOTICE '✅ accounts.access_token 컬럼 삭제 완료';
    ELSE
        RAISE NOTICE '⚠️ accounts.access_token 컬럼이 존재하지 않습니다';
    END IF;
END $$;

-- 2-3. securities_config 컬럼 삭제
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'securities_config'
    ) THEN
        ALTER TABLE accounts DROP COLUMN securities_config;
        RAISE NOTICE '✅ accounts.securities_config 컬럼 삭제 완료';
    ELSE
        RAISE NOTICE '⚠️ accounts.securities_config 컬럼이 존재하지 않습니다';
    END IF;
END $$;

-- 2-4. account_type 컬럼 삭제
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'account_type'
    ) THEN
        -- 인덱스 먼저 삭제
        DROP INDEX IF EXISTS idx_account_type;

        ALTER TABLE accounts DROP COLUMN account_type;
        RAISE NOTICE '✅ accounts.account_type 컬럼 삭제 완료';
    ELSE
        RAISE NOTICE '⚠️ accounts.account_type 컬럼이 존재하지 않습니다';
    END IF;
END $$;

-- ============================================
-- 3. 검증
-- ============================================

DO $$
DECLARE
    remaining_columns INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining_columns
    FROM information_schema.columns
    WHERE table_name = 'accounts'
      AND column_name IN ('account_type', 'securities_config', 'access_token', 'token_expires_at');

    IF remaining_columns = 0 THEN
        RAISE NOTICE '✅ 모든 증권 관련 컬럼 삭제 완료';
    ELSE
        RAISE NOTICE '⚠️ 삭제되지 않은 컬럼 %개 남음', remaining_columns;
    END IF;
END $$;

COMMIT;

-- ============================================
-- 롤백 완료
-- ============================================
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '✅ 롤백 완료 - 증권 거래소 지원 기능 제거됨';
    RAISE NOTICE '';
    RAISE NOTICE '삭제된 항목:';
    RAISE NOTICE '  - securities_tokens 테이블';
    RAISE NOTICE '  - accounts.account_type';
    RAISE NOTICE '  - accounts.securities_config';
    RAISE NOTICE '  - accounts.access_token';
    RAISE NOTICE '  - accounts.token_expires_at';
    RAISE NOTICE '';
END $$;
