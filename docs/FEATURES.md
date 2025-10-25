# Feature Catalog

This document catalogs all features in the trading system for quick reference and grep-based code discovery.

## Active Features

### auth-session
**Tags:** `@FEAT:auth-session`
**Components:** route, service, model
**Description:** User authentication, login, logout, session management, password management, permission control
**Files:**
- `/Users/binee/Desktop/quant/webserver/web_server/app/routes/auth.py`
- `/Users/binee/Desktop/quant/webserver/web_server/app/services/security.py` (authentication methods)
- `/Users/binee/Desktop/quant/webserver/web_server/app/models.py` (User, UserSession models)
- `/Users/binee/Desktop/quant/webserver/web_server/app/__init__.py` (password change middleware)
**Dependencies:** None
**Documentation:** `/Users/binee/Desktop/quant/webserver/docs/features/auth-session.md`

**Key Features:**
- Flask-Login based web UI authentication
- Custom session token for API authentication
- IP-based login failure tracking and blocking (5 attempts, 1 hour block)
- Password management (force change, voluntary change, min 6 chars)
- Role-based permission system (admin vs regular users)
- Webhook token management for API access
- User registration with admin approval (is_active flag)

**Endpoints:**
- `GET/POST /auth/login` - User login
- `GET /auth/logout` - User logout
- `GET/POST /auth/register` - User registration
- `GET/POST /auth/profile` - Profile management and webhook token
- `GET/POST /auth/force-change-password` - Mandatory password change
- `GET/POST /auth/change-password` - Voluntary password change
- `POST /auth/profile/test-telegram` - Telegram connection test

**Quick Search:**
```bash
# Find all authentication code
grep -r "@FEAT:auth-session" --include="*.py"

# Find core authentication logic
grep -r "@FEAT:auth-session" --include="*.py" | grep "@TYPE:core"

# Find security validation code
grep -r "@FEAT:auth-session" --include="*.py" | grep "@TYPE:validation"

# Find route handlers
grep -r "@FEAT:auth-session" --include="*.py" | grep "@COMP:route"

# Find service methods
grep -r "@FEAT:auth-session" --include="*.py" | grep "@COMP:service"

# Find password-related code
grep -r "must_change_password" --include="*.py"

# Find session management code
grep -r "session_token" --include="*.py"
```

---

### health-monitoring
**Tags:** `@FEAT:health-monitoring`
**Components:** route
**Description:** System health checks, scheduler monitoring, cache management
**Files:**
- `/Users/binee/Desktop/quant/webserver/web_server/app/routes/health.py`
- `/Users/binee/Desktop/quant/webserver/web_server/app/routes/system.py`
**Dependencies:** None
**Documentation:** `/Users/binee/Desktop/quant/webserver/docs/features/health-monitoring.md`

**Endpoints:**
- `GET /health` - Basic health check
- `GET /health/ready` - Readiness check
- `GET /health/live` - Liveness check
- `GET /api/system/health` - Minimal health check
- `GET /api/system/scheduler-status` - Query scheduler status (Admin)
- `POST /api/system/scheduler-control` - Control scheduler (Admin)
- `POST /api/system/trigger-job` - Manual job execution (Admin)
- `GET /api/system/cache-stats` - Cache statistics (Admin)
- `POST /api/system/cache-clear` - Clear cache (Admin)

**Quick Search:**
```bash
# Find all health monitoring code
grep -r "@FEAT:health-monitoring" --include="*.py"

# Find health check endpoints
grep -r "@FEAT:health-monitoring" --include="*.py" | grep "health"

# Find scheduler control code
grep -r "@FEAT:health-monitoring" --include="*.py" | grep "scheduler"

# Find cache management code
grep -r "@FEAT:health-monitoring" --include="*.py" | grep "cache"
```

---

## Exchange Integration

### Supported Exchanges

#### Crypto Exchanges

##### 1. Binance
**Tags:** `@FEAT:exchange-integration`
**Region:** Global
**Markets:** Spot, Futures
**Features:**
- ✅ Leverage trading
- ✅ Position mode (Hedge/One-way)
- ✅ Testnet support
- ✅ WebSocket real-time data
- ✅ Batch orders (native API)

**Key Specifications:**
- **Base Currency**: USDT, BUSD, BTC
- **Rate Limit**: 1200 req/min, 10 orders/sec
- **Auth**: HMAC-SHA256

**Documentation:** `/Users/binee/Desktop/quant/webserver/docs/features/exchange-integration.md`

---

##### 2. Upbit ✨ NEW
**Tags:** `@FEAT:exchange-integration`
**Region:** South Korea (Domestic)
**Markets:** Spot only
**Features:**
- ❌ No leverage
- ❌ No testnet (Real trading only)
- ✅ WebSocket real-time data
- ✅ Batch orders (sequential fallback)

**Key Specifications:**
- **Base Currency**: KRW (Korean Won)
- **Rate Limit**: 8 req/sec, 600 req/min
- **Auth**: JWT with SHA512
- **Min Order**: 5,000 KRW

**Supported Order Types:**
- ✅ LIMIT (지정가)
- ✅ MARKET (시장가)
- ❌ STOP_LIMIT (미지원)
- ❌ STOP_MARKET (미지원)

**Limitations:**
- KRW market only
- No testnet (real trading only)
- No stop orders
- Sequential batch processing (no native batch API)
- Price must be integer (no decimals)

**Symbol Format:**
- **Standard**: `BTC/KRW` (with slash)
- **Upbit API**: `KRW-BTC` (auto-converted)

**Documentation:** `/Users/binee/Desktop/quant/webserver/docs/features/upbit-integration.md`

**Files:**
- `/Users/binee/Desktop/quant/webserver/web_server/app/exchanges/crypto/upbit.py`
- `/Users/binee/Desktop/quant/webserver/web_server/app/exchanges/crypto/factory.py` (line 31)
- `/Users/binee/Desktop/quant/webserver/web_server/app/exchanges/metadata.py` (line 74-94)

**Quick Search:**
```bash
# Find Upbit implementation
grep -r "@FEAT:exchange-integration" --include="*.py" | grep -i upbit

# Find Upbit-specific code
grep -r "UpbitExchange" --include="*.py"

# Find Upbit metadata
grep -r "'upbit'" --include="*.py"
```

---

#### Securities Exchanges

##### 1. Korea Investment (KIS)
**Tags:** `@FEAT:exchange-integration`
**Region:** South Korea
**Markets:** Stock (Domestic & Overseas)
**Features:**
- ✅ Token refresh job
- ✅ Domestic stock trading
- ✅ Overseas stock trading (US, etc.)

**Key Specifications:**
- **Base Currency**: KRW, USD
- **Auth**: Token-based (auto-refresh)
- **Token Validity**: 24 hours

**Documentation:** `/Users/binee/Desktop/quant/webserver/docs/features/securities-token.md`

---

### Exchange Comparison Table

| Feature | Binance | Upbit | Korea Investment |
|---------|---------|-------|-----------------|
| **Region** | Global | South Korea | South Korea |
| **Market Type** | Spot, Futures | Spot | Stock |
| **Base Currency** | USDT, BTC | KRW | KRW, USD |
| **Leverage** | ✅ Yes | ❌ No | ❌ No |
| **Testnet** | ✅ Yes | ❌ No | ❌ No |
| **Stop Orders** | ✅ Yes | ❌ No | ✅ Yes |
| **Batch API** | ✅ Native | ⚠️ Sequential | ⚠️ Sequential |
| **Rate Limit** | 1200/min | 600/min | Varies |
| **WebSocket** | ✅ Yes | ✅ Yes | ❌ No |

---

### Exchange Selection Guide

#### Use Binance when:
- Need leverage trading (Futures)
- Need stop orders (stop-loss, take-profit)
- Testing strategies (testnet available)
- Global market access (USDT pairs)
- High-frequency trading (fast batch API)

#### Use Upbit when:
- Trading in Korean Won (KRW)
- Domestic compliance required
- Spot trading only
- High liquidity in Korea

#### Use Korea Investment when:
- Trading Korean stocks (KOSPI, KOSDAQ)
- Trading US stocks (NASDAQ, NYSE)
- Diversifying into securities

---

## Feature Search Patterns

### By Component Type
```bash
# Find all routes
grep -r "@COMP:route" --include="*.py"

# Find all services
grep -r "@COMP:service" --include="*.py"

# Find all models
grep -r "@COMP:model" --include="*.py"

# Find all exchanges
grep -r "@COMP:exchange" --include="*.py"
```

### By Logic Type
```bash
# Find core business logic
grep -r "@TYPE:core" --include="*.py"

# Find helper functions
grep -r "@TYPE:helper" --include="*.py"

# Find integrations
grep -r "@TYPE:integration" --include="*.py"

# Find validation logic
grep -r "@TYPE:validation" --include="*.py"
```

### Cross-Feature Search
```bash
# Find code that integrates multiple features
grep -r "@FEAT:" --include="*.py" | grep -c "@FEAT:" | sort -rn

# Find dependencies
grep -r "@DEPS:" --include="*.py"

# Find all authentication-related code
grep -r "@FEAT:auth-session" --include="*.py"

# Find all exchange integration code
grep -r "@FEAT:exchange-integration" --include="*.py"
```

### Multi-Feature Searches
```bash
# Find integration points between two features
grep -r "@FEAT:auth-session" --include="*.py" | grep "@FEAT:telegram-notification"

# Find all service-level core logic
grep -r "@COMP:service" --include="*.py" | grep "@TYPE:core"

# Find exchange-specific implementations
grep -r "@COMP:exchange" --include="*.py" | grep "@TYPE:crypto-implementation"
```

---

## Adding New Features

When adding a new feature to this catalog:

1. **Create Feature Documentation**: `/docs/features/{feature-name}.md`
2. **Add Entry to Catalog**: Update this file with feature details
3. **Tag All Code**: Apply `@FEAT:{feature-name}` tags to related code
4. **Document Dependencies**: List all `@DEPS:` relationships
5. **Verify Search**: Test grep patterns work correctly

**Template:**
```markdown
### {feature-name}
**Tags:** `@FEAT:{feature-name}`
**Components:** {service|route|model|validation|exchange|util|job}
**Description:** {Brief description}
**Files:**
- {absolute-path-1}
- {absolute-path-2}
**Dependencies:** {None or feature-list}
**Documentation:** `/docs/features/{feature-name}.md`

**Quick Search:**
```bash
# Search patterns specific to this feature
```
```

---

## Adding New Exchanges

When integrating a new exchange:

1. **Implement Exchange Class**: `/web_server/app/exchanges/{crypto|securities}/{exchange_name}.py`
2. **Add to Factory**: Update `/web_server/app/exchanges/{crypto|securities}/factory.py`
3. **Add Metadata**: Update `/web_server/app/exchanges/metadata.py`
4. **Create Documentation**: `/docs/features/{exchange_name}-integration.md`
5. **Update This File**: Add exchange to comparison table
6. **Tag Code**: Apply `@FEAT:exchange-integration` tags

**Required Methods:**
- `load_markets()` - Fetch market info
- `fetch_balance()` - Get account balance
- `create_order()` - Place order
- `cancel_order()` - Cancel order
- `fetch_open_orders()` - Get open orders
- `create_batch_orders()` - Batch order execution (if supported)

---

**Last Updated:** 2025-10-12
**Total Features:** 2 core + 3 exchanges
**Maintained By:** documentation-manager agent
