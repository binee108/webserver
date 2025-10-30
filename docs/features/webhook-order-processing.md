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
| `MARKET` | ❌ 제거 | ❌ 제거 | 시장가 주문 (제공 시 경고 후 제거) |
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

### 6.4. MARKET 주문에서 price/stop_price 자동 제거
**WHY**: 거래소 API는 MARKET 주문에 price 파라미터를 허용하지 않음. 사용자 실수 방지.

**구현**:
```python
if order_type == OrderType.MARKET:
    if normalized_data.get('price'):
        logger.warning(f"⚠️ MARKET 주문에서 price는 무시됩니다")
        normalized_data.pop('price', None)
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

## 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [주문 큐 시스템](./order-queue-system.md)
- [거래소 통합](./exchange-integration.md)

---

*Last Updated: 2025-10-30 (Phase 3.1: Database & Security Enhancements)*
*Version: 3.1.0 (Phase 3.1: Error Message Sanitization + Phase 1-2: Statistics Field Consistency)*
