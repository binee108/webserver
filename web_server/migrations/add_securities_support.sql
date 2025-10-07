-- ============================================
-- 증권 거래소 지원 마이그레이션
-- ============================================
-- 작성일: 2025-10-07
-- 목적: Account 테이블 확장 및 SecuritiesToken 테이블 생성
-- 주의: 실행 전 백업 필수
-- ============================================

BEGIN;

-- ============================================
-- 1. Account 테이블 확장
-- ============================================

-- 1-1. account_type 컬럼 추가 (기본값: CRYPTO)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'account_type'
    ) THEN
        ALTER TABLE accounts
        ADD COLUMN account_type VARCHAR(20) DEFAULT 'CRYPTO' NOT NULL;

        -- 인덱스 추가 (조회 성능 향상)
        CREATE INDEX idx_account_type ON accounts(account_type);

        RAISE NOTICE '✅ accounts.account_type 컬럼 추가 완료';
    ELSE
        RAISE NOTICE '⚠️ accounts.account_type 컬럼이 이미 존재합니다';
    END IF;
END $$;

-- 1-2. securities_config 컬럼 추가 (암호화된 JSON)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'securities_config'
    ) THEN
        ALTER TABLE accounts
        ADD COLUMN securities_config TEXT NULL;

        RAISE NOTICE '✅ accounts.securities_config 컬럼 추가 완료';
    ELSE
        RAISE NOTICE '⚠️ accounts.securities_config 컬럼이 이미 존재합니다';
    END IF;
END $$;

-- 1-3. access_token 컬럼 추가 (암호화된 OAuth 토큰)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'access_token'
    ) THEN
        ALTER TABLE accounts
        ADD COLUMN access_token TEXT NULL;

        RAISE NOTICE '✅ accounts.access_token 컬럼 추가 완료';
    ELSE
        RAISE NOTICE '⚠️ accounts.access_token 컬럼이 이미 존재합니다';
    END IF;
END $$;

-- 1-4. token_expires_at 컬럼 추가
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'token_expires_at'
    ) THEN
        ALTER TABLE accounts
        ADD COLUMN token_expires_at TIMESTAMP NULL;

        RAISE NOTICE '✅ accounts.token_expires_at 컬럼 추가 완료';
    ELSE
        RAISE NOTICE '⚠️ accounts.token_expires_at 컬럼이 이미 존재합니다';
    END IF;
END $$;

-- ============================================
-- 2. SecuritiesToken 테이블 생성
-- ============================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'securities_tokens'
    ) THEN
        CREATE TABLE securities_tokens (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            access_token TEXT NOT NULL,
            token_type VARCHAR(20) DEFAULT 'Bearer' NOT NULL,
            expires_in INTEGER NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            last_refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

            -- Foreign Key 제약조건
            CONSTRAINT fk_securities_token_account
                FOREIGN KEY (account_id)
                REFERENCES accounts(id)
                ON DELETE CASCADE,

            -- Unique 제약조건 (계좌당 1개 토큰)
            CONSTRAINT uq_securities_token_account
                UNIQUE (account_id)
        );

        -- 인덱스 추가 (조회 성능 최적화)
        CREATE INDEX idx_securities_token_account_id ON securities_tokens(account_id);
        CREATE INDEX idx_securities_token_expires_at ON securities_tokens(expires_at);
        CREATE INDEX idx_securities_token_last_refreshed ON securities_tokens(last_refreshed_at);

        RAISE NOTICE '✅ securities_tokens 테이블 생성 완료';
    ELSE
        RAISE NOTICE '⚠️ securities_tokens 테이블이 이미 존재합니다';
    END IF;
END $$;

-- ============================================
-- 3. 검증 쿼리
-- ============================================

-- 3-1. Account 테이블 컬럼 확인
DO $$
DECLARE
    column_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO column_count
    FROM information_schema.columns
    WHERE table_name = 'accounts'
      AND column_name IN ('account_type', 'securities_config', 'access_token', 'token_expires_at');

    RAISE NOTICE '📊 accounts 테이블 추가 컬럼: %개', column_count;
END $$;

-- 3-2. SecuritiesToken 테이블 구조 확인
DO $$
DECLARE
    table_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'securities_tokens'
    ) INTO table_exists;

    IF table_exists THEN
        RAISE NOTICE '📊 securities_tokens 테이블: 존재함';
    ELSE
        RAISE NOTICE '⚠️ securities_tokens 테이블: 존재하지 않음';
    END IF;
END $$;

COMMIT;

-- ============================================
-- 마이그레이션 완료
-- ============================================
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '✅ 증권 거래소 지원 마이그레이션 완료';
    RAISE NOTICE '';
    RAISE NOTICE '변경 내역:';
    RAISE NOTICE '  - accounts.account_type (CRYPTO/SECURITIES_STOCK 등)';
    RAISE NOTICE '  - accounts.securities_config (암호화된 증권사 설정)';
    RAISE NOTICE '  - accounts.access_token (OAuth 토큰)';
    RAISE NOTICE '  - accounts.token_expires_at (토큰 만료 시각)';
    RAISE NOTICE '  - securities_tokens 테이블 (토큰 캐시)';
    RAISE NOTICE '';
END $$;
