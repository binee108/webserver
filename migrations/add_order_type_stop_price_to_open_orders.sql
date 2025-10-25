-- Migration: Add order_type and stop_price fields to open_orders table
-- Date: 2025-09-05
-- Purpose: Support STOP_MARKET and STOP_LIMIT order types

-- Add order_type column (default to LIMIT for existing records)
ALTER TABLE open_orders ADD COLUMN order_type VARCHAR(20) NOT NULL DEFAULT 'LIMIT';

-- Add stop_price column (nullable for non-STOP orders)  
ALTER TABLE open_orders ADD COLUMN stop_price FLOAT NULL;

-- Update price column to be nullable (MARKET orders may not have price)
ALTER TABLE open_orders ALTER COLUMN price DROP NOT NULL;

-- Add index for better query performance
CREATE INDEX idx_open_orders_order_type ON open_orders(order_type);
CREATE INDEX idx_open_orders_stop_price ON open_orders(stop_price) WHERE stop_price IS NOT NULL;

-- Add constraints to ensure data integrity
-- STOP orders must have stop_price
-- ALTER TABLE open_orders ADD CONSTRAINT chk_stop_orders_have_stop_price 
--   CHECK ((order_type NOT IN ('STOP_LIMIT', 'STOP_MARKET')) OR (stop_price IS NOT NULL));

-- LIMIT orders must have price
-- ALTER TABLE open_orders ADD CONSTRAINT chk_limit_orders_have_price 
--   CHECK ((order_type NOT IN ('LIMIT', 'STOP_LIMIT')) OR (price IS NOT NULL));

-- Update existing records with proper order_type based on price presence
-- UPDATE open_orders SET order_type = 'LIMIT' WHERE price IS NOT NULL;
-- UPDATE open_orders SET order_type = 'MARKET' WHERE price IS NULL;

COMMENT ON COLUMN open_orders.order_type IS 'Order type: MARKET, LIMIT, STOP_LIMIT, STOP_MARKET';
COMMENT ON COLUMN open_orders.stop_price IS 'Stop trigger price for STOP orders (nullable)';
COMMENT ON COLUMN open_orders.price IS 'Limit price for LIMIT orders (nullable for MARKET orders)';