# Exchange-Agnostic STOP Order Activation Detection

## 개요

이 문서는 Issue #45에서 구현된 거래소 독립적 STOP 주문 활성화 감지 아키텍처를 설명합니다.

### 배경

STOP_LIMIT 주문은 거래소마다 다른 방식으로 활성화됩니다:
- **Binance**: order_type이 STOP_LIMIT → LIMIT으로 변환되고 stopPrice가 도달하면 활성화
- **OKX/Bybit**: 자체 상태 필드를 통해 활성화 상태를 표현

이전 방식은 Binance에만 특화되어 있어 새 거래소 추가 시 다른 프로토콜을 처리하기 어려웠습니다.

### Option C 전략 (Graceful Degradation)

Order 모델에 정규화 필드(`is_stop_order_activated`)를 추가하고:
- Exchange 계층이 거래소별 프로토콜을 감지하여 정규화 필드에 저장
- order_manager는 정규화 필드를 기반으로 비즈니스 로직 실행
- Cache miss 시 기존 로직(stopPrice 비교)으로 자동 Fallback

**핵심 장점**: 새 거래소는 Order 모델 수정 없이 Exchange 계층만 확장

---

## 아키텍처

### 3-계층 구조

```
┌─────────────────────────────────────────┐
│      order_manager (비즈니스 로직)       │
│  _handle_stop_order_activation()         │
│  → is_stop_order_activated 기반 실행    │
└──────────────────┬──────────────────────┘
                   │ 정규화된 Order 읽기
                   ▼
┌─────────────────────────────────────────┐
│      Exchange 계층 (프로토콜 감지)       │
│  _parse_order()                         │
│  → order_type_mappings (캐시)           │
│  → is_stop_order_activated 설정         │
└──────────────────┬──────────────────────┘
                   │ 정규화된 필드 저장
                   ▼
┌─────────────────────────────────────────┐
│      Order 모델 (정규화 계약)            │
│  is_stop_order_activated: bool|None     │
│  activation_detected_at: datetime|None  │
└─────────────────────────────────────────┘
```

### Phase 1: Order 모델 (데이터 계약)

**추가 필드**:

```python
class Order(BaseModel):
    # ... 기존 필드 ...

    # Exchange-agnostic 정규화 필드
    is_stop_order_activated: Optional[bool] = None
    # None: 활성화 여부 미감지 (캐시 miss)
    # True: STOP 주문이 활성화됨
    # False: STOP 주문이 여전히 미활성화됨

    activation_detected_at: Optional[datetime] = None
    # 활성화 감지 시점 (timezone aware, UTC)
```

**의미**:
- `is_stop_order_activated=True`: 주문이 활성화되었으므로 position tracking 시작
- `is_stop_order_activated=None`: 감지 실패(캐시 miss)로 fallback 로직 필요
- `activation_detected_at`: order_manager에서 활성화 시간 추적용

### Phase 2: Exchange 계층 (Binance 예시)

**1. order_type_mappings 캐시**

```python
class BinanceExchange(Exchange):
    def __init__(self):
        # STOP_LIMIT/STOP_MARKET 주문의 원본 order_type 기록
        self.order_type_mappings = {}  # {order_id: 'STOP_LIMIT'}
```

**2. create_order에서 캐시 업데이트**

```python
def create_order(self, symbol: str, side: str, order_type: str, ...):
    """주문 생성 시 STOP 타입을 캐시에 기록"""
    if order_type in ['STOP_LIMIT', 'STOP_MARKET']:
        self.order_type_mappings[order_id] = order_type
```

**3. _parse_order에서 활성화 감지**

```python
def _parse_order(self, raw_order: dict) -> Order:
    """거래소 응답 파싱 시 활성화 상태 감지"""
    order_id = raw_order['orderId']
    binance_type = raw_order['type']  # Binance order_type

    is_activated = None
    activation_detected_at = None

    # 캐시 Hit: 원본이 STOP이었고, 현재 타입이 LIMIT/MARKET면 활성화됨
    if order_id in self.order_type_mappings:
        original_type = self.order_type_mappings[order_id]
        if original_type in ['STOP_LIMIT', 'STOP_MARKET']:
            if binance_type in ['LIMIT', 'MARKET']:
                # Binance protocol: STOP_LIMIT → LIMIT 변환 = 활성화
                is_activated = True
                activation_detected_at = datetime.now(timezone.utc)

    return Order(
        order_id=order_id,
        symbol=raw_order['symbol'],
        # ... other fields ...
        is_stop_order_activated=is_activated,
        activation_detected_at=activation_detected_at
    )
```

**4. 캐시 Hit vs Miss**

| 상황 | 결과 | 작동 |
|------|------|------|
| 캐시 Hit + 타입 변환됨 | `is_activated=True` | position tracking 시작 |
| 캐시 Hit + 타입 안 변환 | `is_activated=False` | 기다림 |
| 캐시 Miss (서버 재시작) | `is_activated=None` | order_manager fallback |

### Phase 3: order_manager (비즈니스 로직)

**_handle_stop_order_activation 헬퍼**

```python
def _handle_stop_order_activation(self, order: Order) -> bool:
    """STOP 주문 활성화 감지 및 처리"""

    # 1단계: Exchange 감지 우선 (캐시 Hit)
    if order.is_stop_order_activated is not None:
        if order.is_stop_order_activated:
            self._start_position_tracking(order)
            logger.info(f"[Stop Activation] Detected via exchange - {order.order_id}")
            return True
        return False  # is_activated=False면 아직 미활성화

    # 2단계: Fallback - stopPrice 비교 (캐시 Miss)
    if order.stop_price and order.current_price >= order.stop_price:
        self._start_position_tracking(order)
        logger.info(f"[Stop Activation] Fallback detection - {order.order_id}")
        return True

    return False
```

**호출 위치**:

```python
def update_order_status(self, order: Order):
    """주기적으로 호출되는 주문 상태 업데이트"""
    fetched_order = self.exchange.fetch_order(order.order_id)

    # Exchange의 정규화 필드로 활성화 감지
    if self._handle_stop_order_activation(fetched_order):
        # position tracking 로직
        pass
```

---

## 새 거래소 추가 가이드

### 거래소 프로토콜 조사 (Step 1)

새 거래소에서 STOP_LIMIT 활성화 방식 확인:

**체크리스트**:
- [ ] STOP_LIMIT 주문 생성 시 order_type이 변환되는가?
  - Yes → Binance 유형 (캐시 방식 사용)
  - No → OKX 유형 (상태 필드 사용)
- [ ] stopPrice 필드가 유지되는가?
- [ ] 활성화 시 status 필드가 변경되는가?
- [ ] 활성화 시간을 추적할 수 있는가?

### Exchange 파일 수정 (Step 2)

**예시: OKX (상태 필드 기반)**

```python
class OKXExchange(Exchange):
    def __init__(self):
        # OKX는 상태 필드로 감지하므로 캐시 불필요
        self.original_order_types = {}  # 참고용만 유지

    def _parse_order(self, raw_order: dict) -> Order:
        """OKX: state='triggered'로 활성화 감지"""
        order_id = raw_order['ordId']
        okx_state = raw_order['state']  # 'live', 'triggered', 'filled' 등
        order_type = raw_order['ordType']  # 'limit', 'market', 'conditional' 등

        is_activated = None
        activation_detected_at = None

        # OKX protocol: conditional order가 triggered면 활성화
        if order_type == 'conditional':
            if okx_state == 'triggered':
                is_activated = True
                activation_detected_at = datetime.now(timezone.utc)
            else:
                is_activated = False

        return Order(
            order_id=order_id,
            symbol=raw_order['instId'],
            is_stop_order_activated=is_activated,
            activation_detected_at=activation_detected_at,
            # ... other fields ...
        )
```

**예시: Bybit (상태 필드 기반)**

```python
class BybitExchange(Exchange):
    def _parse_order(self, raw_order: dict) -> Order:
        """Bybit: triggerStatus='Triggered'로 활성화 감지"""
        order_id = raw_order['orderId']
        trigger_status = raw_order.get('triggerStatus')  # 'Triggered' or 'Untriggered'
        order_status = raw_order['status']  # 'New', 'PartiallyFilled' 등

        is_activated = None

        if trigger_status == 'Triggered':
            is_activated = True
        elif trigger_status == 'Untriggered':
            is_activated = False

        return Order(
            order_id=order_id,
            is_stop_order_activated=is_activated,
            # ... other fields ...
        )
```

### 테스트 시나리오 (Step 3)

**시나리오 1: 활성화 즉시 감지**

```python
# STOP_LIMIT 주문 생성
order = exchange.create_order(
    'BTC/USDT', 'buy', 'STOP_LIMIT',
    amount=1.0, price=35000, stopPrice=34500
)

# 1회차: 캐시 Hit, order_type 변환 감지
fetched = exchange.fetch_order(order.order_id)
assert fetched.is_stop_order_activated == True
```

**시나리오 2: 캐시 Miss 시 Fallback**

```python
# 서버 재시작으로 캐시 날림
exchange.order_type_mappings.clear()

# 2회차: 캐시 Miss, is_activated=None
fetched = exchange.fetch_order(order.order_id)
assert fetched.is_stop_order_activated is None

# order_manager가 stopPrice 비교로 대체
if manager._handle_stop_order_activation(fetched):
    # Fallback 성공
    assert order_manager.is_tracking(order.order_id)
```

**시나리오 3: 여러 거래소 동시 지원**

```python
# Binance (캐시 기반)
binance_order = binance.fetch_order(order_id)
assert binance_order.is_stop_order_activated == True

# OKX (상태 기반)
okx_order = okx.fetch_order(order_id)
assert okx_order.is_stop_order_activated == True

# order_manager는 동일한 로직으로 처리
assert manager._handle_stop_order_activation(binance_order)
assert manager._handle_stop_order_activation(okx_order)
```

---

## 코드 전체 구현 체크리스트

### Phase 1 완료 (Order 모델)
- [x] `is_stop_order_activated: Optional[bool] = None`
- [x] `activation_detected_at: Optional[datetime] = None`

### Phase 2 완료 (Binance Exchange)
- [x] `order_type_mappings` 캐시 추가
- [x] `create_order`에서 캐시 업데이트
- [x] `_parse_order`에서 활성화 감지

### Phase 3 완료 (order_manager)
- [x] `_handle_stop_order_activation()` 구현
- [x] Exchange 감지 우선, Fallback 자동 처리

---

## 참고 자료

**관련 파일**:
- `models/order.py` - Order 모델 정의
- `services/exchanges/binance.py` - Binance 구현
- `services/order_manager.py` - 비즈니스 로직
- `.plan/issue-45-exchange-agnostic_plan.md` - 전체 계획서

**태그로 코드 검색**:
```bash
grep -r "@FEAT:stop-limit-activation" --include="*.py"
grep -r "@COMP:exchange" --include="*.py"
grep -r "@TYPE:core" --include="*.py"
```
