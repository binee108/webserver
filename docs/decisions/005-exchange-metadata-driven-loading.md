# ADR 005: Exchange Metadata-Driven Loading

## 상태
**승인됨** (2025-10-13)

## 컨텍스트

### 문제
Symbol Validator가 거래소별 심볼 정보를 로드할 때 하드코딩된 방식을 사용하여 다음과 같은 문제가 발생했습니다:

1. **확장성 문제**:
   - 새 거래소 추가 시 `_load_binance_public_symbols()` 형태의 함수를 추가로 작성해야 함
   - 각 거래소마다 중복된 로직 (DRY 원칙 위배)

2. **market_type 하드코딩**:
   ```python
   for market_type in ['spot', 'futures']:  # ❌ 하드코딩
       markets = binance.load_markets_impl(market_type)
   ```
   - Upbit은 SPOT만 지원하는데 FUTURES도 시도하여 에러 발생
   - 거래소별 지원 market_type을 수동으로 관리해야 함

3. **유지보수 부담**:
   - 거래소별 특성을 코드 여러 곳에 분산 관리
   - 변경 시 여러 파일 수정 필요

### 발견 시점
2025-10-13, Upbit 거래소 통합 작업 중 Background Job에서 "Upbit은 Futures를 지원하지 않습니다" 에러 발생

---

## 결정

### CryptoExchangeFactory + ExchangeMetadata 기반 동적 로딩 채택

#### 핵심 아이디어
1. **거래소 목록**: `crypto_factory.SUPPORTED_EXCHANGES`에서 자동 추출
2. **market_type 필터링**: `ExchangeMetadata.supported_markets`로 자동 감지
3. **통일된 로직**: 단일 순회 구조로 모든 거래소 처리

#### 구현
```python
# @FEAT:symbol-validation @FEAT:exchange-integration @COMP:service @TYPE:core
def load_initial_symbols(self):
    """
    서비스 시작 시 모든 거래소 심볼 정보 필수 로드 (Public API)

    WHY CryptoExchangeFactory 기반 동적 로딩:
    - 하드코딩 제거: 새 거래소 추가 시 코드 수정 불필요
    - 메타데이터 활용: ExchangeMetadata의 supported_markets로 market_type 자동 필터링
    - 확장성: 모든 거래소를 동일한 방식으로 처리
    """
    from app.exchanges.crypto.factory import crypto_factory
    from app.exchanges.metadata import ExchangeMetadata

    # ⭐ 기존 CryptoExchangeFactory 활용하여 모든 거래소 순회
    for exchange_name in crypto_factory.SUPPORTED_EXCHANGES:
        metadata = ExchangeMetadata.get_metadata(exchange_name)
        supported_markets = metadata.get('supported_markets', [])

        if not supported_markets:
            logger.warning(f"⚠️ {exchange_name}: 지원하는 market_type 없음 (스킵)")
            continue

        # Public API 사용 (API 키 불필요)
        exchange = crypto_factory.create(exchange_name, '', '', testnet=False)

        for market_type in supported_markets:
            markets = exchange.load_markets_impl(market_type.value, reload=True)
            # ... 캐시 저장
```

---

## 근거

### 1. DRY 원칙 (Don't Repeat Yourself)
**Before**:
```python
def _load_binance_public_symbols(self):
    binance = crypto_factory.create('binance', '', '', testnet=False)
    for market_type in ['spot', 'futures']:
        markets = binance.load_markets_impl(market_type)
        # ... 캐시 저장 로직

def _load_upbit_public_symbols(self):  # ❌ 중복 코드
    upbit = crypto_factory.create('upbit', '', '', testnet=False)
    for market_type in ['spot']:  # ❌ 하드코딩
        markets = upbit.load_markets_impl(market_type)
        # ... 동일한 캐시 저장 로직
```

**After**:
```python
def load_initial_symbols(self):
    for exchange_name in crypto_factory.SUPPORTED_EXCHANGES:  # ✅ 단일 소스
        metadata = ExchangeMetadata.get_metadata(exchange_name)
        supported_markets = metadata.get('supported_markets', [])
        # ... 통일된 로직
```

### 2. 확장성 (Scalability)
**새 거래소 추가 시 코드 수정 불필요**:
- **Before**: `_load_bybit_public_symbols()` 함수 작성 필요
- **After**: `ExchangeMetadata`에 메타데이터만 등록
  ```python
  'bybit': {
      'supported_markets': [MarketType.SPOT, MarketType.FUTURES],
      # ...
  }
  ```

### 3. 에러 방지 (Error Prevention)
**거래소별 지원 market_type 자동 감지**:
- **Before**: 수동으로 market_type 리스트 관리 → Upbit Futures 에러 발생
- **After**: 메타데이터 기반 자동 필터링 → 지원하지 않는 market_type 시도 안함

### 4. 유지보수성 (Maintainability)
**단일 소스 관리**:
- **거래소 목록**: `crypto_factory.SUPPORTED_EXCHANGES` (팩토리 패턴)
- **거래소 특성**: `ExchangeMetadata` (메타데이터 패턴)
- **로딩 로직**: `load_initial_symbols()` (단일 함수)

---

## 결과

### 긍정적 영향
1. ✅ **Upbit SPOT 지원**: 215개 심볼 로드 성공
2. ✅ **에러 제거**: "Upbit은 Futures 지원하지 않음" 에러 제거
3. ✅ **코드 간결화**: `_load_binance_public_symbols()`, `_load_binance_symbols()` 삭제
4. ✅ **확장 용이**: 새 거래소 추가 시 메타데이터만 등록

### 변경 내역
- **삭제된 메서드**:
  - `_load_binance_public_symbols()`
  - `_load_binance_symbols()`

- **개선된 메서드**:
  - `load_initial_symbols()`: crypto_factory.SUPPORTED_EXCHANGES 순회 + metadata 기반 필터링
  - `_refresh_all_symbols()`: ExchangeMetadata.supported_markets 기반 필터링

### 테스트 결과
✅ **4/4 테스트 통과** (feature-tester 검증)

1. Upbit BTC/KRW 심볼 검증: 성공
2. Upbit ETH/KRW 심볼 검증: 성공
3. 존재하지 않는 심볼 (SOLANA/KRW): 명확한 에러 메시지
4. Background Job: "Upbit은 Futures 지원하지 않음" 에러 제거 확인

---

## 고려사항

### 1. 성능 영향
**영향 없음**:
- 초기화 시간: 동일 (Public API 호출 횟수 동일)
- 메모리 사용: 동일 (캐시 구조 동일)
- 검증 속도: < 1ms (변화 없음)

### 2. 테스트 커버리지
**영향 없음**:
- 기존 테스트 모두 통과
- Symbol Validator 인터페이스 동일

### 3. 호환성
**하위 호환성 유지**:
- 캐시 키 형식 동일: `{EXCHANGE}_{SYMBOL}_{MARKET_TYPE}`
- 반환값 구조 동일
- 사용처 코드 수정 불필요

### 4. 의존성
**기존 의존성 활용**:
- `CryptoExchangeFactory`: 이미 사용 중
- `ExchangeMetadata`: 이미 정의됨
- 새로운 의존성 추가 없음

---

## 대안 고려

### 대안 1: 거래소별 함수 유지 + market_type 하드코딩 수정
**장점**:
- 변경 범위 최소화

**단점**:
- 중복 코드 유지 (DRY 원칙 위배)
- 새 거래소 추가 시 여전히 함수 작성 필요
- 장기적 유지보수 부담

**결정**: ❌ 채택하지 않음 (근본 문제 미해결)

### 대안 2: 설정 파일 기반 (JSON/YAML)
**장점**:
- 코드 변경 없이 설정 수정 가능

**단점**:
- 새로운 설정 파일 관리 필요
- ExchangeMetadata와 중복
- 타입 안정성 감소 (Enum → String)

**결정**: ❌ 채택하지 않음 (기존 메타데이터 활용이 더 적절)

### 대안 3: 메타데이터 기반 동적 로딩 (채택됨)
**장점**:
- DRY 원칙 준수
- 확장성 우수
- 타입 안정성 유지 (MarketType Enum)
- 기존 인프라 활용

**단점**:
- 초기 구조 변경 필요

**결정**: ✅ 채택 (장기적 이익 > 단기 비용)

---

## 관련 문서

- **구현 파일**: `web_server/app/services/symbol_validator.py`
- **메타데이터**: `web_server/app/exchanges/metadata.py`
- **팩토리**: `web_server/app/exchanges/crypto/factory.py`
- **Feature 문서**: `docs/features/symbol-validation.md`
- **Catalog**: `docs/FEATURE_CATALOG.md` (symbol-validation 섹션)

---

## 후속 작업

### 완료
- [x] Symbol Validator 리팩토링
- [x] Background Job 개선
- [x] 테스트 검증 (4/4 통과)
- [x] 문서화 (feature doc + ADR)

### 향후 계획
- [ ] Bybit 거래소 통합 시 동일 패턴 적용
- [ ] Upbit 주문 실행 async 인터페이스 통일 (별도 작업)

---

**승인자**: documentation-manager
**일자**: 2025-10-13
**관련 이슈**: Upbit 거래소 통합, Symbol Validator 확장성 개선
