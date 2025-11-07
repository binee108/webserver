# 웹훅 주문 처리 (Webhook Order Processing)

## 1. 개요 (Purpose)

TradingView 등 외부 시그널을 웹훅으로 수신하여 다중 계좌에 자동으로 주문을 실행하는 시스템입니다.

**핵심 기능** (Phase 4: 즉시 실행):
- 다중 계좌 동시 주문 실행 (하나의 웹훅 → 여러 계좌, 병렬 처리)
- 전략별 독립적 주문 관리 (전략 격리, DB 기반)
- 유연한 주문 타입 지원 (LIMIT, MARKET, STOP_LIMIT, STOP_MARKET)
- 배치 주문 지원 (단일 웹훅 → 여러 심볼 동시 처리, 우선순위 분류)
- **10초 타임아웃** (threading.Timer, 멀티스레드 안전)
- **증권(STOCK) 거래 지원** (크립토 병렬 처리)

---

## 2. 실행 플로우 (Execution Flow - Phase 4: 즉시 실행 + 타임아웃)

```
외부 시그널 (TradingView)
    ↓ POST /api/webhook
[1] 웹훅 수신 (webhook.py) → 10초 타임아웃 설정 (threading.Timer, 멀티스레드 안전)
    ↓ TimeoutContext.__enter__() → Timer 시작
[2] JSON 파싱 + 데이터 정규화 (webhook_service.py)
    ↓
[3] 전략 조회 및 토큰 검증 (DB 기반, 공개 전략 구독자 허용)
    ↓
[4] 주문 타입별 파라미터 검증
    ├─ LIMIT: price 필수 검증
    ├─ STOP_LIMIT: price + stop_price 필수 검증
    └─ MARKET: price/stop_price 자동 제거
    ↓
[5] 거래 타입 분기
    ├─ CANCEL_ALL_ORDER → process_cancel_all_orders() [DB 기반 취소]
    ├─ CANCEL → process_cancel_order() [개별 주문 취소]
    └─ 정상 거래 → [6]으로 진행
    ↓ (정상 거래)
[6] 배치 모드 판정 및 우선순위 분류 (Phase 4 신규)
    ├─ 단일 주문: 배치 형식으로 자동 변환
    ├─ 배치 주문: 우선순위 분류 (30개 제한)
    │   ├─ HIGH: CANCEL_ALL_ORDER + MARKET (즉시 체결)
    │   └─ LOW: LIMIT + STOP (조건부 체결)
    ↓
[7] 크립토/증권 거래소 분기 (Phase 4: 독립 트랜잭션)
    ├─ Crypto (SPOT/FUTURES):
    │   ├─ 배치1 실행 (고우선순위) → db.session.commit()
    │   ├─ 배치2 실행 (저우선순위) → db.session.commit() [배치1과 독립]
    │   └─ 병렬 처리 (ThreadPoolExecutor, max_workers=10)
    └─ Securities (STOCK): UnifiedExchangeFactory → create_order()
    ↓
[8] 결과 병합 + 타이밍 정보 수집
    ↓ TimeoutContext.__exit__() → Timer 취소
[9] 타임아웃 확인 → HTTP 200 OK + error response (타임아웃 시)
    ↓
[10] 성능 메트릭 계산 및 WebhookLog 업데이트
```

---

## 3. 데이터 플로우 (Data Flow)

**Input**:
```json
{
  "group_name": "test1",
  "token": "xxx",
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "LIMIT",
  "price": "90000",
  "qty_per": 5
}
```

**Process**:
1. 정규화 → 전략 조회 → 토큰 검증 → 파라미터 검증
2. 전략 연결 계좌 조회 (StrategyAccount)
3. 계좌별 수량 계산 (qty_per=5 → 자본의 5%)
4. 거래소 API 호출 (병렬 처리)

**Output**:
```json
{
  "action": "orders_processed",
  "strategy": "test1",
  "results": [
    {"account_name": "A1", "status": "success", "order_id": "123"},
    {"account_name": "A2", "status": "success", "order_id": "456"}
  ],
  "summary": {
    "total_accounts": 2,
    "successful_orders": 2,
    "failed_orders": 0
  },
  "performance_metrics": {
    "validation_time_ms": 12.5,
    "total_processing_time_ms": 150.3
  }
}
```

---

## 4. 주요 컴포넌트 (Components - Phase 4: 즉시 실행)

| 파일 | 역할 | 핵심 메서드 | 라인 |
|------|------|------------|------|
| `app/routes/webhook.py` | HTTP 요청 수신 + 타임아웃 | `webhook()`, `TimeoutContext` (threading.Timer) | 99-271 |
| `app/services/webhook_service.py` | 웹훅 처리 오케스트레이터 | `process_webhook()`, `_validate_strategy_token()`, `process_cancel_all_orders()`, `_process_securities_order()` | 28-1184 |
| `app/services/trading/core.py` | 거래 실행 + 배치 처리 | `execute_trade()`, `process_trading_signal()`, `process_batch_trading_signal()` | 71+ |
| `app/services/utils.py` | 데이터 정규화 | `normalize_webhook_data()` | - |
| `app/services/exchange.py` | 거래소 통합 (crpyto/stock) | `create_order()`, `cancel_order()` | - |
| `app/models` | 데이터 모델 | `WebhookLog`, `Strategy`, `StrategyAccount`, `OpenOrder`, `Trade` | - |

### Grep 검색 예시
```bash
# 웹훅 관련 모든 코드
grep -r "@FEAT:webhook-order" --include="*.py"

# 주문 실행 핵심 로직만
grep -r "@FEAT:order-execution" --include="*.py" | grep "@TYPE:core"

# 거래소 통합 코드
grep -r "@FEAT:exchange-integration" --include="*.py"
```

---

## 5. Phase 3.2: DB-first Orphan Prevention (2025-10-30)

### 목적

**Orphan Order 방지**: 거래소 API 호출 중 네트워크 단절, 서버 크래시 등으로 발생하는 고아 주문(거래소엔 있는데 DB엔 없는 주문) 방지.

**DB-first Pattern**: 거래소 API 호출 **전**에 PENDING 상태의 주문을 DB에 먼저 생성 → API 호출 → 결과에 따라 상태 업데이트.

### 새로운 주문 상태

**constants.py:818-826**

```python
PENDING = 'PENDING'              # 거래소 API 호출 전 임시 상태 (Phase 2: 2025-10-30)
FAILED = 'FAILED'                # API 실패 또는 예외 발생 (Phase 2: 2025-10-30)
```

**상태 그룹화**:
```python
get_active_statuses()      # [PENDING, NEW, OPEN, PARTIALLY_FILLED] - 백그라운드 작업용 (cleanup)
get_open_statuses_for_ui() # [NEW, OPEN, PARTIALLY_FILLED] - UI 표시용 (PENDING 제외)
```

### execute_trade() 5단계 흐름

**core.py:241-397**

```
STEP 1: Create PENDING Order (Lines 241-268)
  └─ PENDING 상태 주문 DB 저장 (exchange_order_id: PENDING-{UUID})

STEP 2: Exchange API Call (Lines 270-284)
  └─ _execute_exchange_order() 실행

STEP 3: Update PENDING → OPEN (Lines 288-319)
  └─ API 성공 시 상태 전환 + exchange_order_id 업데이트

STEP 5: Update PENDING → FAILED (Lines 321-368)
  └─ API 실패 시 상태 전환 + error_message 저장
     └─ FailedOrder 생성 (재시도 메커니즘)

STEP 5b: Exception Handling (Lines 370-397)
  └─ 예외 발생 시 PENDING → FAILED 전환 + 재발생
```

**예시 코드**:
```python
# STEP 1: DB 저장
pending_order = OpenOrder(
    status=OrderStatus.PENDING,
    exchange_order_id=f"PENDING-{uuid.uuid4().hex}"  # Unique marker
)
db.session.commit()

# STEP 2: Exchange API
order_result = self._execute_exchange_order(...)

# STEP 3: Success
if order_result.get('success'):
    order = OpenOrder.query.get(pending_order_id)
    order.status = OrderStatus.OPEN
    order.exchange_order_id = order_result.get('order_id')
    db.session.commit()
```

### Cleanup Job (고아 주문 정리)

**order_manager.py:797-854**

고장난 PENDING 주문을 120초 후 자동 FAILED로 전환.

```python
def _cleanup_stuck_pending_orders(self) -> None:
    """PENDING → FAILED (타임아웃: 120초)"""
    stuck_orders = OpenOrder.query.filter(
        OpenOrder.status == OrderStatus.PENDING,
        OpenOrder.created_at < cutoff_time  # 120초 이전
    ).all()

    for order in stuck_orders:
        order.status = OrderStatus.FAILED
        order.error_message = "Order stuck in PENDING state for >120s"
```

**호출 시점**: `update_open_orders_status()` 내 정기 실행 (29초마다)

### PENDING 필터링 전략

| 위치 | 필터링 | 이유 |
|------|--------|------|
| UI 응답 | `get_open_statuses_for_ui()` (PENDING 제외) | 사용자에게 거래소 호출 대기 상태 표시 금지 |
| 백그라운드 | `get_active_statuses()` (PENDING 포함) | cleanup job이 PENDING을 모니터링해야 함 |

**검증 명령어**:
```bash
# PENDING 필터링 확인
grep -n "get_open_statuses_for_ui\|get_active_statuses" \
  web_server/app/services/trading/order_manager.py

# PENDING 상태 생성 확인
grep -n "@DATA:OrderStatus.PENDING" web_server/app/services/trading/core.py
```

---

## 5. Phase 4: 타임아웃 처리 (새로운 기능)

### 5.0. TimeoutContext (threading.Timer 기반)

**파일**: `app/routes/webhook.py:55-94`

웹훅 처리의 10초 타임아웃을 구현합니다 (Phase 4 신규).

**메커니즘**:
```python
with TimeoutContext(10) as timeout_ctx:
    result = webhook_service.process_webhook(data, webhook_received_at)
    if timeout_ctx.timed_out:
        return create_success_response(
            data={'success': False, 'error': '...', 'timeout': True},
            message='웹훅 타임아웃'
        )
```

**특징**:
- `threading.Timer` 사용 (signal.alarm 대체, 멀티스레드 안전)
- Flask 워커 스레드에서 정상 작동
- 크로스 플랫폼 지원 (Windows/Unix)
- HTTP 200 OK 응답 (TradingView 재전송 방지)

**배경**:
- Phase 3: signal.alarm() → Flask 워커 스레드에서 작동 불가 (ValueError)
- Phase 4: threading.Timer → 멀티스레드 환경에서 정상 작동

---

### 5.1. 배치 우선순위 분류 (Phase 4 신규)

**파일**: `app/services/webhook_service.py:241-382`

배치 주문을 우선순위별로 분류하여 독립 트랜잭션으로 처리합니다.

**분류 로직**:
```python
HIGH_PRIORITY:    CANCEL_ALL_ORDER, MARKET
                  → 즉시 체결 필수 (포지션 정리, 시장가)

LOW_PRIORITY:     LIMIT, STOP
                  → 조건부 체결 (지정가 대기, 조건부 실행)
```

**트랜잭션 패턴**:
```python
# 배치1 (고우선순위) - 독립 트랜잭션
try:
    result1 = trading_service.core.process_batch_trading_signal(...)
    db.session.commit()  # 배치1 독립 커밋
except Exception:
    db.session.rollback()  # 배치1 롤백

# 배치2 (저우선순위) - 배치1과 독립
try:
    result2 = trading_service.core.process_batch_trading_signal(...)
    db.session.commit()  # 배치2 독립 커밋
except Exception:
    db.session.rollback()  # 배치1 커밋 유지
```

**효과** (부분 실패 격리):
- 배치1 실패 → 롤백, 배치2는 계속 실행
- 배치2 실패 → 롤백, 배치1 커밋 유지 (부분 성공 보장)
- HTTP 200 OK + `{succeeded: N, failed: M}`

---

### 5.3. 전략 조회 및 토큰 검증
**파일**: `app/services/webhook_service.py:68-114`
**메서드**: `_validate_strategy_token()`

**검증 규칙**:
- 전략 소유자 토큰: 항상 허용
- 공개 전략 구독자 토큰: 전략을 구독한 사용자의 토큰도 허용
- 비공개 전략: 소유자 토큰만 허용

**에러**:
- `활성 전략을 찾을 수 없습니다: {group_name}`
- `웹훅 토큰이 유효하지 않습니다`

---

### 5.4. 주문 타입별 파라미터 검증
**파일**: `app/services/webhook_service.py:35-66`
**메서드**: `_validate_order_type_params()`

| 주문 타입 | price | stop_price | 처리 |
|-----------|-------|------------|------|
| `LIMIT` | ✅ 필수 | ❌ 불필요 | 지정가 주문 |
| `MARKET` | ✅ 선택적 | ❌ 제거 | 시장가 주문 (웹훅 가격 우선, 캐시 가격 폴백) |
| `STOP_LIMIT` | ✅ 필수 | ✅ 필수 | 스톱 리밋 주문 |

**에러**:
- `{order_type} 주문에는 price가 필수입니다`
- `{order_type} 주문에는 stop_price가 필수입니다`

---

### 5.5. 주문 취소 (CANCEL_ALL_ORDER / CANCEL)

**CANCEL_ALL_ORDER**:
- **파일**: `app/services/webhook_service.py:537-722`
- **메서드**: `process_cancel_all_orders()`
- DB 기반 전략 격리 (다른 전략 주문 미영향)
- 심볼 필터링 (symbol 파라미터, 선택적)
- Side 필터링 (side: buy/sell, 선택적)

**CANCEL**:
- **파일**: `app/services/webhook_service.py:725-830`
- **메서드**: `process_cancel_order()`
- 개별 주문 취소 (order_id 기반)

**예시**:
```json
{
  "group_name": "test1",
  "symbol": "BTC/USDT",
  "order_type": "CANCEL_ALL_ORDER",
  "token": "xxx",
  "side": "buy"  // 선택적
}
```

---

### 5.6. 증권 거래 (STOCK 시장)

**파일**: `app/services/webhook_service.py:832-1127`

증권 거래소 주문 처리 (Phase 4 신규):
- **생성**: `_process_securities_order()` (861-992줄)
- **취소**: `_cancel_securities_orders()` (995-1127줄)

특징:
- UnifiedExchangeFactory로 증권 어댑터 생성
- Trade + OpenOrder 테이블 DB 저장
- SSE 이벤트 발행 (`_emit_order_event()`)

---

### 5.7. 포지션 청산 (qty_per=-100)
**파일**: `app/services/trading/quantity_calculator.py`
**메서드**: `calculate_order_quantity()`

**로직**:
- `qty_per=-100` → 포지션 100% 청산
- `qty_per=5` → 자본의 5% 배분

**에러**:
- `보유한 롱 포지션이 없습니다.` (qty_per=-100, side=SELL 시 롱 포지션 없음)
- `보유한 숏 포지션이 없습니다.` (qty_per=-100, side=BUY 시 숏 포지션 없음)

---

### 5.8. 배치 주문 (Phase 4: 우선순위 분류)
**파일**: `app/services/webhook_service.py:228-382`

**입력 형식**:
```json
{
  "group_name": "test1",
  "token": "xxx",
  "orders": [
    {"symbol": "BTC/USDT", "side": "buy", "order_type": "LIMIT", "price": "90000", "qty_per": 5},
    {"symbol": "ETH/USDT", "side": "sell", "order_type": "MARKET", "qty_per": 10}
  ]
}
```

**처리** (Phase 4):
- 단일 주문 → 배치 형식으로 자동 변환
- 배치 크기 제한: 30개 (10초 안전 마진)
- 우선순위 분류 (고/저):
  - HIGH: CANCEL_ALL_ORDER, MARKET
  - LOW: LIMIT, STOP
- 배치1 실행 → db.session.commit()
- 배치2 실행 → db.session.commit() (배치1과 독립)
- 계좌별 병렬 처리 (ThreadPoolExecutor, max_workers=10)

---

## 6. 설계 결정 히스토리 (Design Decisions)

### 6.0. Threading.Timer vs signal.alarm (Phase 4 신규)

**WHY**: Phase 3에서 signal.alarm()이 Flask 워커 스레드에서 작동하지 않아 ValueError 발생.

**선택**:
```python
# ❌ Phase 3: signal.alarm() (멀티스레드 환경 비호환)
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(10)  # ValueError: signal only works in main thread

# ✅ Phase 4: threading.Timer (멀티스레드 안전)
timer = threading.Timer(10, timeout_callback)
timer.start()  # 모든 스레드에서 작동
```

**효과**: 크로스 플랫폼 (Windows/Unix) 지원, 멀티스레드 안전

---

### 6.1. 배치 우선순위 분류 + 독립 트랜잭션 (Phase 4 신규)

**WHY**: 배치 주문에서 일부 실패 시 다른 주문도 함께 롤백되는 문제 해결.

**선택**:
```python
# ❌ Phase 3: 단일 트랜잭션
try:
    for order in orders:
        process(order)
    db.session.commit()  # 하나 실패 → 모두 롤백

# ✅ Phase 4: 배치별 독립 트랜잭션
try:
    for order in high_priority:
        process(order)
    db.session.commit()  # 배치1 독립

try:
    for order in low_priority:
        process(order)
    db.session.commit()  # 배치2 독립, 배치1과 무관
```

**효과**: 부분 성공 보장 (배치1 성공 + 배치2 실패 가능)

---

### 6.2. DB 기반 주문 조회 (CANCEL_ALL_ORDER)
**WHY**: 거래소 API는 전략 개념이 없어 모든 주문을 반환함. DB 기반 조회로 전략 격리 보장.

**구현**:
```python
# ❌ 거래소 API (전략 격리 불가)
orders = exchange.fetch_open_orders(symbol)

# ✅ DB 기반 (전략 격리)
orders = OpenOrder.query.filter_by(strategy_id=strategy.id, symbol=symbol).all()
```

---

### 6.3. 단일 주문 → 배치 형식 자동 변환
**WHY**: Trading Service는 배치 처리만 지원. 웹훅 서비스에서 단일 주문을 배치 형식으로 변환.

**구현**:
```python
# 단일 주문 입력
normalized_data = {"symbol": "BTC/USDT", "side": "buy", ...}

# 배치 형식으로 변환 (Phase 4)
if 'orders' not in normalized_data:
    normalized_data['orders'] = [normalized_data.copy()]

# Trading Service 호출
result = trading_service.core.process_trading_signal(normalized_data, timing_context)
```

---

### 6.4. MARKET 주문에서 stop_price 제거 및 price 유지 (2025-11-07 변경)
**WHY**: 웹훅에서 제공한 가격을 수량 계산에 활용하기 위해 price는 유지하되, 거래소 API 비호환 필드인 stop_price만 제거합니다.

**구현**:
```python
if order_type == OrderType.MARKET:
    if normalized_data.get('stop_price'):
        logger.warning(f"⚠️ MARKET 주문에서 stop_price는 무시됩니다")
        normalized_data.pop('stop_price', None)

    # price 필드 유지 (제거하지 않음)
    if normalized_data.get('price'):
        logger.info(f"💰 MARKET 주문: 웹훅 제공 price 사용 예정 (수량 계산용)")
    else:
        logger.debug(f"📊 MARKET 주문: price 미제공, 로컬 캐시 가격 사용 예정")
```

---

## 7. 성능 최적화

### 7.1. 병렬 처리 (ThreadPoolExecutor)
**적용 위치**: `trading/core.py:process_orders()`

```python
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(self._process_single_order, account, order)
               for account in active_accounts]
    results = [f.result() for f in futures]
```

**효과**: 계좌별 주문 실행 시간 단축 (N개 계좌 × 순차 → 병렬)

---

### 7.2. 가격 캐싱
**적용 위치**: `services/price_cache.py`

```python
price = price_cache.get_cached_price(symbol, exchange)
if price is None:
    price = exchange.fetch_ticker(symbol)['last']
    price_cache.set_cached_price(symbol, exchange, price)
```

**효과**: 거래소 API 호출 횟수 감소, Rate Limit 리스크 완화

---

### 7.3. 성능 메트릭 추적
**WebhookLog 테이블 기록**:
- `validation_time_ms`: 웹훅 검증 시간
- `preprocessing_time_ms`: 전처리 시간
- `trade_processing_time_ms`: 거래 실행 시간
- `total_processing_time_ms`: 전체 처리 시간

---

## 8. 에러 처리

| 에러 메시지 | 원인 | 해결 방법 |
|------------|------|----------|
| `활성 전략을 찾을 수 없습니다` | 전략 미존재 또는 비활성화 | 전략 생성 또는 `is_active=True` 설정 |
| `웹훅 토큰이 유효하지 않습니다` | 잘못된 토큰 | 토큰 확인 (전략 소유자/구독자) |
| `LIMIT 주문에는 price가 필수입니다` | price 누락 | `price` 필드 추가 |
| `STOP_LIMIT 주문에는 stop_price가 필수입니다` | stop_price 누락 | `stop_price` 필드 추가 |
| `보유한 롱 포지션이 없습니다.` | qty_per=-100, side=SELL 시 롱 포지션 없음 | 롱 포지션 확인 후 청산 시도 |
| `보유한 숏 포지션이 없습니다.` | qty_per=-100, side=BUY 시 숏 포지션 없음 | 숏 포지션 확인 후 청산 시도 |

---

## 9. 유지보수 가이드

### 주의사항
1. **전략 격리**: 주문 조회 시 반드시 DB 기반 (`strategy_id` 필터링) 사용
2. **토큰 검증**: 공개 전략의 경우 구독자 토큰도 허용되므로 보안 주의
3. **타임스탬프 추적**: `webhook_received_at` 등 타임스탬프는 성능 분석에 필수

### 확장 포인트
1. **새 주문 타입 추가**: `_validate_order_type_params()`에 검증 로직 추가
2. **새 거래소 추가**: `exchange.py`에 어댑터 등록, `MarketType` enum 확장
3. **배치 주문 우선순위**: `priority` 필드 기반 정렬 로직 커스터마이징 가능

---

## 10. 테스트 시나리오

### 시나리오 1: LIMIT 주문 생성
```bash
curl -k -s -X POST https://localhost:5001/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"group_name": "test1", "symbol": "BTC/USDT", "order_type": "LIMIT",
       "side": "buy", "price": "90000", "qty_per": 5,
       "token": "xxx"}' | python -m json.tool
```

### 시나리오 2: 배치 주문 생성
```bash
curl -k -s -X POST https://localhost:5001/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"group_name": "test1", "token": "xxx",
       "orders": [
         {"symbol": "BTC/USDT", "side": "buy", "order_type": "LIMIT",
          "price": "90000", "qty_per": 5, "priority": 1},
         {"symbol": "ETH/USDT", "side": "sell", "order_type": "MARKET",
          "qty_per": 10, "priority": 2}
       ]}' | python -m json.tool
```

### 시나리오 3: 주문 취소
```bash
curl -k -s -X POST https://localhost:5001/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"group_name": "test1", "symbol": "BTC/USDT",
       "order_type": "CANCEL_ALL_ORDER", "token": "xxx"}' | python -m json.tool
```

### 시나리오 4: 포지션 청산
```bash
# 1. 포지션 진입
curl -k -s -X POST https://localhost:5001/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"group_name": "test1", "symbol": "BTC/USDT", "side": "buy",
       "order_type": "MARKET", "qty_per": 0.001, "token": "xxx"}' | python -m json.tool

# 2. 포지션 청산
curl -k -s -X POST https://localhost:5001/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"group_name": "test1", "symbol": "BTC/USDT", "side": "sell",
       "order_type": "MARKET", "qty_per": -100, "token": "xxx"}' | python -m json.tool
```

---

## 변경 이력 (Change Log)

### Phase 1: 생산자 필드명 통일 (2025-10-30)

**목표**: 모든 생산자의 통계 필드명을 `successful_orders` / `failed_orders`로 통일

**변경 사항**:
1. **trading/core.py:771-772** - `process_trading_signal()` 필드명 통일
   - `successful_orders`, `failed_orders` 사용 (이미 통일됨)
   - Tag 추가: `@DATA:successful_orders,failed_orders`

2. **webhook_service.py:374-375** - 배치 결과 필드명 통일
   - `successful_orders`, `failed_orders` 사용 (이미 통일됨)
   - Tag 추가: `@DATA:successful_orders,failed_orders`

**영향 범위**:
- 모든 생산자 응답 포맷 일관성 확보
- 소비자는 단일 필드명으로 데이터 접근 가능 (폴백 불필요)
- Phase 2에서 소비자 필드명 통일 완료 (2025-10-30)

**검색 패턴**:
```bash
grep -r "@DATA:successful_orders" --include="*.py"
# 결과: 4개 파일 (core.py, webhook_service.py x2, webhook.py)
```

### Phase 2: 소비자 필드명 통일 (2025-10-30)

**목표**: 모든 소비자의 필드명 파싱을 `successful_orders` / `failed_orders`로 통일

**변경 사항**:
1. **webhook_service.py:496-497** - `_analyze_trading_result()` 필드명 파싱
   - `successful_orders = summary.get('successful_orders', 0)`
   - `failed_orders = summary.get('failed_orders', 0)`
   - Tag: `@DATA:successful_orders,failed_orders - 소비자 필드명 파싱 (2025-10-30)`
   - 로그 메시지 변수명 동기화 (Lines 502, 520, 522, 527, 528, 531)

2. **webhook_service.py:322-323, 349-350** - 배치 통계 필드명 파싱
   - Batch 1: `summary1.get('successful_orders', 0)`
   - Batch 2: `summary2.get('successful_orders', 0)`
   - Tag: `@DATA:successful_orders,failed_orders - 배치 통계 (2025-10-30)`

3. **webhook.py:183-184** - HTTP 응답 필드명 파싱
   - `successful_count = summary.get('successful_orders', 0)`
   - `failed_count = summary.get('failed_orders', 0)`
   - Tag: `@DATA:successful_orders,failed_orders - HTTP 응답 (2025-10-30)`

**영향 범위**:
- 생산자(Phase 1) + 소비자(Phase 2) = 전역 일관성 완성
- 폴백 로직 불필요 (단일 필드명으로 접근 가능)
- End-to-End 일관성: trading/core.py → webhook_service.py → webhook.py

**Phase 1+2 통합 완료**:
- 생산자 2곳: `trading/core.py:773`, `webhook_service.py:376`
- 소비자 3곳: `webhook_service.py:322,349,496`, `webhook.py:183`
- 총 4개 파일, 5개 위치에 `@DATA:successful_orders,failed_orders` 태그 적용

**검증**:
```bash
grep -r "@DATA:successful_orders" --include="*.py"
# 결과: 4개 파일 발견 (전역 일관성 확보)
```

---

## Phase 3.1: Database & Security Enhancements (2025-10-30)

**목표**: 주문 실패 원인 추적 및 에러 메시지 보안 강화 (고아 주문 방지 기반 구축)

### 변경 사항

#### 1. OpenOrder 모델 확장 (`models.py:390-393`)

**추가 필드**:
```python
error_message = db.Column(db.Text, nullable=True)
# Sanitized error message from exchange API failures (max 500 chars)
```

**용도**: 거래소 API 실패 시 sanitized 에러 메시지 저장
**제약**: 최대 500자 (`sanitize_error_message()` 함수에서 제한)
**하위 호환성**: nullable=True (기존 주문 레코드 영향 없음)

#### 2. 에러 메시지 보안 함수 (`trading/core.py:71-127`)

**함수 시그니처**:
```python
def sanitize_error_message(error_msg: str, max_length: int = 500) -> str:
    """
    Remove sensitive information from error messages before DB storage.

    Security patterns:
    - API key masking (preserves first 8 chars for debugging)
    - Account number redaction (9+ digit sequences)
    - Bearer token masking (JWT/OAuth patterns)
    - Email address redaction
    - IP address partial redaction
    - 500-char truncation
    """
```

**6단계 보안 패턴**:
1. **API 키 마스킹**: `API-KEY: abc123def456` → `API-KEY: abc123***`
2. **계정 번호 제거**: `Account 123456789` → `Account [REDACTED]`
3. **Bearer 토큰 마스킹**: `bearer eyJhbGc...` → `bearer [REDACTED]`
4. **이메일 마스킹**: `support@exchange.com` → `***@***.***`
5. **IP 부분 마스킹**: `192.168.1.100` → `192.168.*.*`
6. **길이 제한**: 500자 초과 시 truncation (DB 비대화 방지)

**사용 예시**:
```python
# 거래소 API 에러
error = "API-KEY: abc123def456 invalid for account 123456789"
sanitized = sanitize_error_message(error)
# Result: "API-KEY: abc123*** invalid for account [REDACTED]"

# OpenOrder 저장
order.error_message = sanitized
db.session.commit()
```

#### 3. 데이터베이스 마이그레이션 (`migrations/20251030_add_error_message_field.py`)

**마이그레이션 특징**:
- **Idempotent upgrade**: 기존 컬럼 존재 시 스킵 (중복 실행 안전)
- **Safe downgrade**: 컬럼 제거 전 존재 여부 확인
- **PostgreSQL COMMENT**: 스키마 문서화 자동화

**적용 방법**:
```bash
# 자동 마이그레이션 (권장)
python run.py migrate

# 수동 실행
python migrations/20251030_add_error_message_field.py
```

**롤백 방법**:
```bash
python migrations/20251030_add_error_message_field.py --downgrade
```

### 영향 범위

**코드 변경**:
- `models.py`: +5 lines (error_message 필드)
- `core.py`: +75 lines (sanitize_error_message 함수)
- `migrations/`: +180 lines (마이그레이션 파일)

**보안 개선**:
- 민감 정보 유출 방지 (API 키, 계정 번호, 토큰 등)
- XSS 공격 표면 감소 (에러 메시지에 스크립트 코드 포함 불가)
- 로그 스크래핑 공격 차단 (민감 정보가 DB에만 존재)

**하위 호환성**:
- ✅ 기존 주문 레코드는 `error_message=NULL` (영향 없음)
- ✅ 기존 API 응답 형식 유지 (error_message 필드 추가만)
- ✅ 롤백 안전 (downgrade 시 컬럼 제거, 데이터 손실 없음)

### 검증 방법

```bash
# 1. 마이그레이션 적용 확인
psql -d webserver_dev -c "\d open_orders" | grep error_message

# 2. 보안 함수 테스트
python -c "
from web_server.app.services.trading.core import sanitize_error_message
result = sanitize_error_message('API-KEY: abc123def456 for account 123456789')
print(result)
# Expected: API-KEY: abc123*** for account [REDACTED]
"

# 3. Feature tags 검색
grep -r "@DATA:error_message" --include="*.py" web_server/app/
# Expected: 2 files (models.py, core.py)
```

### 다음 단계

**Phase 3.2: DB-first Pattern Implementation (예정)**:
- `execute_trade()`에서 `sanitize_error_message()` 사용
- PENDING → ACTIVE/FAILED 상태 전환 시 error_message 저장
- 백그라운드 정리 작업에서 stuck PENDING 주문 처리 (120초 timeout)
- 사용자 UI에서 PENDING 상태 필터링 (혼란 방지)

**Phase 3.2 목표**: 로직 예외로 인한 고아 주문 완전 방지
- 거래소 API 호출 **전에** DB에 PENDING 상태로 먼저 기록
- API 성공/실패에 따라 ACTIVE/FAILED로 업데이트
- 항상 DB 레코드 존재 보장 → 고아 주문 없음

---

### Phase 3.3: Database Schema for Cancel Orphan Prevention (2025-10-30)

**Feature**: `cancel-order-db-first-orphan-prevention` (Phase 1: State Management)

#### 목적
주문 취소 시 고아 주문 방지를 위한 데이터베이스 스키마 및 상태 관리 인프라 구축. 주문 생성의 `PENDING` 상태와 대칭되는 `CANCELLING` 상태를 추가하여 DB-First 패턴의 기반 마련.

#### 배경

**현재 문제점**:
- 주문 **생성**: DB-First 패턴 (PENDING → OPEN/FAILED) ✅
- 주문 **취소**: Exchange-First 패턴 (거래소 API → DB 삭제) ❌
- 패턴 불일치로 취소 시에만 고아 주문 위험 존재

**고아 주문 시나리오**:
```
1. 사용자 주문 취소 요청
2. 거래소 API 호출 → 타임아웃
3. 실제로는 취소되었지만 응답 못 받음
4. DB의 OpenOrder 그대로 유지 (고아 주문)
5. 사용자는 계속 "미체결"로 보임
```

#### 구현 내용

##### 1. CANCELLING 상태 추가

**파일**: `web_server/app/constants.py:820`

```python
class OrderStatus:
    PENDING = 'PENDING'      # @DATA:OrderStatus.PENDING - Pre-exchange API call state (order creation)
    CANCELLING = 'CANCELLING'  # @DATA:OrderStatus.CANCELLING - Pre-exchange API call state (order cancellation)
    OPEN = 'OPEN'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    # ... (기존 상태들)
```

**설계 의도**:
- **PENDING과 대칭**: 주문 생성(PENDING)과 취소(CANCELLING)의 일관된 패턴
- **임시 상태**: 거래소 API 호출 전 DB 기록용 상태
- **백그라운드 정리 대상**: `OPEN_STATUSES`에 포함되어 자동 모니터링

**상태 그룹 업데이트**:
```python
# Line 832
OPEN_STATUSES = [NEW, OPEN, PARTIALLY_FILLED, CANCELLING]  # @FEAT:cancel-order-db-first
```

**UI 필터링**:
```python
# Line 1014: get_open_statuses_for_ui()
return [cls.NEW, cls.OPEN, cls.PARTIALLY_FILLED]  # CANCELLING 제외 (임시 상태)
```

**기능 구분**:
- `get_open_statuses()`: 백그라운드 작업용 (CANCELLING 포함)
- `get_active_statuses()`: PENDING + OPEN_STATUSES (모든 활성 상태)
- `get_open_statuses_for_ui()`: UI 표시용 (PENDING, CANCELLING 제외)

##### 2. cancel_attempted_at 필드 추가

**파일**: `web_server/app/models.py:398`

```python
# @FEAT:cancel-order-db-first @COMP:model @TYPE:core
# @DATA:cancel_attempted_at - 주문 취소 시도 시각 (디버깅 및 백그라운드 정리용)
# Used for: (1) Debugging stuck CANCELLING orders, (2) Background cleanup timeout detection
cancel_attempted_at = db.Column(db.DateTime, nullable=True)
```

**용도**:
1. **타임아웃 감지**: 백그라운드 작업이 120초 초과 CANCELLING 주문을 자동 정리
2. **디버깅**: 취소 실패 원인 추적 (`error_message`와 함께 사용)
3. **모니터링**: 취소 작업 소요 시간 분석

**Nullable 설계**:
- 기존 주문 호환성 유지
- 취소 시도한 주문만 값 기록

##### 3. 데이터베이스 마이그레이션

**파일**: `web_server/migrations/20251030_add_cancelling_state.py`

**마이그레이션 내용**:
1. `cancel_attempted_at` 컬럼 추가 (timestamp without time zone, nullable)
2. PostgreSQL COMMENT 추가 (스키마 문서화)
3. 인덱스 생성: `idx_open_orders_cancelling_cleanup`
   - 컬럼: `(status, cancel_attempted_at)`
   - WHERE 조건: `status = 'CANCELLING'`
   - 용도: 백그라운드 정리 작업 쿼리 최적화

**마이그레이션 특징**:
- **Idempotent**: 재실행 안전 (`IF NOT EXISTS` 사용)
- **Downgrade 지원**: 안전한 롤백 (CANCELLING 상태 주문 존재 여부 확인)
- **안전성 검증**: 업그레이드/다운그레이드 후 컬럼 및 인덱스 검증

**실행 방법**:
```bash
# Upgrade
python migrations/20251030_add_cancelling_state.py --upgrade

# Verification
psql -d trading_system -c "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'open_orders' AND column_name = 'cancel_attempted_at';"

# Index verification
psql -d trading_system -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'open_orders' AND indexname = 'idx_open_orders_cancelling_cleanup';"

# Downgrade (if needed)
python migrations/20251030_add_cancelling_state.py --downgrade
```

#### 아키텍처 설계

##### 상태 전환 다이어그램 (Phase 2 구현 예정)

```
주문 생성 (DB-First):
  [사용자 요청] → PENDING → [거래소 API] → OPEN/FAILED

주문 취소 (DB-First - Phase 2 구현 예정):
  [사용자 요청] → CANCELLING → [거래소 API] → CANCELLED/OPEN
```

##### 대칭적 설계

| 작업 | 임시 상태 | 성공 상태 | 실패 상태 | 백그라운드 정리 |
|------|----------|----------|----------|----------------|
| 주문 생성 | PENDING | OPEN | FAILED | 120초 초과 → FAILED |
| 주문 취소 | CANCELLING | CANCELLED | OPEN (복원) | 120초 초과 → OPEN (Phase 4) |

##### 상태 필터링 전략

```python
# 백그라운드 작업 (주문 상태 업데이트, 정리 작업)
active_statuses = OrderStatus.get_active_statuses()
# → [PENDING, NEW, OPEN, PARTIALLY_FILLED, CANCELLING]

# UI 표시 (사용자에게 보이는 미체결 주문)
ui_statuses = OrderStatus.get_open_statuses_for_ui()
# → [NEW, OPEN, PARTIALLY_FILLED]
# PENDING, CANCELLING은 임시 상태로 숨김
```

#### 코드 태그

**검색 가능한 태그**:
```bash
# 모든 관련 코드 찾기
grep -r "@FEAT:cancel-order-db-first" --include="*.py"

# 컴포넌트별 검색
grep -r "@COMP:constant" --include="*.py" | grep cancel-order-db-first
grep -r "@COMP:model" --include="*.py" | grep cancel-order-db-first
grep -r "@COMP:migration" --include="*.py" | grep cancel-order-db-first

# 데이터 필드 검색
grep -r "@DATA:OrderStatus.CANCELLING" --include="*.py"
grep -r "@DATA:cancel_attempted_at" --include="*.py"
```

#### 영향 범위

**변경된 파일**:
- `constants.py`: +12 줄 (CANCELLING 상태, docstring 업데이트)
- `models.py`: +5 줄 (cancel_attempted_at 필드)
- `migrations/20251030_add_cancelling_state.py`: +184 줄 (신규)

**의존성**:
- Phase 2: Core Cancel Logic (DB-First 패턴 구현)
- Phase 3: Retry & Resilience Mechanisms (타임아웃, 재시도)
- Phase 4: Background Cleanup Job (CANCELLING 정리)

**영향받는 서비스** (Phase 2 이후):
- `order_manager.py`: 취소 로직 리팩토링
- `exchange.py`: 타임아웃 및 재시도 추가
- 백그라운드 작업: CANCELLING 정리 작업 추가

#### 테스트 전략 (Phase 1 범위)

**Unit Tests**:
```python
# test_order_status.py
def test_cancelling_in_open_statuses():
    """OPEN_STATUSES가 CANCELLING 포함"""
    assert 'CANCELLING' in OrderStatus.OPEN_STATUSES
    assert OrderStatus.get_open_statuses() == ['NEW', 'OPEN', 'PARTIALLY_FILLED', 'CANCELLING']

def test_cancelling_excluded_from_ui():
    """UI용 필터는 CANCELLING 제외"""
    ui_statuses = OrderStatus.get_open_statuses_for_ui()
    assert 'CANCELLING' not in ui_statuses
    assert ui_statuses == ['NEW', 'OPEN', 'PARTIALLY_FILLED']

def test_is_open_with_cancelling():
    """is_open()이 CANCELLING을 True로 반환"""
    assert OrderStatus.is_open('CANCELLING') is True

def test_active_statuses_includes_cancelling():
    """get_active_statuses()가 CANCELLING 포함"""
    active = OrderStatus.get_active_statuses()
    assert 'CANCELLING' in active
    assert 'PENDING' in active
```

**Migration Tests**:
```bash
# 업그레이드 테스트
python migrations/20251030_add_cancelling_state.py --upgrade
# Expected: cancel_attempted_at 컬럼, idx_open_orders_cancelling_cleanup 인덱스 생성

# 모델 검증
python -c "from app.models import OpenOrder; print(OpenOrder.cancel_attempted_at)"
# Expected: <sqlalchemy.orm.attributes.InstrumentedAttribute object>

# 다운그레이드 테스트
python migrations/20251030_add_cancelling_state.py --downgrade
# Expected: 컬럼 및 인덱스 제거
```

#### 다음 단계 (Phase 2-4)

**Phase 2: Core Cancel Logic**
- `order_manager.cancel_order()` 함수를 DB-First 패턴으로 리팩토링
- 상태 전환: CANCELLING → CANCELLED/OPEN
- 예외 처리: 하이브리드 방식 (1회 재확인 + 백그라운드)

**Phase 3: Retry & Resilience**
- 거래소 API 타임아웃 설정 (10초)
- 지수 백오프 재시도 (최대 3회: 1초, 2초, 4초)
- 재시도 가능한 오류 판별

**Phase 4: Background Cleanup**
- `_cleanup_orphan_cancelling_orders()` 함수 추가
- 120초 초과 CANCELLING 주문 자동 정리
- 거래소 상태 재확인 후 CANCELLED 또는 OPEN으로 전환

#### 참고 문서

- **주문 생성 DB-First 패턴**: `core.py:243-397`
- **백그라운드 정리 작업**: `order_manager.py:799-854` (`_cleanup_stuck_pending_orders`)
- **관련 기능**: Phase 3.1 (error_message 필드), Phase 3.2 (DB-first orphan prevention)

---

## 부록 A: 배치 모드 감지 (2025-11-03)

### ❌ 금지 사항: `batch_mode` 파생 필드 생성

**원칙**: 배치 모드는 **`'orders'` 필드 존재 여부로만 판단**합니다. 절대 `batch_mode` 같은 파생 필드를 생성하지 마세요.

**이유**:
- 단일 소스 원칙(Single Source of Truth) 위반
- 중복 데이터로 인한 불일치 위험
- 유지보수 복잡도 증가

### ✅ 올바른 구현 패턴

```python
# ✅ 올바른 방식: 'orders' 필드로 직접 판단
if 'orders' in normalized_data:
    # 배치 모드 처리
    result = trading_service.process_batch_trading_signal(normalized_data)
else:
    # 단일 주문 처리
    result = trading_service.process_trading_signal(normalized_data)
```

```python
# ❌ 잘못된 방식: 파생 필드 생성 (금지!)
batch_mode = 'orders' in normalized_data  # 중복된 정보!
if batch_mode:
    # ...
```

### 📍 코드 위치

| 파일 | 라인 | 설명 |
|------|------|------|
| `webhook_service.py` | 227-239 | 테스트 모드에서의 배치 감지 |
| `webhook_service.py` | 284-288 | 정상 모드에서의 배치 감지 |
| `webhook_service.py` | 306 | 배치 크기 체크 |

### 🔍 검색 명령어

```bash
# 배치 모드 감지 코드 찾기
grep -n "'orders' in" web_server/app/services/webhook_service.py

# 금지 패턴 확인 (결과 없어야 정상)
grep -n "batch_mode\s*=" web_server/app/services/
```

### 📜 역사적 배경

**2025-11-03 이전**: `batch_mode` 파생 필드가 `utils.py`에서 생성되어 `webhook_service.py`에서 사용됨
**문제점**: `'orders' in webhook_data`와 `batch_mode = True`가 100% 동기화되는 중복 정보
**해결**: `batch_mode` 필드를 완전히 제거하고, `'orders'` 필드 존재 여부로 직접 판단

---

## 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [주문 큐 시스템](./order-queue-system.md)
- [거래소 통합](./exchange-integration.md)

---

## 부록 A: 배치 모드 감지 (Batch Mode Detection)

### 원칙 및 구현

**단일 소스 원칙 (Single Source of Truth):**
- ❌ **금지**: `batch_mode` 파생 필드 생성
- ✅ **필수**: `'orders'` 필드 존재 여부로 직접 판단

### 코드 패턴

**위치**: `web_server/app/services/webhook_service.py`

**구현**:
```python
# @PRINCIPLE: Never create batch_mode field - check 'orders' presence directly
# @HISTORICAL: batch_mode was a redundant derived field, removed in 2025-11-03 refactoring

# 테스트 모드 검증
if 'orders' not in normalized_data:
    self._validate_order_type_params(normalized_data)

# 배치 vs 단일 라우팅
if 'orders' in normalized_data:
    result = trading_service.process_batch_trading_signal(normalized_data)
else:
    result = trading_service.process_trading_signal(normalized_data)
```

### 유지보수 주의사항

**반복 방지 (2025-11-03)**:
- `batch_mode` 필드는 `'orders'` 필드 존재 여부를 이중 표현하는 중복 파생 필드였음
- 검증과 라우팅 모두 `'orders'` 필드 존재 여부로 통일하여 제거
- 향후 수정자는 이 단일 소스 원칙을 반드시 유지할 것

**검색 명령**:
```bash
grep -r "'orders' in" web_server/app/services/webhook_service.py
```

---

*Last Updated: 2025-11-03 (부록 A: 배치 모드 감지 원칙 추가 + Phase 1: Remove batch_mode Redundancy)*
*Version: 3.2.0 (batch_mode 필드 제거, 단일 소스 원칙 강화)*
