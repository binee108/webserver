# 웹훅 주문 처리 (Webhook Order Processing)

## 1. 개요 (Purpose)

TradingView 등 외부 시그널을 웹훅으로 수신하여 다중 계좌에 자동으로 주문을 실행하는 시스템입니다.

**핵심 기능**:
- 다중 계좌 동시 주문 실행 (하나의 웹훅 → 여러 계좌)
- 전략별 독립적 주문 관리 (전략 격리)
- 유연한 주문 타입 지원 (LIMIT, MARKET, STOP_LIMIT)
- 배치 주문 지원 (단일 웹훅 → 여러 심볼 동시 처리)

---

## 2. 실행 플로우 (Execution Flow)

```
외부 시그널 (TradingView)
    ↓ POST /api/webhook
[1] 웹훅 수신 (webhook.py) → 타임스탬프 기록
    ↓
[2] 데이터 정규화 (webhook_service.py) → 필수 필드 검증
    ↓
[3] 전략 조회 및 토큰 검증 → 권한 확인
    ↓
[4] 주문 타입별 파라미터 검증 → LIMIT: price 필수, MARKET: price 제거
    ↓
[5] 거래 타입 라우팅
    ├─ CANCEL_ALL_ORDER → process_cancel_all_orders()
    ├─ CANCEL → process_cancel_order()
    ├─ Crypto (FUTURES/SPOT) → trading_service.core.process_orders()
    └─ Securities (STOCK) → _process_securities_order()
    ↓
[6] Trading Service 주문 실행
    - 전략 연결 계좌 조회
    - 계좌별 병렬 주문 처리 (ThreadPoolExecutor)
    - 수량 계산 (qty_per, 청산 로직)
    - 거래소 API 호출 (OpenOrder/PendingOrder)
    ↓
[7] 결과 반환 및 성능 메트릭 기록 → WebhookLog 업데이트
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
    "successful_trades": 2,
    "failed_trades": 0
  },
  "performance_metrics": {
    "validation_time_ms": 12.5,
    "total_processing_time_ms": 150.3
  }
}
```

---

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `app/routes/webhook.py` | HTTP 요청 수신 | @FEAT:webhook-order @COMP:route @TYPE:core | `webhook()` |
| `app/services/webhook_service.py` | 웹훅 처리 오케스트레이터 | @FEAT:webhook-order @COMP:service @TYPE:core | `process_webhook()`, `_validate_strategy_token()`, `process_cancel_all_orders()` |
| `app/services/trading/core.py` | 거래 실행 코어 | @FEAT:webhook-order @COMP:service @TYPE:core | `process_orders()`, `execute_trade()` |
| `app/services/trading/order_manager.py` | 주문 생성/취소 | @COMP:service @TYPE:core | `create_order()`, `cancel_all_orders_by_user()`, `create_open_order_record()` |
| `app/services/trading/quantity_calculator.py` | 수량 계산 | @FEAT:capital-management @COMP:service @TYPE:helper | `calculate_order_quantity()`, `calculate_quantity_from_percentage()` |
| `app/services/trading/record_manager.py` | DB 저장 | @COMP:service @TYPE:helper | `create_trade_record()`, `create_trade_execution_record()` |
| `app/services/exchange.py` | 거래소 통합 레이어 | @FEAT:exchange-integration @COMP:exchange @TYPE:integration | `create_order()`, `cancel_order()` |

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

## 5. 주요 기능 상세

### 5.1. 전략 조회 및 토큰 검증
**파일**: `app/services/webhook_service.py`
**메서드**: `_validate_strategy_token()`

**검증 규칙**:
- 전략 소유자 토큰: 항상 허용
- 공개 전략 구독자 토큰: 전략을 구독한 사용자의 토큰도 허용
- 비공개 전략: 소유자 토큰만 허용

**에러**:
- `활성 전략을 찾을 수 없습니다: {group_name}`
- `웹훅 토큰이 유효하지 않습니다`

---

### 5.2. 주문 타입별 파라미터 검증
**파일**: `app/services/webhook_service.py`
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

### 5.3. 주문 취소 (CANCEL_ALL_ORDER)
**파일**: `app/services/webhook_service.py`
**메서드**: `process_cancel_all_orders()`

**특징**:
- DB 기반 전략 격리 (다른 전략 주문 미영향)
- 심볼 필터링 지원 (symbol 파라미터, **선택적**)
- Side 필터링 지원 (side: buy/sell, **선택적**)

**예시**:
```json
{
  "group_name": "test1",
  "symbol": "BTC/USDT",
  "order_type": "CANCEL_ALL_ORDER",
  "token": "xxx"
}
```

**참고**: symbol과 side 파라미터는 선택적입니다. 생략하면 전략의 모든 주문을 취소합니다.

---

### 5.4. 포지션 청산 (qty_per=-100)
**파일**: `app/services/trading/quantity_calculator.py`
**메서드**: `calculate_order_quantity()`

**로직**:
- `qty_per=-100` → 포지션 100% 청산
- `qty_per=5` → 자본의 5% 배분

**에러**:
- `보유한 롱 포지션이 없습니다.` (qty_per=-100, side=SELL 시 롱 포지션 없음)
- `보유한 숏 포지션이 없습니다.` (qty_per=-100, side=BUY 시 숏 포지션 없음)

---

### 5.5. 배치 주문
**파일**: `app/services/trading/core.py`
**메서드**: `process_orders()`

**입력 형식**:
```json
{
  "group_name": "test1",
  "token": "xxx",
  "orders": [
    {"symbol": "BTC/USDT", "side": "buy", "order_type": "LIMIT", "price": "90000", "qty_per": 5, "priority": 1},
    {"symbol": "ETH/USDT", "side": "sell", "order_type": "MARKET", "qty_per": 10, "priority": 2}
  ]
}
```

**처리**:
- 단일 주문 → 배치 형식으로 자동 변환 (`orders` 배열)
- 계좌별 병렬 처리 (ThreadPoolExecutor, max_workers=10)
- 우선순위 기반 정렬 (priority 필드)

---

## 6. 설계 결정 히스토리 (Design Decisions)

### 6.1. DB 기반 주문 조회 (CANCEL_ALL_ORDER)
**WHY**: 거래소 API는 전략 개념이 없어 모든 주문을 반환함. DB 기반 조회로 전략 격리 보장.

**구현**:
```python
# ❌ 거래소 API (전략 격리 불가)
orders = exchange.fetch_open_orders(symbol)

# ✅ DB 기반 (전략 격리)
orders = OpenOrder.query.filter_by(strategy_id=strategy.id, symbol=symbol).all()
```

---

### 6.2. 단일 주문 → 배치 형식 자동 변환
**WHY**: Trading Service는 배치 처리만 지원. 웹훅 서비스에서 단일 주문을 배치 형식으로 변환.

**구현**:
```python
# 단일 주문 입력
normalized_data = {"symbol": "BTC/USDT", "side": "buy", ...}

# 배치 형식으로 변환
batch_data = normalized_data.copy()
batch_data['orders'] = [normalized_data.copy()]

# Trading Service 호출
trading_service.core.process_orders(batch_data, timing_context)
```

---

### 6.3. MARKET 주문에서 price/stop_price 자동 제거
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

## 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [주문 큐 시스템](./order-queue-system.md)
- [거래소 통합](./exchange-integration.md)

---

*Last Updated: 2025-10-11*
*Version: 2.0.0 (Streamlined)*
