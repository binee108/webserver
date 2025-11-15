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

**v3.0 업데이트 (2025-10-17)**: 타입 그룹별 독립 정렬 구현

### 타입 그룹별 독립 할당

심볼당 최대 20개 주문 = **LIMIT 그룹 10개 + STOP 그룹 10개**

#### LIMIT 그룹
- **포함 타입**: LIMIT, LIMIT_MAKER
- **정렬 기준**: `priority` → `price` → `created_at`
- **할당**: BUY 5개 + SELL 5개 = 총 10개

#### STOP 그룹 ⭐
- **포함 타입**: STOP, STOP_LIMIT, STOP_MARKET
- **정렬 기준**: `stop_price` → `created_at` (**priority 무시**)
  - **중요**: STOP_MARKET(priority=3)과 STOP_LIMIT(priority=4)을 **하나의 그룹으로 통합 정렬**
  - **STOP_BUY**: 낮은 stop_price 우선 (121000 → 125000)
  - **STOP_SELL**: 높은 stop_price 우선 (130000 → 125000)
- **할당**: BUY 5개 + SELL 5개 = 총 10개

#### 정렬 예시

**STOP_BUY 주문 (6개 입력)**:
| order_type | stop_price | priority | 선택 결과 |
|-----------|-----------|---------|----------|
| STOP_MARKET | 120000 | 3 | ✅ OpenOrder (1위) |
| STOP_MARKET | 121000 | 3 | ✅ OpenOrder (2위) |
| STOP_LIMIT | 122000 | 4 | ✅ OpenOrder (3위) |
| STOP_LIMIT | 123000 | 4 | ✅ OpenOrder (4위) |
| STOP_MARKET | 124000 | 3 | ✅ OpenOrder (5위) |
| STOP_LIMIT | 125000 | 4 | ❌ PendingOrder (6위) |

→ **priority 값(3 vs 4)과 무관하게 stop_price만으로 정렬**

**주요 개선 (v3.0)**:
- **타입 그룹별 독립**: LIMIT과 STOP이 각각 독립적인 할당량 보유
- **용량 보장**: LIMIT 10개 + STOP 10개 = 총 20개 (LIMIT 공간 보호)
- **STOP 통합 정렬**: STOP_MARKET과 STOP_LIMIT을 priority 무시하고 통합 정렬
- **명확한 우선순위**: 각 타입 그룹 내에서만 비교하여 우선순위 왜곡 방지

## 주요 컴포넌트

### 1. OrderQueueManager
**@FEAT:order-queue @COMP:service @TYPE:core**

**파일**: `web_server/app/services/trading/order_queue_manager.py`

**주요 메서드**:
- `rebalance_symbol(account_id, symbol)`: 심볼별 동적 재정렬 (핵심 알고리즘, v2.2)
- `_select_top_orders(orders, max_orders, max_stop_orders)`: 상위 N개 주문 선택 헬퍼 함수 (v2.2)
- `add_pending_order(order_data)`: PendingOrder 추가
- `promote_pending_order(pending_order_id)`: PendingOrder → OpenOrder
- `demote_open_order(open_order_id)`: OpenOrder → PendingOrder

**재정렬 알고리즘 (v2.2 - Side별 분리)**:
```python
# Step 1: OpenOrder + PendingOrder 조회 및 Side별 분리
buy_orders = []
sell_orders = []

for order in active_orders + pending_orders:
    order_dict = {
        'source': 'active' or 'pending',
        'db_record': order,
        'priority': OrderType.get_priority(order.order_type),
        'sort_price': _calculate_sort_price(order),  # 부호 변환 적용
        'created_at': order.created_at,
        'is_stop': OrderType.requires_stop_price(order.order_type)
    }
    if order.side.upper() == 'BUY':
        buy_orders.append(order_dict)
    else:
        sell_orders.append(order_dict)

# Step 2: 각 Side별 독립 정렬
buy_orders.sort(key=lambda x: (x['priority'], -x['sort_price'], x['created_at']))
sell_orders.sort(key=lambda x: (x['priority'], -x['sort_price'], x['created_at']))

# Step 3: 각 Side별 상위 N개 선택 (헬퍼 함수 사용)
max_orders_per_side = limits['max_orders_per_side']  # 예: 20
max_stop_orders_per_side = limits['max_stop_orders_per_side']  # 예: 5 (v2.3부터)

selected_buy_orders, buy_stop_count = _select_top_orders(
    buy_orders, max_orders_per_side, max_stop_orders_per_side
)
selected_sell_orders, sell_stop_count = _select_top_orders(
    sell_orders, max_orders_per_side, max_stop_orders_per_side
)

# Step 4: Sync (기존 로직 유지)
# - 하위로 밀린 OpenOrder → 취소 + PendingOrder로 이동
# - 상위로 올라온 PendingOrder → 거래소 전송
```

**v2.2 주요 개선사항**:
- **DRY 원칙**: `_select_top_orders()` 헬퍼 함수로 40+ 라인 중복 제거
- **명확한 의도**: Side별 분리로 정렬 로직 의도가 명시적으로 드러남
- **독립 제한**: Buy 20개 + Sell 20개 = 총 40개 동시 관리 가능

### 2. ExchangeLimits (v2.3 업데이트)
**@FEAT:order-queue @COMP:config @TYPE:core**

**파일**: `web_server/app/constants.py`

**주요 메서드**:
- `calculate_symbol_limit(exchange, market_type, symbol)`: 심볼별 최대 주문 수 계산

**반환값 (v2.3 - 25% STOP 할당 제한)**:
```python
{
    'max_orders': 40,              # 총 허용량 (Buy 20 + Sell 20)
    'max_orders_per_side': 20,     # 각 side별 독립 제한
    'max_stop_orders': 10,         # 총 STOP 허용량 (v2.3: 25% cap 적용)
    'max_stop_orders_per_side': 5  # 각 side별 STOP 제한 (v2.3: 25% cap)
}
```

**거래소별 제한 (BINANCE FUTURES 예시)**:
| 항목 | v2.0 | v2.2 | v2.3 (2025-10-16) | 변화 |
|------|------|------|-------------------|------|
| max_orders | 20 (총합) | 40 (총합) | 40 (총합) | +100% (v2.2) |
| max_orders_per_side | - | 20 (각 side) | 20 (각 side) | 신규 (v2.2) |
| max_stop_orders | - | 20 (총합) | **10 (총합)** | **-50% (v2.3)** |
| max_stop_orders_per_side | - | 10 (각 side) | **5 (각 side)** | **25% cap (v2.3)** |
| Buy 할당 | 0-20 (공유) | 0-20 (독립) | 0-20 (독립) | 독립 보장 (v2.2) |
| Sell 할당 | 0-20 (공유) | 0-20 (독립) | 0-20 (독립) | 독립 보장 (v2.2) |

**v2.3 25% STOP 할당 정책**:
- **목적**: STOP 주문이 대기열을 독점하여 LIMIT 주문 공간을 고갈시키는 것을 방지
- **계산식**: `max_stop_per_side = min(ceil(max_orders_per_side * 0.25), exchange_conditional, max_orders_per_side)`
- **최소 보장**: `math.ceil()` 적용으로 대기열 공간이 있으면 최소 1개 STOP 주문 할당
- **예시**:
  - BINANCE FUTURES (20개/side): 5개 STOP (25%)
  - BINANCE SPOT (2개/side): 1개 STOP (50%, ceil로 인한 오버)
  - BYBIT FUTURES (20개/side): 5개 STOP (exchange conditional=10이지만 25% cap 우선)

**주요 개선**:
- **의미 명확화**: `max_orders`가 총 허용량임을 명시
- **Side별 제한**: 신규 필드로 각 side의 독립 제한 지원
- **용량 증가**: 실질적인 주문 용량 2배 증가
- **STOP 제약**: 25% cap으로 LIMIT 주문 보호

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
        self._locks_lock = threading.Lock()  # _rebalance_locks 자체를 보호

    def _get_lock(self, account_id: int, symbol: str):
        """심볼별 Lock 반환 (CANCEL_ALL과 재정렬이 공유)

        Thread-safe하게 Lock 생성 및 반환. CANCEL_ALL과 재정렬이
        동일한 Lock을 사용하여 아토믹 처리 보장.

        Args:
            account_id: 계정 ID
            symbol: 심볼 (예: 'BTC/USDT')

        Returns:
            threading.Lock: 해당 심볼의 Lock
        """
        lock_key = (account_id, symbol)
        with self._locks_lock:
            if lock_key not in self._rebalance_locks:
                self._rebalance_locks[lock_key] = threading.Lock()
            return self._rebalance_locks[lock_key]

    def rebalance_symbol(self, account_id: int, symbol: str):
        """심볼별 동적 재정렬"""
        lock = self._get_lock(account_id, symbol)
        with lock:
            self._do_rebalance(account_id, symbol)
```

**효과**: 동일 (account_id, symbol) 조합에 대한 동시 재정렬 방지

### Race Condition 해결 (Issue #9)

**문제**: CANCEL_ALL 작업 중 재정렬이 끼어들어 주문 손실 발생 (18.75%)

**시나리오**:
```
Thread A (CANCEL_ALL)         Thread B (재정렬)
1. SELECT PendingOrder
2.                            1. SELECT OpenOrder
3. DELETE PendingOrder        2. SELECT PendingOrder
                              3. ... 주문 1개 손실
```

**해결 방법**: 심볼별 Lock을 CANCEL_ALL과 재정렬이 공유
- 모든 영향받는 (account_id, symbol) 조합의 Lock 획득
- Phase 1 (PendingOrder 삭제) + Phase 2 (OpenOrder 취소)를 불가분 작업으로 처리
- Deadlock 방지: 정렬된 순서 (account → symbol) Lock 획득

**구현 (order_manager.py:516-794)**:
```python
def cancel_all_orders_by_user(...):
    # Step 0: 영향받는 (account_id, symbol) 조합 파악
    pending_symbols = {(o.strategy_account.account.id, o.symbol)
                       for o in pending_orders}
    open_symbols = {(o.strategy_account.account.id, o.symbol)
                    for o in open_orders}
    affected_symbols = sorted(pending_symbols | open_symbols)

    # Step 1: 정렬된 순서로 모든 Lock 획득 (Deadlock 방지)
    with ExitStack() as stack:
        for account_id, symbol in affected_symbols:
            lock = self.queue_manager._get_lock(account_id, symbol)
            stack.enter_context(lock)

        # Step 2: Lock 내에서 아토믹 처리
        # - PendingOrder 즉시 삭제 (재정렬 대기 중 손실 방지)
        # - OpenOrder 거래소 취소 (재정렬과 동시 실행 불가)
```

**효과**: CANCEL_ALL 진행 중 재정렬이 대기 → 주문 손실 제거

## Known Issues & Counterintuitive Code

### sort_price 부호 반전 로직 (v2.2)
**이상한 점**: SELL LIMIT 주문의 sort_price는 음수(`-price`)이고, 정렬은 DESC(`-sort_price`)
**이유**: SELL은 낮은 가격 우선이지만, DESC 정렬에서는 높은 값이 앞에 옴. 부호를 반전하여 "높은 음수(= 절대값이 낮음) = 낮은 원본 가격"으로 매핑하여 의도대로 동작 보장
**참고**: `order_queue_manager.py:219-224` (`_calculate_sort_price()` 메서드)

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

## 마이그레이션 가이드 (v2.3)

### 25% STOP 할당 제한 적용 (2025-10-16)

**변경 사항**:
- BINANCE FUTURES: max_stop_per_side **10 → 5**
- BINANCE SPOT: max_stop_per_side **5 → 1**
- 기타 거래소: 25% cap 또는 exchange conditional 중 낮은 값 적용

**영향**:
- 기존 6-10개의 STOP 주문이 있는 경우, queue_rebalancer가 점진적으로 5개로 축소
- 축소 과정은 1초마다 실행되는 재정렬 로직이 자동 처리
- 우선순위가 낮은 STOP 주문부터 PendingOrder로 이동

**모니터링**:
로그에서 다음 패턴 확인:
```
🔄 재정렬 완료 - 취소: 3개, 실행: 0개
✅ 선택 완료 - BUY: 20/25개 (STOP: 5/5)
```
취소된 주문은 STOP 제한 초과로 인한 자동 조정입니다.

**롤백 방법**:
```bash
# constants.py 라인 1151 수정
STOP_ALLOCATION_RATIO = 0.50  # 25% → 50%로 변경
python run.py restart
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

*Last Updated: 2025-10-26*
*Version: 3.1.0 (Race Condition 수정)*

**v3.1.0 주요 변경사항 (2025-10-26)**:
- **Issue #9 해결**: CANCEL_ALL 작업 중 재정렬로 인한 주문 손실 (18.75%) 제거
- **심볼별 Lock 도입**: `_get_lock(account_id, symbol)` 헬퍼 메서드 추가
- **아토믹 처리**: CANCEL_ALL과 재정렬이 동일한 Lock 사용하여 불가분 작업 보장
- **Deadlock 방지**: 정렬된 순서(account → symbol) Lock 획득으로 교착 상태 방지
- 문서화: Race Condition 해결 방법 및 구현 세부사항 추가

**v3.0 주요 변경사항 (2025-10-17)**:
- **타입 그룹별 독립 정렬**: LIMIT과 STOP이 각각 독립적인 할당량 보유
  - LIMIT 그룹: BUY 5개 + SELL 5개 = 10개
  - STOP 그룹: BUY 5개 + SELL 5개 = 10개
- **STOP 통합 정렬**: STOP_MARKET(priority=3)과 STOP_LIMIT(priority=4)을 **priority 무시하고 stop_price로 통합 정렬**
- **4-way 재정렬 로직**: LIMIT_BUY, LIMIT_SELL, STOP_BUY, STOP_SELL 독립 버킷
- 목적: LIMIT 공간 보호, STOP 주문 간 명확한 우선순위

**v2.3 주요 변경사항 (2025-10-16)**:
- 25% STOP 할당 제한 적용: STOP 주문이 전체 주문의 25%를 초과하지 않도록 제한
- `STOP_ALLOCATION_RATIO = 0.25` 상수 추가 (constants.py)
- `math.ceil()` 적용으로 최소 1개 STOP 주문 보장 (대기열 공간 존재 시)
- BINANCE FUTURES: max_stop_orders_per_side 10 → 5로 변경
- BINANCE SPOT: max_stop_orders_per_side 5 → 1로 변경
- 목적: LIMIT 주문이 충분한 대기열 공간 확보, STOP 주문 독점 방지

**v2.2 주요 변경사항**:
- Buy/Sell 주문 독립 정렬 및 할당
- ExchangeLimits에 side별 제한 필드 추가 (BREAKING CHANGE)
- `_select_top_orders()` 헬퍼 함수 추가 (DRY 원칙)
- 용량 2배 증가: BINANCE FUTURES 기준 20개 → 40개
- 성능 개선: 재정렬 <100ms (효율적 O(N log N) 정렬)
- Known Issues 섹션 추가: sort_price 부호 반전 로직 문서화
