# 주문 큐 시스템 가이드

> **목적**: 거래소 최대 심볼 수 제한 대응을 위한 동적 우선순위 기반 주문 대기열 시스템

## 문제와 솔루션

### 문제: 거래소 제한
- **Binance FUTURES**: 최대 200개 심볼
- **Bybit**: 최대 500개 활성 주문
- **증권사**: 제한 없음

### 솔루션: 2-Tier 주문 큐
```
웹훅 수신 → 제한 확인 → [OpenOrder (거래소 전송) | PendingOrder (대기열)]
                           ↓                              ↓
                    status=NEW, exchange_order_id    priority 기반 정렬
                           └──────────┬────────────────────┘
                                      ↓
                           동적 재정렬 (1초마다)
                    - 하위 주문: OpenOrder → PendingOrder
                    - 상위 주문: PendingOrder → OpenOrder
```

## 핵심 개념

1. **OpenOrder**: 거래소 전송된 활성 주문 (exchange_order_id 존재)
2. **PendingOrder**: 대기열의 주문 (우선순위 기반 정렬)
3. **동적 재정렬**: 1초마다 우선순위 기반으로 OpenOrder ↔ PendingOrder 이동

## 우선순위 정렬 규칙

주문은 다음 순서로 정렬됩니다:

1. **priority** (낮을수록 높음, default: 999999)
2. **sort_price** (BUY: 높을수록 우선 | SELL: 낮을수록 우선)
3. **created_at** (먼저 생성된 것 우선)

## 주요 컴포넌트

### 1. OrderQueueManager
**@FEAT:order-queue @COMP:service @TYPE:core**

**파일**: `web_server/app/services/trading/order_queue_manager.py`

**주요 메서드**:
- `rebalance_symbol(account_id, symbol)`: 심볼별 동적 재정렬 (핵심 알고리즘)
- `add_pending_order(order_data)`: PendingOrder 추가
- `promote_pending_order(pending_order_id)`: PendingOrder → OpenOrder
- `demote_open_order(open_order_id)`: OpenOrder → PendingOrder
- `_get_sorted_orders(account, symbol)`: 통합 정렬된 주문 목록

**재정렬 알고리즘**:
```python
# 1. OpenOrder + PendingOrder 통합 조회 및 정렬
# 참고: OpenOrder는 priority/sort_price 없음 → getattr로 기본값 999999 사용
combined_orders = sorted(
    open_orders + pending_orders,
    key=lambda o: (
        getattr(o, 'priority', 999999),  # OpenOrder는 999999 (최하위 우선순위)
        -getattr(o, 'sort_price', 0) if o.side == 'buy' else getattr(o, 'sort_price', 0),
        getattr(o, 'created_at', datetime.min)
    )
)

# 2. 상위 N개 선택 (거래소 제한 내)
top_orders = combined_orders[:symbol_limit]
bottom_orders = combined_orders[symbol_limit:]

# 3. Sync
# - 하위 OpenOrder → 취소 + PendingOrder로 이동
# - 상위 PendingOrder → 거래소 전송
```

### 2. ExchangeLimitTracker
**@FEAT:order-queue @FEAT:exchange-integration @COMP:service @TYPE:validation**

**파일**: `web_server/app/services/trading/exchange_limit_tracker.py`

**주요 메서드**:
- `can_add_symbol(account, symbol)`: 새 심볼 추가 가능 여부
- `calculate_symbol_limit(account, symbol)`: 심볼별 최대 주문 수
- `get_current_symbols_count(account)`: 현재 활성 심볼 수

**거래소별 제한**:
| 거래소 | 최대 심볼 수 |
|--------|-------------|
| Binance FUTURES | 200 |
| Binance SPOT | 9999 (제한 없음) |
| Bybit | 500 |
| 증권사 | 9999 (제한 없음) |

### 3. QueueRebalancer
**@FEAT:order-queue @COMP:job @TYPE:core**

**파일**: `web_server/app/services/background/queue_rebalancer.py`

**역할**: 1초마다 전체 계좌-심볼 조합에 대해 재정렬 실행

**실행 로직**:
```python
def rebalance_all_symbols():
    # 1. 활성 계좌 조회
    active_accounts = Account.query.filter_by(is_active=True).all()

    # 2. OpenOrder + PendingOrder에서 (account_id, symbol) 조합 추출
    all_pairs = set(OpenOrder + PendingOrder의 account_id, symbol)

    # 3. 각 조합에 대해 재정렬 실행
    for account_id, symbol in all_pairs:
        queue_manager.rebalance_symbol(account_id, symbol)
```

## 데이터베이스 스키마

### OpenOrder 테이블
```sql
CREATE TABLE open_orders (
    id SERIAL PRIMARY KEY,
    strategy_account_id INTEGER REFERENCES strategy_accounts(id),
    exchange_order_id VARCHAR(100) UNIQUE NOT NULL,  -- 거래소 주문 ID
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'BUY' or 'SELL'
    order_type VARCHAR(20) NOT NULL DEFAULT 'LIMIT',  -- MARKET, LIMIT, STOP_LIMIT, STOP_MARKET
    price FLOAT,  -- 지정가 가격 (MARKET 주문시 null 가능)
    stop_price FLOAT,  -- Stop 가격 (STOP 주문시 필수)
    quantity FLOAT NOT NULL,  -- 주문 수량
    filled_quantity FLOAT NOT NULL DEFAULT 0.0,  -- 체결된 수량
    status VARCHAR(20) NOT NULL,  -- OPEN, PARTIALLY_FILLED, CANCELLED, FILLED (DEFAULT 없음)
    market_type VARCHAR(10) NOT NULL DEFAULT 'SPOT',  -- SPOT 또는 FUTURES
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_open_orders_account_symbol ON open_orders(strategy_account_id, symbol, status);
```

### PendingOrder 테이블
```sql
CREATE TABLE pending_orders (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id) NOT NULL,
    strategy_account_id INTEGER REFERENCES strategy_accounts(id) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- BUY, SELL
    order_type VARCHAR(20) NOT NULL,  -- LIMIT, STOP_LIMIT, STOP_MARKET
    price NUMERIC(20, 8),  -- LIMIT 가격
    stop_price NUMERIC(20, 8),  -- STOP 트리거 가격
    quantity NUMERIC(20, 8) NOT NULL,
    priority INTEGER NOT NULL,  -- OrderType.get_priority()로 __init__에서 자동 계산
    sort_price NUMERIC(20, 8),  -- 정렬용 가격 (__init__에서 자동 계산)
    market_type VARCHAR(10) NOT NULL,  -- SPOT, FUTURES
    reason VARCHAR(50) NOT NULL DEFAULT 'QUEUE_LIMIT',  -- 대기열 진입 사유
    retry_count INTEGER NOT NULL DEFAULT 0,  -- 재시도 횟수
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pending_account_symbol ON pending_orders(account_id, symbol);
CREATE INDEX idx_pending_priority_sort ON pending_orders(account_id, symbol, priority, sort_price, created_at);
CREATE INDEX idx_pending_strategy ON pending_orders(strategy_account_id);
```

**중요 참고사항**:
- **OpenOrder**는 거래소에 이미 전송된 주문이므로 `priority`와 `sort_price` 필드가 **없습니다**.
- **PendingOrder**만 대기열 관리를 위해 `priority`와 `sort_price`를 가집니다.
- `priority`와 `sort_price`는 PendingOrder 생성 시 `__init__()` 메서드에서 자동 계산됩니다:
  - `priority`: `OrderType.get_priority(order_type)`로 계산 (1-5)
  - `sort_price`: `_calculate_sort_price()` 메서드로 계산 (정렬 로직은 아래 참조)

## 동시성 제어

### threading.Lock (메모리 기반)
**@FEAT:order-queue @COMP:service @TYPE:helper**

```python
class OrderQueueManager:
    def __init__(self):
        self._rebalance_locks = {}  # (account_id, symbol) -> Lock

    def rebalance_symbol(self, account_id: int, symbol: str):
        lock_key = (account_id, symbol)
        if lock_key not in self._rebalance_locks:
            self._rebalance_locks[lock_key] = threading.Lock()

        with self._rebalance_locks[lock_key]:
            self._do_rebalance(account_id, symbol)
```

**효과**: 동일 (account_id, symbol) 조합에 대한 동시 재정렬 방지

## 트러블슈팅

### 주문이 계속 PendingOrder에 머무름
**원인**: 거래소 제한 도달 또는 스케줄러 미실행

**해결**:
```bash
# 현재 활성 심볼 수 확인
curl -k https://222.98.151.163/api/accounts/{account_id}/symbols/count

# 스케줄러 로그 확인
grep "재정렬 대상 조합" web_server/logs/app.log

# 기존 주문 취소하여 공간 확보
curl -k -X POST https://222.98.151.163/api/webhook \
  -d '{"group_name": "test1", "symbol": "OLD_SYMBOL", "order_type": "CANCEL_ALL_ORDER", ...}'
```

### 재정렬 시 주문 취소/생성 반복
**원인**: 우선순위(priority) 동일하여 sort_price가 자주 변동

**해결**: 우선순위를 명확히 구분하여 설정
```json
{
  "orders": [
    {"symbol": "BTC/USDT", "priority": 1, ...},
    {"symbol": "ETH/USDT", "priority": 2, ...},
    {"symbol": "SOL/USDT", "priority": 3, ...}
  ]
}
```

### 스케줄러 중복 실행
**원인**: Flask Reloader가 메인 프로세스와 워커 프로세스 모두 실행

**해결**: `app/__init__.py:336`에서 WERKZEUG_RUN_MAIN 체크
```python
if os.environ.get('WERKZEUG_RUN_MAIN'):
    init_scheduler(app)
```

## Quick Search

```bash
# 주문 큐 관련 코드 찾기
grep -r "@FEAT:order-queue" --include="*.py"

# 핵심 로직만 찾기
grep -r "@FEAT:order-queue" --include="*.py" | grep "@TYPE:core"

# 재정렬 알고리즘 찾기
grep -r "rebalance_symbol" --include="*.py"

# 동시성 제어 코드 찾기
grep -r "_rebalance_locks" --include="*.py"
```

## 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [웹훅 주문 처리](./webhook-order-processing.md)
- [백그라운드 스케줄러](./background-scheduler.md)
- [거래소 통합](./exchange-integration.md)

---

*Last Updated: 2025-10-12*
*Version: 2.0.1 (DB Schema Corrections - OpenOrder/PendingOrder fields aligned with actual code)*
