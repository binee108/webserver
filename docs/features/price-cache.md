# 가격 캐싱 시스템 (Price Cache)

## 1. 개요 (Purpose)

거래소 API 호출을 최소화하고 응답 속도를 개선하기 위한 메모리 기반 가격 캐싱 시스템입니다.

**해결하는 문제**:
- 네트워크 지연 (100-500ms) 제거
- API Rate Limit 절약 (Binance 기준 초당 1200건 제한)
- 동일 심볼 반복 조회 비용 감소

**성과**:
- 캐시 히트율: 95%+ (API 호출 90% 감소)
- 응답 시간: <10ms (캐시 히트), <200ms (캐시 미스)

---

## 2. 실행 플로우 (Execution Flow)

```
┌─────────────────────────────────────┐
│      클라이언트 요청                  │
│  (주문 수량 계산, PnL 계산 등)         │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   PriceCache.get_price()             │
│   TTL: 30초                          │
└────────┬───────────────┬────────────┘
         │               │
    Cache HIT        Cache MISS
    (<10ms)         (API 호출 → 캐시 갱신)
         │               │
         └───────┬───────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  백그라운드 갱신 (31초마다)            │
│  1. 전체 시장 가격 일괄 조회           │
│  2. 활성 포지션 심볼 우선 갱신         │
└─────────────────────────────────────┘
```

**주요 단계**:
1. **앱 시작**: `warm_up_market_caches_with_context()` - 전체 시장 가격 캐시 웜업
2. **주기 갱신**: 31초마다 전체 시장 + 활성 포지션 심볼 갱신 (소수 주기로 정각 트래픽 회피)
3. **실시간 조회**: TTL 체크 → 캐시 히트 시 즉시 반환, 캐시 미스 시 REST API 호출 후 캐시 갱신

**가격 업데이트 메커니즘**:
- 주기적 REST API 폴링 방식 (31초마다 `ExchangeService.get_price_quotes()` 호출)
- WebSocket 실시간 스트리밍 미사용 (WebSocket은 주문 체결 이벤트만 처리)

---

## 3. 데이터 플로우 (Data Flow)

**Input**: `symbol`, `exchange`, `market_type`
**Process**: TTL 체크 → 캐시 조회 → Fallback API 호출 (필요 시)
**Output**: `Decimal` 가격 또는 `dict` (상세 정보 포함)

**캐시 구조**:
- 메모리 기반 (In-memory dictionary)
- 캐시 키 패턴: `{EXCHANGE}:{MARKET_TYPE}:{SYMBOL}` (예: `BINANCE:FUTURES:BTCUSDT`)
- 저장 데이터: `{'price': float, 'timestamp': float, 'exchange': str, 'market_type': str, 'symbol': str}`

**의존성**:
- `ExchangeService.get_price_quotes()` - 거래소 API 호출
- `APScheduler` - 백그라운드 주기 갱신
- `StrategyPosition` DB - 활성 포지션 목록 조회

---

## 4. 주요 컴포넌트 (Components)

### 4.1 PriceCache 클래스

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `services/price_cache.py` | 가격 캐싱 및 조회 | `@FEAT:price-cache @COMP:service @TYPE:core` | `get_price()`, `set_price()`, `update_batch_prices()`, `get_usdt_krw_rate()` |

**주요 메서드**:

#### __init__() - 초기화
```python
# @FEAT:price-cache @COMP:service @TYPE:core
def __init__(self, ttl_seconds: int = 60)
```
**기능**: PriceCache 인스턴스 초기화
- TTL 설정 (기본 60초, 싱글톤은 30초)
- 메모리 캐시 딕셔너리 초기화
- Thread-safe Lock 설정 (RLock)
- 통계 카운터 초기화 (hit, miss, update)

#### _get_cache_key() - 캐시 키 생성 (내부 함수)
```python
# @FEAT:price-cache @COMP:service @TYPE:helper
def _get_cache_key(
    symbol: str,
    exchange: str = 'BINANCE',
    market_type: str = 'FUTURES'
) -> str
```
**기능**: 캐시 키 생성 (정규화된 형식)
- 반환 형식: `{EXCHANGE}:{MARKET_TYPE}:{SYMBOL}` (예: `BINANCE:FUTURES:BTCUSDT`)
- 대문자 정규화

#### get_price() - 가격 조회 (TTL 기반 캐싱)
```python
# @FEAT:price-cache @COMP:service @TYPE:core
def get_price(
    symbol: str,
    exchange: str = 'BINANCE',
    market_type: str = 'FUTURES',
    fallback_to_api: bool = True,
    return_details: bool = False
) -> Optional[Any]
```
**기능**: 메모리 캐시에서 심볼 가격 조회 또는 API 폴백
- 기본 TTL: 60초 (싱글톤 인스턴스는 30초로 설정)
- Thread-safe (RLock 사용)
- 자동 Fallback API 호출 (캐시 미스 시)
- 1시간(3600초) 이상 갱신 지연 시 CRITICAL 로그 발생 및 None 반환
- `return_details=True`: 상세 정보 반환
  - 캐시 HIT: {price, age_seconds, source='cache', timestamp}
  - API 호출: {price, age_seconds=0.0, source='api', timestamp}
- 캐시 HIT/MISS 통계 자동 기록

#### get_usdt_krw_rate() - 환율 조회 (신뢰성 중시)
```python
# @FEAT:price-cache @COMP:service @TYPE:core @DEPS:exchange-api
def get_usdt_krw_rate(fallback_to_api: bool = True) -> Decimal
```
**기능**: UPBIT에서 USDT/KRW 환율 조회 (금전적 손실 방지)
- TTL: 30초 (USDT/KRW 심볼로 캐싱)
- 거래소: UPBIT, 마켓타입: SPOT
- 실패 시 `ExchangeRateUnavailableError` 예외 발생
- 용도: KRW 잔고를 USDT로 변환할 때 사용
- fallback_to_api=False: API 호출 없이 캐시만 확인

#### _fetch_price_from_api() - API 직접 조회 (내부 함수)
```python
# @FEAT:price-cache @COMP:service @TYPE:integration @DEPS:exchange-integration
def _fetch_price_from_api(
    symbol: str,
    exchange: str = 'BINANCE',
    market_type: str = 'FUTURES'
) -> Optional[Decimal]
```
**기능**: API에서 직접 가격 조회 (캐시 미스 시 호출)
- ExchangeService.get_price_quotes() 호출
- 거래소/마켓타입 정규화 처리
- 예외 발생 시 로그 기록 후 None 반환

#### update_batch_prices() - 일괄 업데이트
```python
# @FEAT:price-cache @COMP:service @TYPE:core
def update_batch_prices(
    symbols: list,
    exchange: str,
    market_type: str
) -> Dict[str, Decimal]
```
**기능**: 여러 심볼 가격 일괄 업데이트
- 단일 API 호출로 효율성 극대화
- 거래소/마켓타입 정규화 처리
- 심볼 중복 제거 및 정렬 처리
- 반환: 성공적으로 업데이트된 심볼 딕셔너리 {symbol: price}
- 개별 조회 실패는 무시하고 계속 진행 (부분 성공 허용)
- 예외 발생 시 에러 로그 기록하고 현재까지의 성공 결과 반환

#### set_price() - 캐시 수동 업데이트
```python
# @FEAT:price-cache @COMP:service @TYPE:core
def set_price(
    symbol: str,
    price: Decimal,
    exchange: str = 'BINANCE',
    market_type: str = 'FUTURES'
) -> None
```
**기능**: 특정 심볼의 가격을 수동으로 캐시에 저장
- 캐시 데이터: price, timestamp, exchange, market_type, symbol
- Thread-safe (RLock 사용)
- 업데이트 카운트 증가

#### get_stats() - 통계 조회
```python
# @FEAT:price-cache @COMP:service @TYPE:helper
def get_stats() -> Dict[str, Any]
```
- 반환: 캐시_크기, 히트/미스 횟수, 히트율, 업데이트 횟수

#### clear_cache() / get_cached_symbols() - 유틸리티
```python
# @FEAT:price-cache @COMP:service @TYPE:helper
def clear_cache(
    exchange: Optional[str] = None,
    market_type: Optional[str] = None
) -> int

def get_cached_symbols(
    exchange: Optional[str] = None,
    market_type: Optional[str] = None
) -> list
```
**clear_cache()**: 캐시 클리어 (조건부)
- None일 시 전체 클리어
- 거래소/마켓타입 필터 적용 가능
- 반환: 삭제된 항목 수

**get_cached_symbols()**: 캐시된 심볼 목록 조회
- 거래소/마켓타입 필터 적용 가능
- 반환: 심볼 리스트

### 4.1.1 싱글톤 인스턴스

```python
# @FEAT:price-cache @COMP:service @TYPE:core
price_cache = PriceCache(ttl_seconds=30)  # 30초 TTL
```

**특징**:
- 모듈 레벨 싱글톤 (전역 인스턴스)
- 기본 TTL 60초 대신 30초로 설정 (백그라운드 갱신 주기 31초와 동기화)
- 거래소 전체, 마켓타입 전체 통합 캐싱

**사용 예시**:
```python
from app.services.price_cache import price_cache

# 가격 조회
price = price_cache.get_price('BTCUSDT', 'BINANCE', 'FUTURES')

# 환율 조회 (금전적 손실 방지)
rate = price_cache.get_usdt_krw_rate()

# 일괄 업데이트
prices = price_cache.update_batch_prices(['BTCUSDT', 'ETHUSDT'], 'BINANCE', 'FUTURES')

# 통계
stats = price_cache.get_stats()
```

### 4.2 백그라운드 갱신 스케줄러

| 파일 | 역할 | 태그 |
|------|------|------|
| `app/__init__.py:979-1081` | 주기적 가격 캐시 갱신 핵심 로직 (`_refresh_price_cache`) | `@FEAT:price-cache @FEAT:background-scheduler @COMP:job @TYPE:core` |
| `app/__init__.py:1084-1092` | 앱 시작 시 캐시 초기 웜업 (`warm_up_market_caches`) | `@FEAT:price-cache @COMP:job @TYPE:core` |
| `app/__init__.py:1095-1104` | 주기적 갱신 래퍼 함수 (`update_price_cache`) | `@FEAT:price-cache @COMP:job @TYPE:helper` |

**스케줄러 설정** (`app/__init__.py:687-696`):
```python
scheduler.add_job(
    func=update_price_cache,
    trigger="interval",
    seconds=31,  # 소수 주기 (정각 트래픽 회피)
    id='update_price_cache',
    name='Update Price Cache',
    replace_existing=True,
    max_instances=1
)
```

**갱신 전략 (2-Tier)**:

**Tier 1 - 전체 시장 조회** (모든 거래소/마켓타입)
- ExchangeMetadata 기반 supported_markets 필터링
- 각 거래소별로 메타데이터에 정의된 마켓타입만 조회
- 전체 심볼 일괄 조회 (symbols=None)

**Tier 2 - 활성 포지션 우선 갱신**
- DB 조회: `StrategyPosition.query.filter(quantity != 0)`
- 보유 중인 심볼만 추출하여 거래소/마켓타입별로 그룹화
- `update_batch_prices()` 호출로 배치 업데이트

**초기 웜업** (`app/__init__.py:1084-1092`):
- 애플리케이션 시작 시 `warm_up_market_caches()` 호출
- `_refresh_price_cache(app, source='startup')` 실행
- 전체 시장 가격 캐시를 미리 로드하여 초기 캐시 미스 방지

---

## 5. 사용 위치 (Integration Points)

### 5.1 position-tracking
- **용도**: 미실현 손익 계산 (현재가 조회)
- **파일**: `services/trading/position_manager.py:907-982`
- **태그**: `@FEAT:position-tracking @DEPS:price-cache`
- **스케줄**: 307초마다 실행

### 5.2 order-queue
- **용도**: 정렬 가격 (sort_price) 계산, MARKET 주문 현재가 조회
- **파일**: `services/trading/quantity_calculator.py:30-70`
- **태그**: `@FEAT:order-queue @DEPS:price-cache`

### 5.3 webhook-order
- **용도**: 주문 수량 계산 (qty_per % 변환 시 현재가 필요)
- **의존성**: `quantity_calculator.determine_order_price()` 내부에서 사용

### 5.4 analytics
- **용도**: 현재 포지션 가치 계산
- **태그**: `@FEAT:analytics @DEPS:price-cache`

---

## 6. 설계 결정 히스토리 (Design Decisions)

### TTL 30초 선택 이유
- 실시간성과 캐시 효율의 균형점
- 백그라운드 갱신 주기(31초)와 유사하여 대부분 최신 데이터 유지
- 메모리 효율성 (너무 긴 TTL은 불필요한 메모리 사용)
- 참고: PriceCache 클래스의 기본 TTL은 60초이지만, 싱글톤 인스턴스(`price_cache`)는 30초로 초기화됨

### 31초 주기 (소수 주기 전략)
- 31은 소수(prime number)로 정각(00초, 30초 등) 집중 트래픽 회피
- 거래소 API Rate Limit 분산 효과

### Thread-safe 보장
- `threading.RLock` 사용 (재진입 가능)
- 멀티스레드 환경 (Flask + APScheduler)에서 안전성 보장

---

## 7. 성능 지표

| 지표 | 목표 | 달성 (예시) |
|-----|------|-----------|
| 캐시 히트율 | 95%+ | 97.4% |
| 응답 시간 (캐시 히트) | <10ms | 5ms |
| 응답 시간 (캐시 미스) | <200ms | 150ms |
| API 호출 감소 | 90%+ | 92% |
| 메모리 사용량 | <50MB | 12MB |

---

## 7.5 Known Issues

### 1시간 갱신 지연 감지 (Critical Safety Check)
**이상한 점**: `get_price()`가 1시간(3600초) 이상 갱신 안 된 캐시를 감지하면 CRITICAL 로그 후 None 반환
**이유**: 스케줄러 정지 또는 거래소 API 장애 등으로 인한 금전적 손실 방지. 신뢰할 수 없는 구식 가격으로 거래하지 못하도록 강제

---

## 8. 유지보수 가이드

### 8.1 주의사항
- TTL 변경 시 백그라운드 갱신 주기도 함께 고려
- 심볼 표기 일관성 유지 (예: `BTCUSDT` vs `BTC/USDT`)
- 거래소별 Rate Limit 준수

### 8.2 트러블슈팅

**문제 1: 캐시 히트율 낮음 (<80%)**
- 원인: TTL 짧음, 백그라운드 갱신 실패, 심볼 표기 불일치
- 해결: 로그 확인 (`grep "가격 캐시 통계" logs/app.log`), TTL 조정

**문제 2: 1시간 이상 갱신 지연**
- 원인: 스케줄러 중단, 거래소 API 실패
- 해결: 스케줄러 상태 확인, 수동 갱신 트리거 (`POST /api/scheduler/force/price_cache`)

**문제 3: 특정 심볼 미업데이트**
- 원인: 거래소에서 가격 정보 미제공, 심볼 표기 불일치
- 해결: `get_cached_symbols()` 확인, `fallback_to_api=True`로 강제 조회

**문제 4: 메모리 증가**
- 원인: TTL 너무 길거나 심볼 수 과다
- 해결: 주기적 캐시 클리어 스케줄 추가, LRU 전략 도입

### 8.3 확장 포인트
- LRU 캐시 전략 도입 (최대 크기 제한)
- Redis 기반 분산 캐시로 확장 (현재는 메모리 기반, 멀티 인스턴스 환경에서는 Redis 권장)
- WebSocket 기반 실시간 가격 스트리밍 통합 (현재 WebSocket은 주문 이벤트만 처리, 가격 스트리밍 미구현)

---

## 9. 코드 검색 가이드

```bash
# 가격 캐시 관련 모든 코드
grep -r "@FEAT:price-cache" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:price-cache" --include="*.py" | grep "@TYPE:core"

# 가격 캐시를 의존하는 기능
grep -r "@DEPS:price-cache" --include="*.py"

# 가격 조회 호출 위치
grep -r "price_cache.get_price" --include="*.py"

# 배치 업데이트 호출 위치
grep -r "update_batch_prices" --include="*.py"
```

---

## 10. 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [거래소 통합](./exchange-integration.md)
- [포지션 추적](./position-tracking.md)
- [주문 큐 시스템](./order-queue-system.md)
- [백그라운드 스케줄러](./background-scheduler.md)

---

*Last Updated: 2025-10-30*
*Version: 2.2.0 (Code Sync - Added Method Details: __init__, _get_cache_key, _fetch_price_from_api, Singleton Instance)*
