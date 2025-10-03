-- Phase 1: Order Tracking System Tables Migration
-- Created: 2025-01-25
-- Description: Add tables for order tracking, trade execution recording, and performance tracking

-- 1. Order Tracking Sessions Table
CREATE TABLE IF NOT EXISTS order_tracking_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    connection_type VARCHAR(20) NOT NULL,
    exchange VARCHAR(50),
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'connecting',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_ping TIMESTAMP,
    ended_at TIMESTAMP,
    error_message TEXT,
    metadata JSONB,
    
    -- Indexes
    CONSTRAINT check_connection_type CHECK (connection_type IN ('websocket', 'polling'))
);

CREATE INDEX idx_tracking_session_user ON order_tracking_sessions(user_id);
CREATE INDEX idx_tracking_session_status ON order_tracking_sessions(status);
CREATE INDEX idx_tracking_session_started ON order_tracking_sessions(started_at);

-- 2. Trade Executions Table
CREATE TABLE IF NOT EXISTS trade_executions (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER REFERENCES trades(id) ON DELETE SET NULL,
    strategy_account_id INTEGER NOT NULL REFERENCES strategy_accounts(id) ON DELETE CASCADE,
    exchange_trade_id VARCHAR(100) NOT NULL,
    exchange_order_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    execution_price FLOAT NOT NULL,
    execution_quantity FLOAT NOT NULL,
    commission FLOAT,
    commission_asset VARCHAR(20),
    execution_time TIMESTAMP NOT NULL,
    is_maker BOOLEAN,
    realized_pnl FLOAT,
    market_type VARCHAR(10) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT check_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT check_market_type CHECK (market_type IN ('SPOT', 'FUTURES'))
);

CREATE INDEX idx_trade_exec_symbol ON trade_executions(symbol);
CREATE INDEX idx_trade_exec_time ON trade_executions(execution_time);
CREATE INDEX idx_trade_exec_strategy ON trade_executions(strategy_account_id);
CREATE UNIQUE INDEX uq_exchange_trade ON trade_executions(exchange_trade_id, strategy_account_id);

-- 3. Strategy Performance Table
CREATE TABLE IF NOT EXISTS strategy_performance (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    
    -- Return metrics
    daily_return FLOAT DEFAULT 0.0 NOT NULL,
    cumulative_return FLOAT DEFAULT 0.0 NOT NULL,
    
    -- PnL metrics
    daily_pnl FLOAT DEFAULT 0.0 NOT NULL,
    cumulative_pnl FLOAT DEFAULT 0.0 NOT NULL,
    
    -- Trading statistics
    total_trades INTEGER DEFAULT 0 NOT NULL,
    winning_trades INTEGER DEFAULT 0 NOT NULL,
    losing_trades INTEGER DEFAULT 0 NOT NULL,
    win_rate FLOAT DEFAULT 0.0 NOT NULL,
    
    -- Risk metrics
    max_drawdown FLOAT DEFAULT 0.0 NOT NULL,
    sharpe_ratio FLOAT,
    sortino_ratio FLOAT,
    volatility FLOAT,
    
    -- Position statistics
    avg_position_size FLOAT,
    max_position_size FLOAT,
    active_positions INTEGER DEFAULT 0 NOT NULL,
    
    -- Commission statistics
    total_commission FLOAT DEFAULT 0.0 NOT NULL,
    commission_ratio FLOAT DEFAULT 0.0 NOT NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    UNIQUE(strategy_id, date)
);

CREATE INDEX idx_performance_date ON strategy_performance(date);
CREATE INDEX idx_performance_strategy ON strategy_performance(strategy_id);

-- 4. Tracking Logs Table
CREATE TABLE IF NOT EXISTS tracking_logs (
    id SERIAL PRIMARY KEY,
    log_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    source VARCHAR(100) NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    
    -- Log content
    message TEXT NOT NULL,
    details JSONB,
    
    -- Related entity references
    order_id VARCHAR(100),
    trade_id VARCHAR(100),
    symbol VARCHAR(20),
    
    -- Performance metrics
    execution_time_ms FLOAT,
    
    -- Timestamp
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT check_severity CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical'))
);

CREATE INDEX idx_tracking_log_type ON tracking_logs(log_type);
CREATE INDEX idx_tracking_log_severity ON tracking_logs(severity);
CREATE INDEX idx_tracking_log_created ON tracking_logs(created_at);
CREATE INDEX idx_tracking_log_user ON tracking_logs(user_id);
CREATE INDEX idx_tracking_log_symbol ON tracking_logs(symbol);
CREATE INDEX idx_tracking_log_order ON tracking_logs(order_id);

-- Add trigger to update updated_at column for strategy_performance
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_strategy_performance_updated_at 
    BEFORE UPDATE ON strategy_performance 
    FOR EACH ROW 
    EXECUTE PROCEDURE update_updated_at_column();

-- Grant permissions (adjust based on your database user)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_app_user;

-- Comments
COMMENT ON TABLE order_tracking_sessions IS 'WebSocket 연결 세션 관리';
COMMENT ON TABLE trade_executions IS '체결된 거래 상세 정보 (기존 trades 테이블 보완)';
COMMENT ON TABLE strategy_performance IS '전략별 성과 메트릭';
COMMENT ON TABLE tracking_logs IS '시스템 추적 로그';
