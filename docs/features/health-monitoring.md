# Health Monitoring Documentation

## Overview
Comprehensive system status monitoring for trading system reliability. Provides health checks, scheduler control, cache management, and integration testing.

**Purpose:** Enable production monitoring, orchestration platform integration (Kubernetes probes), and operational troubleshooting.

## Architecture

### Execution Flow
```
Request → Route Handler → Service Check → Response
                              ↓
                    (DB/Scheduler/Cache)
```

**Data Flow:**
1. Health checks: Query DB connection status → Return status + timestamp
2. Scheduler control: APScheduler state management → Job list/control actions
3. Cache management: Query/clear price_cache service → Statistics/confirmation
4. Integration tests: Trigger external services → Validate connectivity

## Key Components

### 1. Health Check Endpoints
| Endpoint | Purpose | Auth | Tags |
|----------|---------|------|------|
| `/health` | Basic health + DB status | Public | `@FEAT:health-monitoring @COMP:route @TYPE:core` |
| `/health/ready` | Readiness probe (K8s) | Public | `@FEAT:health-monitoring @COMP:route @TYPE:core` |
| `/health/live` | Liveness probe (K8s) | Public | `@FEAT:health-monitoring @COMP:route @TYPE:core` |
| `/api/system/health` | Minimal health (no sensitive data) | Public | `@FEAT:health-monitoring @COMP:route @TYPE:core` |

**Design Decision:** Separate endpoints for orchestration platforms vs. internal monitoring to control information exposure.

### 2. Scheduler Management (Admin Only)
- **Status Query** (`/api/system/scheduler-status`): View APScheduler state, job list, next run times
- **Job Control** (`/api/system/scheduler-control`): Start/stop/restart scheduler
- **Manual Trigger** (`/api/system/trigger-job`): Execute jobs on demand (update_orders, calculate_pnl, daily_summary)

**Tags:** `@FEAT:health-monitoring @COMP:route @TYPE:core` + `@FEAT:scheduler @COMP:service @TYPE:integration`

**Security:** Admin authentication required for all scheduler operations.

### 3. Cache Management (Admin Only)
- **Statistics** (`/api/system/cache-stats`): Hit/miss rates, entry counts, exchange list
- **Cache Clearing** (`/api/system/cache-clear`): Granular clearing by exchange/symbol/type

**Tags:** `@FEAT:health-monitoring @COMP:route @TYPE:core` + `@FEAT:price-cache @COMP:service @TYPE:integration`

### 4. Integration Testing (Admin Only)
- **Telegram Test** (`/api/system/test-telegram`): Verify notification system connectivity

**Tags:** `@FEAT:health-monitoring @COMP:route @TYPE:integration`

## API Reference

### Health Checks

#### GET /health
Basic health check with database connectivity.

**Response:**
```json
{
    "status": "healthy",
    "timestamp": "2025-10-11T12:00:00",
    "database": "healthy",
    "service": "trading-system"
}
```

#### GET /health/ready
Readiness check for orchestration platforms. Returns 503 if not ready.

**Response (Ready):** `{"status": "ready", "timestamp": "...", "checks": {"database": "ok"}}`
**Response (Not Ready):** `{"status": "not_ready", "error": "..."}` (HTTP 503)

#### GET /health/live
Liveness check for orchestration platforms.

**Response:** `{"status": "alive", "timestamp": "..."}`

#### GET /api/system/health
Minimal health check without sensitive information. Returns 503 if unhealthy.

**Response:** `{"status": "healthy|unhealthy", "timestamp": "..."}`

### Scheduler Management (Admin Only)

#### GET /api/system/scheduler-status
Query APScheduler state and registered jobs.

**Response:**
```json
{
    "success": true,
    "scheduler_running": true,
    "status": {
        "is_running": true,
        "jobs_count": 10,
        "jobs": [
            {
                "id": "update_open_orders",
                "name": "Update Open Orders Status",
                "next_run_time": "2025-10-11T12:05:00",
                "trigger": "interval[0:00:29]"
            }
        ]
    }
}
```

#### POST /api/system/scheduler-control
Control scheduler state.

**Request:** `{"action": "start|stop|restart"}`
**Response:** `{"success": true, "message": "...", "scheduler_running": true}`

#### POST /api/system/trigger-job
Manually execute background job.

**Request:** `{"job_type": "update_orders|calculate_pnl|daily_summary|calculate_performance"}`
**Response:** `{"success": true, "message": "작업 완료"}`

**Job Types:**
- `update_orders`: Update open orders status via `trading_service.update_open_orders_status()`
- `calculate_pnl`: Calculate unrealized PnL via `trading_service.calculate_unrealized_pnl()`
- `daily_summary`: Generate and send daily summary to all active accounts
- `calculate_performance`: Execute daily performance calculation

### Cache Management (Admin Only)

#### GET /api/system/cache-stats
Query cache statistics.

**Response:**
```json
{
    "success": true,
    "cache_stats": {
        "total_cached_clients": 5,
        "active_clients": 4,
        "expired_clients": 1,
        "cache_max_size": 100,
        "cache_ttl_seconds": 3600
    },
    "message": "Market 캐시를 통한 API 호출 최적화 활성화됨"
}
```

#### POST /api/system/cache-clear
Clear cache entries (price cache or exchange client cache).

**Request:** `{"exchange": "BINANCE", "market_type": "FUTURES", "type": "price|exchange|all"}`
**Response:** `{"success": true, "message": "가격 캐시 정리 완료 - 5개 항목 삭제"}`

**Cache Types:**
- `price`: Clear price cache (uses `price_cache.clear_cache()`)
- `exchange`: Clear exchange client cache (uses `exchange_service.clear_all_cache()`)
- `all`: Clear both caches

### Integration Testing (Admin Only)

#### POST /api/system/test-telegram
Test Telegram notification connectivity.

**Response:** `{"success": true, "message": "텔레그램 연결 성공"}`

## Implementation Details

### Files & Location Details

#### Health Check Endpoints
- **File**: `web_server/app/routes/health.py` (76 lines)
- **Tag**: `@FEAT:health-monitoring @COMP:route @TYPE:core`
- **Endpoints**:
  - `GET /health` (lines 14-35): Basic health + DB status
  - `GET /health/ready` (lines 38-64): Readiness probe
  - `GET /health/live` (lines 67-75): Liveness probe

#### System Management Routes
- **File**: `web_server/app/routes/system.py` (332 lines)
- **Tag**: `@FEAT:health-monitoring @COMP:route @TYPE:core` (primary)
- **Endpoints**:
  - `GET /api/system/health` (lines 16-32): Minimal health check
  - `GET /api/system/scheduler-status` (lines 57-104): APScheduler state query
  - `POST /api/system/scheduler-control` (lines 107-162): Start/stop/restart scheduler
  - `POST /api/system/trigger-job` (lines 165-232): Manual job execution
  - `GET /api/system/cache-stats` (lines 235-260): Cache statistics
  - `POST /api/system/cache-clear` (lines 263-304): Granular cache clearing
  - `GET /api/system/exchange-metadata` (lines 307-331): Futures support metadata

#### Scheduler Integration
- **File**: `web_server/app/__init__.py`
- **Purpose**: APScheduler initialization and registration of background jobs

### Quick Search
```bash
# All health monitoring code
grep -r "@FEAT:health-monitoring" --include="*.py"

# Health check routes only
grep -r "@FEAT:health-monitoring" --include="*.py" | grep "@COMP:route"

# Scheduler control logic
grep -r "@FEAT:health-monitoring" --include="*.py" | grep "scheduler"
```

## Maintenance Guidelines

### Health Checks
- **Response Time:** Must respond within 1 second
- **Error Handling:** Use appropriate HTTP status codes (200 for healthy, 503 for unhealthy)
- **Database Check:** Always validate database connectivity in readiness probe
- **Sensitive Data:** System health endpoint excludes internal details

### Scheduler Management
- **Idempotency:** Manual job triggers must support repeated execution
- **Concurrency:** Jobs use `max_instances` to prevent overlapping execution
- **Admin Only:** All scheduler control requires admin authentication

### Cache Management
- **Granular Control:** Support clearing by exchange/symbol/type
- **Performance:** Track hit/miss rates for optimization opportunities
- **Warmup:** Initial cache warmup on application startup

### Security
- Admin endpoints validate user role before execution
- Public health checks exclude sensitive system information
- Error messages sanitized to prevent information disclosure

## Usage Examples

### Kubernetes Probes
```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 5001
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 5001
  initialDelaySeconds: 10
  periodSeconds: 5
```

### Manual Job Trigger
```bash
curl -X POST https://example.com/api/system/trigger-job \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{"job_type": "update_orders"}'
```

### Cache Operations
```bash
# Query statistics
curl -X GET https://example.com/api/system/cache-stats \
  -H "Cookie: session=YOUR_SESSION_COOKIE"

# Clear price cache for specific exchange and market type
curl -X POST https://example.com/api/system/cache-clear \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{"exchange": "BINANCE", "market_type": "FUTURES", "type": "price"}'

# Clear exchange client cache
curl -X POST https://example.com/api/system/cache-clear \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{"type": "exchange"}'

# Clear all caches
curl -X POST https://example.com/api/system/cache-clear \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{"type": "all"}'
```

---
**Last Updated:** 2025-10-30
**Feature Status:** Active
**Dependencies:** APScheduler, Flask-Login, SQLAlchemy
**Sync Status:** Code-aligned (health.py 76L, system.py 332L)
