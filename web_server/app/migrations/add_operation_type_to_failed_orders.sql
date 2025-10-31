-- @FEAT:orphan-order-prevention @COMP:model @TYPE:migration @PHASE:2
-- Phase 2: Add operation_type and original_order_id to failed_orders
-- Date: 2025-10-31
-- Purpose: Track cancel failures in FailedOrder table

-- ============================================================
-- UP MIGRATION
-- ============================================================

-- 1. operation_type 필드 추가 (기본값 'CREATE')
ALTER TABLE failed_orders
ADD COLUMN operation_type VARCHAR(20) NOT NULL DEFAULT 'CREATE';

-- 2. original_order_id 필드 추가 (NULL 허용)
ALTER TABLE failed_orders
ADD COLUMN original_order_id VARCHAR(100);

-- 3. operation_type 인덱스 생성
CREATE INDEX idx_failed_operation_type ON failed_orders(operation_type);

-- 4. 기존 데이터는 자동으로 DEFAULT 'CREATE' 적용됨
-- (추가 데이터 마이그레이션 불필요)

-- 5. 컬럼 설명 추가
COMMENT ON COLUMN failed_orders.operation_type IS 'Operation type: CREATE (생성 실패) or CANCEL (취소 실패)';
COMMENT ON COLUMN failed_orders.original_order_id IS 'Original exchange order ID (for CANCEL operation_type)';


-- ============================================================
-- DOWN MIGRATION (롤백)
-- ============================================================

-- 1. 인덱스 삭제
-- DROP INDEX IF EXISTS idx_failed_operation_type;

-- 2. 필드 삭제
-- ALTER TABLE failed_orders DROP COLUMN IF EXISTS operation_type;
-- ALTER TABLE failed_orders DROP COLUMN IF EXISTS original_order_id;
