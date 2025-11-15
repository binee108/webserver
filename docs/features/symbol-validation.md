# Symbol Validation Feature

> **목적**: 거래소별 심볼 제한사항을 메모리에 캐싱하고 주문 파라미터를 고속 검증하여 거래소 API 거부를 사전 방지

## 개요

### 핵심 원칙
- **메모리 기반 고속 검증**: 네트워크 요청 없이 캐시된 데이터로 즉시 검증 (< 1ms)
- **자동 파라미터 조정**: 소수점 정밀도, 최소/최대 수량, 틱 사이즈에 맞춰 자동 조정
- **백그라운드 갱신**: 매시 15분에 심볼 정보 자동 갱신 (트레이딩 중단 없음)
- **거래소 확장성**: 메타데이터 기반 동적 로딩으로 새 거래소 추가 시 코드 수정 불필요

### 주요 이점
- 거래소 API 거부 사전 방지 (주문 전 검증)
- 성능 최적화 (메모리 기반 검증)
- 자동 조정 (소수점 계산 불필요)
- 확장 용이성 (하드코딩 제거)

---

## 최신 수정 (2025-10-13)

### CryptoExchangeFactory 기반 동적 로딩
**문제**: 기존 `_load_binance_public_symbols()` 하드코딩으로 인해 새 거래소 추가 시 코드 수정 필요

**해결**:
- `crypto_factory.SUPPORTED_EXCHANGES` 순회
- `ExchangeMetadata.supported_markets` 기반 market_type 자동 필터링
- 하드코딩 제거 (DRY 원칙)

**변경 내역**:
```python
# 기존 (하드코딩)
def _load_binance_public_symbols(self):
    binance = crypto_factory.create('binance', '', '', testnet=False)
    for market_type in ['spot', 'futures']:  # ❌ 하드코딩
        markets = binance.load_markets_impl(market_type)
        # ...

# 현재 (메타데이터 기반)
def load_initial_symbols(self):
    for exchange_name in crypto_factory.SUPPORTED_EXCHANGES:  # ✅ 동적 순회
        metadata = ExchangeMetadata.get_metadata(exchange_name)
        supported_markets = metadata.get('supported_markets', [])  # ✅ 메타데이터 기반

        for market_type in supported_markets:  # ✅ 자동 필터링
            markets = exchange.load_markets_impl(market_type.value)
            # ...
```

**영향**:
- ✅ Upbit SPOT 지원 (215개 심볼 로드)
- ✅ "Upbit은 Futures 지원하지 않음" 에러 제거
- ✅ 새 거래소 추가 시 코드 수정 불필요

---

## 실행 플로우

```
1. 서비스 시작 → load_initial_symbols() → 모든 거래소 순회 → market_info_cache 채움
2. 주문 검증 → validate_order_params() → 캐시 조회 → 수량/가격 조정 → 결과 반환
3. 백그라운드 갱신 (매시 15분) → DB 계좌 조회 → 심볼 갱신 → 로그 기록
```

### 초기화 플로우 (상세)
```
load_initial_symbols()
  ├─ crypto_factory.SUPPORTED_EXCHANGES 순회 (['binance', 'upbit'])
  │
  ├─ 각 거래소별:
  │   ├─ ExchangeMetadata.get_metadata(exchange_name)
  │   ├─ supported_markets 추출 (['spot', 'futures'] or ['spot'])
  │   ├─ exchange = crypto_factory.create(exchange_name, '', '', testnet=False)
  │   │
  │   └─ 각 market_type별:
  │       ├─ exchange.load_markets_impl(market_type.value, reload=True)
  │       ├─ 캐시 키 생성: f"{EXCHANGE}_{SYMBOL}_{MARKET_TYPE}"
  │       └─ market_info_cache에 저장
  │
  └─ 초기화 완료: is_initialized 플래그 설정
```

---

## 데이터 플로우

### MarketInfo (데이터 모델)
```python
# @FEAT:symbol-validation @COMP:model @TYPE:core
@dataclass
class MarketInfo:
    symbol: str                 # 예: "BTCUSDT", "BTC/KRW"
    base_asset: str            # 예: "BTC"
    quote_asset: str           # 예: "USDT", "KRW"

    # LOT_SIZE 제한
    min_qty: Decimal           # 최소 주문 수량
    max_qty: Decimal           # 최대 주문 수량
    step_size: Decimal         # 수량 증분 (예: 0.001)
    amount_precision: int      # 수량 기본 소수점 자리수 (step_size 없을 때 대체)

    # PRICE_FILTER 제한
    min_price: Decimal         # 최소 주문 가격
    max_price: Decimal         # 최대 주문 가격
    tick_size: Decimal         # 가격 증분 (예: 0.01, 1)
    price_precision: int       # 가격 기본 소수점 자리수 (tick_size 없을 때 대체)

    # MIN_NOTIONAL 제한
    min_notional: Decimal      # 최소 거래금액 (qty × price)
```

### 캐시 키 형식
```python
cache_key = f"{EXCHANGE}_{SYMBOL}_{MARKET_TYPE}"

# 예시:
# - "BINANCE_BTCUSDT_FUTURES"
# - "BINANCE_BTC/USDT_SPOT"
# - "UPBIT_BTC/KRW_SPOT"
# - "UPBIT_ETH/KRW_SPOT"
```

---

## 주요 기능

### 1. 심볼 정보 로딩
**@FEAT:symbol-validation @FEAT:exchange-integration @COMP:service @TYPE:core**

#### 초기 로딩 (서비스 시작 시)
- **방식**: Public API 사용 (계정 불필요)
- **대상**: `crypto_factory.SUPPORTED_EXCHANGES` 모든 거래소
  - Binance: SPOT, FUTURES
  - Upbit: SPOT
- **필터링**: ExchangeMetadata.supported_markets 기반 자동 필터링
- **실패 시**: Exception (서비스 시작 중단)

#### 백그라운드 갱신
**@FEAT:symbol-validation @FEAT:background-scheduler @COMP:service @TYPE:helper**

- **주기**: 매시 15분 (APScheduler)
- **방식**: DB 활성 계좌 사용
- **필터링**: 메타데이터 기반 market_type 자동 감지
- **실패 시**: 로그 기록 후 기존 캐시 유지

---

### 2. 주문 파라미터 검증
**@FEAT:symbol-validation @COMP:validation @TYPE:core**

#### 검증 플로우
```
validate_order_params()
  ├─ _validate_and_adjust_quantity()  # 수량 검증 및 소수점 조정
  │   ├─ min_qty/max_qty 범위 확인
  │   └─ step_size 또는 amount_precision으로 소수점 조정 (내림)
  ├─ _validate_and_adjust_price()     # 가격 검증 및 소수점 조정
  │   ├─ min_price/max_price 범위 확인
  │   └─ tick_size 또는 price_precision으로 소수점 조정 (내림)
  └─ min_notional 검증 (adjusted_qty × adjusted_price)
```

#### 수량 조정 로직
```python
# step_size > 0이면 step_size 기반 조정
precision = abs(step_size.as_tuple().exponent)
adjusted_quantity = quantity.quantize(
    Decimal('0.1') ** precision,
    rounding=ROUND_DOWN
)

# step_size ≤ 0이면 amount_precision 기반 조정
adjusted_quantity = quantity.quantize(
    Decimal('0.1') ** amount_precision,
    rounding=ROUND_DOWN
)
```

#### 가격 조정 로직
```python
# tick_size > 0이면 tick_size 기반 조정
precision = abs(tick_size.as_tuple().exponent)
adjusted_price = price.quantize(
    Decimal('0.1') ** precision,
    rounding=ROUND_DOWN
)

# tick_size ≤ 0이면 price_precision 기반 조정
adjusted_price = price.quantize(
    Decimal('0.1') ** price_precision,
    rounding=ROUND_DOWN
)
```

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
# Binance (tick_size: 0.01)
# 원본: 99999.87654321 USDT
# 결과: 99999.87 USDT (내림)

# Upbit (tick_size: 1)
# 원본: 150123456.789 KRW
# 결과: 150123456 KRW (내림)
```

---

## 사용 예시

### Webhook Order Processing
**@FEAT:webhook-order @DEPS:symbol-validation**

```python
from app.services.symbol_validator import symbol_validator

validation = symbol_validator.validate_order_params(
    exchange='UPBIT',
    symbol='BTC/KRW',
    market_type='SPOT',
    quantity=Decimal('0.00123456'),
    price=Decimal('150123456.789')
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

# 거래소 통합 지점
grep -r "@FEAT:symbol-validation" --include="*.py" | grep "@FEAT:exchange-integration"

# 메타데이터 기반 로딩 확인
grep -rn "ExchangeMetadata" web_server/app/services/symbol_validator.py
```

### 주요 파일 및 함수
- **핵심 서비스**:
  - `web_server/app/services/symbol_validator.py`
    - `SymbolValidator.load_initial_symbols()` (L65) - 초기 심볼 로드 (Public API)
    - `SymbolValidator.refresh_symbols()` (L57) - Flask context 래퍼 (APScheduler용)
    - `SymbolValidator._refresh_all_symbols()` (L155) - 백그라운드 갱신 (DB 계좌 사용)
    - `SymbolValidator.validate_order_params()` (L236) - 주문 파라미터 검증
    - `SymbolValidator._validate_and_adjust_quantity()` (L315) - 수량 검증 및 조정
    - `SymbolValidator._validate_and_adjust_price()` (L368) - 가격 검증 및 조정
    - `SymbolValidator.get_market_info()` (L228) - 캐시 조회 헬퍼
    - `SymbolValidator.get_cache_stats()` (L419) - 캐시 통계 조회

- **데이터 모델**:
  - `web_server/app/exchanges/models.py` - MarketInfo 클래스

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
- `@FEAT:exchange-integration` - Binance/Upbit 거래소 API
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

### WHY: CryptoExchangeFactory 기반 동적 로딩 (2025-10-13)
**문제**:
- 하드코딩된 거래소별 로딩 함수 (`_load_binance_public_symbols()`)
- 새 거래소 추가 시 코드 수정 필요
- Upbit 지원하지 않는 market_type 에러 (Futures)

**결정**:
- `crypto_factory.SUPPORTED_EXCHANGES` 순회
- `ExchangeMetadata.supported_markets` 기반 자동 필터링

**근거**:
- **DRY 원칙**: 중복 코드 제거, 단일 소스
- **확장성**: 새 거래소 추가 시 metadata만 등록
- **에러 방지**: 거래소별 지원 market_type 자동 감지
- **유지보수성**: 팩토리 패턴 활용, 일관된 구조

**영향**:
- 삭제된 메서드: `_load_binance_public_symbols()`, `_load_binance_symbols()`
- 개선된 메서드: `load_initial_symbols()`, `_refresh_all_symbols()`

---

## 성능 특성

- **검증 속도**: < 1ms (메모리 조회)
- **메모리 사용**: 1-5MB (1,000-5,000 심볼)
- **갱신 시간**: 5-10초 (Binance SPOT + FUTURES + Upbit SPOT)

---

## 문제 해결

### 1. 심볼 정보를 찾을 수 없음
```python
# 캐시 상태 확인
stats = symbol_validator.get_cache_stats()
# 반환값: {
#   'total_symbols': 1234,           # 캐시된 심볼 개수
#   'is_initialized': True,          # 초기화 완료 여부
#   'cache_keys': [...]              # 캐시 키 샘플 (처음 10개)
# }

if stats['total_symbols'] == 0:
    print("❌ 캐시가 비어있음 - 초기화 실패")

if not stats['is_initialized']:
    print("❌ 초기화되지 않음 - 서비스 미시작")

# 수동 초기화
symbol_validator.load_initial_symbols()

# 특정 심볼 확인
market_info = symbol_validator.get_market_info('UPBIT', 'BTC/KRW', 'SPOT')
if market_info:
    print(f"min_qty: {market_info.min_qty}, min_notional: {market_info.min_notional}")
else:
    print("심볼 정보 없음")
```

### 2. 백그라운드 갱신 실패
- 로그 확인: `/web_server/logs/app.log`
- 활성 계좌 확인: `Account.query.filter_by(is_active=True).all()`
- 기존 캐시는 유지됨 (다음 스케줄까지 대기)

### 3. Upbit 심볼 로드 안됨
```bash
# 메타데이터 확인
grep -rn "UPBIT.*supported_markets" web_server/app/exchanges/metadata.py

# 캐시 확인
grep -rn "UPBIT.*BTC/KRW.*SPOT" web_server/logs/app.log

# 수동 테스트
python -c "
from app.exchanges.crypto.factory import crypto_factory
from app.exchanges.metadata import ExchangeMetadata

metadata = ExchangeMetadata.get_metadata('upbit')
print(metadata.get('supported_markets'))
"
```

---

## 테스트 검증 (2025-10-13)

### Symbol Validator 테스트 결과
✅ **4/4 테스트 통과**

1. **Upbit BTC/KRW 심볼 검증**: 성공
   - min_qty: 0.00008
   - min_notional: 5000
   - tick_size: 1

2. **Upbit ETH/KRW 심볼 검증**: 성공
   - min_qty: 0.001
   - min_notional: 5000
   - tick_size: 1

3. **존재하지 않는 심볼 (SOLANA/KRW)**: 명확한 에러 메시지
   - error: "심볼 정보를 찾을 수 없습니다: UPBIT_SOLANA/KRW_SPOT"

4. **Background Job**: "Upbit은 Futures 지원하지 않음" 에러 제거 확인

---

## Known Issues

### Upbit 웹훅 주문 실행 실패 (별도 수정 예정)
**이슈**: Upbit 주문 실행 시 `'coroutine' object has no attribute 'status'` 에러

**원인**: `UpbitExchange.create_order()`가 async 메서드인데 동기 방식 호출

**상태**: Symbol Validator는 정상 작동, 실제 주문 실행만 실패

**영향**: 심볼 검증 통과, 주문 파라미터 조정 성공, 주문 실행 단계에서만 실패

**관련 파일**: `web_server/app/exchanges/crypto/upbit.py`

**수정 계획**: Upbit 거래소 구현 리팩토링 시 async 인터페이스 통일 예정

---

*Last Updated: 2025-10-30*
*Version: 2.2.1 (Documentation Sync)*
*Changes: refresh_symbols() 메서드 추가, get_cache_stats() 메서드 문서화, 캐시 통계 반환값 명확화, 문제 해결 섹션 개선*
