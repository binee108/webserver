# Symbol Validation Feature

> **목적**: 거래소별 심볼 제한사항을 메모리에 캐싱하고 주문 파라미터를 고속 검증하여 거래소 API 거부를 사전 방지

## 개요

### 핵심 원칙
- **메모리 기반 고속 검증**: 네트워크 요청 없이 캐시된 데이터로 즉시 검증 (< 1ms)
- **자동 파라미터 조정**: 소수점 정밀도, 최소/최대 수량, 틱 사이즈에 맞춰 자동 조정
- **백그라운드 갱신**: 매시 15분에 심볼 정보 자동 갱신 (트레이딩 중단 없음)

### 주요 이점
- 거래소 API 거부 사전 방지 (주문 전 검증)
- 성능 최적화 (메모리 기반 검증)
- 자동 조정 (소수점 계산 불필요)

---

## 실행 플로우

```
1. 서비스 시작 → load_initial_symbols() → Binance SPOT/FUTURES 로드 → market_info_cache 채움
2. 주문 검증 → validate_order_params() → 캐시 조회 → 수량/가격 조정 → 결과 반환
3. 백그라운드 갱신 (매시 15분) → DB 계좌 조회 → 심볼 갱신 → 로그 기록
```

---

## 데이터 플로우

### MarketInfo (데이터 모델)
```python
# @FEAT:symbol-validation @COMP:model @TYPE:core
@dataclass
class MarketInfo:
    symbol: str                 # 예: "BTCUSDT"
    base_asset: str            # 예: "BTC"
    quote_asset: str           # 예: "USDT"

    # LOT_SIZE 제한
    min_qty: Decimal           # 최소 주문 수량
    max_qty: Decimal           # 최대 주문 수량
    step_size: Decimal         # 수량 증분 (예: 0.001)

    # PRICE_FILTER 제한
    min_price: Decimal         # 최소 주문 가격
    max_price: Decimal         # 최대 주문 가격
    tick_size: Decimal         # 가격 증분 (예: 0.01)

    # MIN_NOTIONAL 제한
    min_notional: Decimal      # 최소 거래금액 (qty × price)
```

### 캐시 키 형식
```python
cache_key = f"{EXCHANGE}_{SYMBOL}_{MARKET_TYPE}"
# 예: "BINANCE_BTCUSDT_FUTURES"
```

---

## 주요 기능

### 1. 심볼 정보 로딩
**@FEAT:symbol-validation @COMP:service @TYPE:core**

#### 초기 로딩 (서비스 시작 시)
- Public API 사용 (계정 불필요)
- 대상: Binance SPOT, Binance FUTURES
- 실패 시: Exception (서비스 시작 중단)

#### 백그라운드 갱신
- 주기: 매시 15분 (APScheduler)
- DB 활성 계좌 사용
- 실패 시: 로그 기록 후 기존 캐시 유지

---

### 2. 주문 파라미터 검증
**@FEAT:symbol-validation @COMP:validation @TYPE:core**

#### 검증 항목
1. **수량**: min_qty/max_qty 확인, step_size로 조정 (내림)
2. **가격**: min_price/max_price 확인, tick_size로 조정 (내림)
3. **최소 거래금액**: MIN_NOTIONAL (qty × price) 확인

#### 반환값 (성공)
```python
{
    'success': True,
    'adjusted_quantity': Decimal('0.001'),
    'adjusted_price': Decimal('100000.0'),
    'min_quantity': Decimal('0.001'),
    'step_size': Decimal('0.001'),
    'min_notional': Decimal('5.0')
}
```

#### 반환값 (실패)
```python
{
    'success': False,
    'error': '최소 거래금액 미달: 4.5 < 5.0',
    'error_type': 'min_notional_error',  # 에러 타입으로 분기 처리
    'min_notional': Decimal('5.0'),
    'min_quantity': Decimal('0.001'),
    'step_size': Decimal('0.001')
}
```

---

### 3. 자동 파라미터 조정
**@FEAT:symbol-validation @COMP:service @TYPE:helper**

#### 수량 조정
```python
# 원본: 0.123456789 BTC
# step_size: 0.001
# 결과: 0.123 BTC (내림)
validation['adjusted_quantity']  # Decimal('0.123')
```

#### 가격 조정
```python
# 원본: 99999.87654321 USDT
# tick_size: 0.01
# 결과: 99999.87 USDT (내림)
validation['adjusted_price']  # Decimal('99999.87')
```

---

## 사용 예시

### Webhook Order Processing
**@FEAT:webhook-order @DEPS:symbol-validation**

```python
from app.services.symbol_validator import symbol_validator

validation = symbol_validator.validate_order_params(
    exchange='BINANCE',
    symbol='BTCUSDT',
    market_type='FUTURES',
    quantity=Decimal('0.123456789'),
    price=Decimal('99999.87654321')
)

if not validation['success']:
    raise Exception(f"검증 실패: {validation['error']}")

# 조정된 값으로 주문 생성
exchange.create_order(
    quantity=float(validation['adjusted_quantity']),
    price=float(validation['adjusted_price'])
)
```

---

## 에러 처리

### 주요 에러 타입
| error_type | 설명 | 대응 |
|-----------|------|-----|
| `symbol_not_found` | 심볼 정보 없음 | 심볼/market_type 확인 |
| `min_quantity_error` | 최소 수량 미달 | 수량 증가 또는 취소 |
| `max_quantity_error` | 최대 수량 초과 | 수량 감소 또는 분할 주문 |
| `min_notional_error` | 최소 거래금액 미달 | 수량 증가 또는 가격 조정 |
| `min_price_error` | 최소 가격 미달 | 가격 증가 |
| `max_price_error` | 최대 가격 초과 | 가격 감소 |
| `quantity_adjustment_error` | 수량 조정 실패 | 입력 데이터 확인 |
| `price_adjustment_error` | 가격 조정 실패 | 입력 데이터 확인 |
| `validation_error` | 일반 검증 실패 | 로그 확인 및 디버깅 |

### 에러 처리 예시

#### MIN_NOTIONAL 에러 처리
```python
if validation['error_type'] == 'min_notional_error':
    min_notional = validation['min_notional']
    min_quantity = validation['min_quantity']
    step_size = validation['step_size']

    # 옵션 1: 최소 수량 사용
    adjusted_qty = min_quantity

    # 옵션 2: 최소 거래금액 기준 계산
    adjusted_qty = (min_notional / price).quantize(step_size, rounding=ROUND_UP)

    # 재검증
    validation = symbol_validator.validate_order_params(...)
```

#### 가격 범위 에러 처리
```python
if validation['error_type'] == 'min_price_error':
    # 최소 가격 미달 - 가격 조정 또는 주문 취소
    logger.warning(f"가격이 너무 낮습니다: {validation['error']}")
    # 최소 가격으로 재설정 가능

elif validation['error_type'] == 'max_price_error':
    # 최대 가격 초과 - 가격 조정 또는 주문 취소
    logger.warning(f"가격이 너무 높습니다: {validation['error']}")
```

---

## 검색 가이드

### Grep 패턴
```bash
# 모든 Symbol Validation 코드
grep -r "@FEAT:symbol-validation" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:symbol-validation" --include="*.py" | grep "@TYPE:core"

# 검증 로직만
grep -r "@FEAT:symbol-validation" --include="*.py" | grep "@TYPE:validation"

# Symbol Validator 사용처
grep -r "symbol_validator.validate_order_params" --include="*.py"
```

### 주요 파일
- **핵심 서비스**: `web_server/app/services/symbol_validator.py`
- **데이터 모델**: `web_server/app/exchanges/models.py` (MarketInfo)
- **사용처**:
  - `web_server/app/services/trading/quantity_calculator.py`
  - `web_server/app/services/exchange.py`
  - `web_server/app/services/__init__.py`

---

## 의존성

### 상위 의존 (이 기능을 사용)
- `@FEAT:webhook-order` - 웹훅 주문 검증
- `@FEAT:order-queue` - 큐 주문 검증
- `@FEAT:quantity-calculator` - 수량 계산 후 검증

### 하위 의존 (이 기능이 사용)
- `@FEAT:exchange-integration` - Binance/Bybit 거래소 API
- `@FEAT:background-scheduler` - APScheduler (백그라운드 갱신)

---

## 설계 결정 히스토리

### WHY: 메모리 캐싱 방식 선택
**문제**: 매 주문마다 거래소 API 호출 시 레이턴시 증가 (100-300ms)
**결정**: 메모리 캐싱 + 백그라운드 갱신
**근거**:
- 검증 속도 < 1ms (네트워크 요청 제거)
- 심볼 정보 변경 빈도 낮음 (1시간 단위 갱신 충분)
- 메모리 사용량 적음 (1,000 심볼 ≈ 1MB)

### WHY: 내림(ROUND_DOWN) 조정 방식
**문제**: 반올림 시 max_qty 초과 또는 거래소 거부 가능
**결정**: 항상 내림 조정
**근거**:
- 거래소 거부 방지 (안전한 방향)
- 예측 가능한 동작 (항상 같거나 작게 조정)

---

## 성능 특성

- **검증 속도**: < 1ms (메모리 조회)
- **메모리 사용**: 1-5MB (1,000-5,000 심볼)
- **갱신 시간**: 5-10초 (Binance SPOT + FUTURES)

---

## 문제 해결

### 1. 심볼 정보를 찾을 수 없음
```python
# 캐시 상태 확인
stats = symbol_validator.get_cache_stats()
print(stats['total_symbols'])      # 0이면 초기화 실패
print(stats['is_initialized'])     # False면 초기화 안됨

# 수동 초기화
symbol_validator.load_initial_symbols()
```

### 2. 백그라운드 갱신 실패
- 로그 확인: `/web_server/logs/app.log`
- 활성 계좌 확인: `Account.query.filter_by(is_active=True).all()`
- 기존 캐시는 유지됨 (다음 스케줄까지 대기)

---

*Last Updated: 2025-10-12*
*Version: 2.1.0 (Error Types Expanded)*
*Changes: Added 5 additional error types (min_price_error, max_price_error, quantity_adjustment_error, price_adjustment_error, validation_error) and price range error handling examples*
