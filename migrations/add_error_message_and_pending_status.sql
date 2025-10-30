-- Migration: Add error_message column and PENDING status support for DB-first pattern
-- Date: 2025-10-30
-- Phase: Phase 2 (DB-first Pattern Implementation)
-- Purpose: Support orphan order prevention via DB-first pattern

-- Add error_message column to track failures (Phase 2)
-- @DATA:error_message - 주문 실패 원인 저장
ALTER TABLE open_orders ADD COLUMN error_message TEXT NULL;
COMMENT ON COLUMN open_orders.error_message IS '[Phase 2] 주문 실패 시 에러 메시지 저장 (PENDING → FAILED 전환 시 설정)';

-- Create index for error_message queries (for cleanup jobs)
CREATE INDEX idx_open_orders_error_message ON open_orders(error_message) WHERE error_message IS NOT NULL;

-- Add index on status for background job queries (get_active_statuses, cleanup job)
CREATE INDEX idx_open_orders_status_created ON open_orders(status, created_at)
  WHERE status IN ('PENDING', 'NEW', 'OPEN', 'PARTIALLY_FILLED');
COMMENT ON INDEX idx_open_orders_status_created IS '[Phase 2] Cleanup job optimization - query PENDING orders by created_at';

-- Add index for UI queries (exclude PENDING from display)
CREATE INDEX idx_open_orders_status_ui ON open_orders(status)
  WHERE status IN ('NEW', 'OPEN', 'PARTIALLY_FILLED');
COMMENT ON INDEX idx_open_orders_status_ui IS '[Phase 2] UI query optimization - exclude PENDING status';
