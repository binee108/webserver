# 거래소 어댑터 문서

Phase 3에서 구현된 비동기 거래소 API 어댑터의 상세 문서입니다.

---

## 개요

**목적**: Binance, Bybit, Upbit 거래소 API를 비동기로 호출하는 통일된 인터페이스 제공

**특징**:
- ⚡ 완전한 비동기 I/O (httpx + asyncio)
- 🔄 자동 재시도 (exponential backoff, 500 에러 포함)
- 🛡️ 거래소별 인증 (HMAC SHA256, JWT)
- ⏱️ Rate Limiting (거래소별 API 제한 준수)
- 🔍 명확한 예외 계층
- 📊 데이터 정규화 (거래소별 차이 흡수)

---

## 지원 거래소

| 거래소 | API 버전 | 인증 방식 | Rate Limit |
|--------|----------|----------|-----------|
| Binance | v3 | HMAC SHA256 | 10 req/s |
| Bybit | v5 | HMAC SHA256 (헤더) | 10 req/s |
| Upbit | v1 | JWT | 8 req/s |

---

## 빠른 시작

### 1. 환경 설정

```bash
# .env 파일에 API Key 추가
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret

BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_api_secret

UPBIT_API_KEY=your_upbit_access_key
UPBIT_API_SECRET=your_upbit_secret_key

# Mock Exchange 사용 여부 (개발/테스트)
USE_MOCK_EXCHANGE=true
```

### 2. 기본 사용법

```python
from app.exchanges import get_exchange_adapter

# 거래소 어댑터 생성 (싱글톤)
binance = get_exchange_adapter("binance")

# 주문 생성
order = await binance.create_order(
    symbol="BTC/USDT",
    side="buy",
    order_type="market",
    quantity=0.001
)

# 주문 조회
order_info = await binance.get_order(
    symbol="BTC/USDT",
    order_id=order["order_id"]
)

# 주문 취소
cancelled = await binance.cancel_order(
    symbol="BTC/USDT",
    order_id=order["order_id"]
)

# 미체결 주문 조회
open_orders = await binance.get_open_orders(symbol="BTC/USDT")
```

### 3. Context Manager 사용

```python
async with get_exchange_adapter("binance") as exchange:
    order = await exchange.create_order(
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        quantity=0.001,
        price=50000.0
    )
# 자동 close()
```

---

## API 레퍼런스

### get_exchange_adapter()

```python
def get_exchange_adapter(
    exchange_name: str,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    **kwargs
) -> BaseExchangeAdapter
```

**거래소 어댑터 팩토리 함수 (싱글톤)**

**Args**:
- `exchange_name`: 거래소 이름 ("binance", "bybit", "upbit")
- `api_key`: API Key (없으면 config에서 로드)
- `api_secret`: API Secret (없으면 config에서 로드)
- `**kwargs`: 추가 설정 (timeout, max_retries 등)

**Returns**: 거래소 어댑터 인스턴스

**Raises**:
- `ValueError`: 지원하지 않는 거래소
- `ValueError`: API Key/Secret 없음

**예시**:
```python
# Config에서 API Key 로드
adapter = get_exchange_adapter("binance")

# 직접 API Key 전달
adapter = get_exchange_adapter(
    "binance",
    api_key="your_key",
    api_secret="your_secret",
    timeout=60.0,
    max_retries=5
)
```

---

### BaseExchangeAdapter (공통 인터페이스)

모든 거래소 어댑터가 구현하는 메서드입니다.

#### cancel_order()

```python
async def cancel_order(
    symbol: str,
    order_id: str
) -> Dict[str, Any]
```

**주문 취소**

**Args**:
- `symbol`: 심볼 (예: "BTC/USDT")
- `order_id`: 주문 ID (거래소 order_id)

**Returns**: 정규화된 주문 정보 (딕셔너리)

**Raises**:
- `OrderNotFoundException`: 주문 없음
- `ExchangeAPIError`: API 에러
- `ExchangeServerError`: 서버 에러

**예시**:
```python
result = await adapter.cancel_order("BTC/USDT", "12345")
# {
#   "exchange": "binance",
#   "order_id": "12345",
#   "status": "CANCELLED",
#   ...
# }
```

#### create_order()

```python
async def create_order(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None
) -> Dict[str, Any]
```

**주문 생성**

**Args**:
- `symbol`: 심볼 (예: "BTC/USDT")
- `side`: 방향 ("buy" | "sell")
- `order_type`: 주문 타입 ("market" | "limit")
- `quantity`: 수량
- `price`: 가격 (limit 주문 시 필수)

**Returns**: 정규화된 주문 정보

**Raises**:
- `InsufficientBalanceError`: 잔고 부족
- `ExchangeAPIError`: API 에러

**예시**:
```python
# Market 주문
order = await adapter.create_order(
    symbol="BTC/USDT",
    side="buy",
    order_type="market",
    quantity=0.001
)

# Limit 주문
order = await adapter.create_order(
    symbol="BTC/USDT",
    side="sell",
    order_type="limit",
    quantity=0.001,
    price=55000.0
)
```

#### get_order()

```python
async def get_order(
    symbol: str,
    order_id: str
) -> Dict[str, Any]
```

**주문 조회**

**Args**:
- `symbol`: 심볼
- `order_id`: 주문 ID

**Returns**: 정규화된 주문 정보

**Raises**:
- `OrderNotFoundException`: 주문 없음

#### get_open_orders()

```python
async def get_open_orders(
    symbol: Optional[str] = None
) -> List[Dict[str, Any]]
```

**미체결 주문 조회**

**Args**:
- `symbol`: 심볼 (None이면 전체)

**Returns**: 정규화된 주문 목록

---

## 정규화된 주문 형식

모든 거래소 어댑터는 주문 데이터를 다음 형식으로 반환합니다:

```python
{
    "exchange": str,           # 거래소 이름
    "order_id": str,           # 주문 ID
    "symbol": str,             # 심볼 (slash 구분: "BTC/USDT")
    "side": str,               # "buy" | "sell"
    "type": str,               # "market" | "limit"
    "status": str,             # "OPEN" | "FILLED" | "CANCELLED" | "FAILED" | "EXPIRED"
    "quantity": float,         # 주문 수량
    "executed_quantity": float,# 체결 수량
    "price": float,            # 주문 가격
    "average_price": float,    # 평균 체결가
    "created_at": int          # 생성 시각 (timestamp ms)
}
```

**상태 매핑**:
- `OPEN`: 미체결 (부분 체결 포함)
- `FILLED`: 체결 완료
- `CANCELLED`: 취소됨
- `FAILED`: 실패 (거부됨)
- `EXPIRED`: 만료됨

---

## 거래소별 특징

### Binance

**API 문서**: https://binance-docs.github.io/apidocs/spot/en/

**인증**:
- HMAC SHA256 서명
- Query string에 timestamp + signature
- 헤더: `X-MBX-APIKEY`

**심볼 형식**:
- 입력: "BTC/USDT"
- 거래소: "BTCUSDT" (slash 제거)

**Rate Limit**:
- 1200 requests/minute (weight 기반)
- 기본 설정: 10 req/s

**특징**:
- 가장 높은 유동성
- 다양한 주문 타입
- Testnet 지원

### Bybit

**API 문서**: https://bybit-exchange.github.io/docs/v5/intro

**인증**:
- HMAC SHA256 서명
- 헤더: `X-BAPI-API-KEY`, `X-BAPI-SIGN`, `X-BAPI-TIMESTAMP`
- POST는 JSON 바디 서명

**심볼 형식**:
- 입력: "BTC/USDT"
- 거래소: "BTCUSDT" (slash 제거)

**Rate Limit**:
- 10 req/s (Spot)
- 50 req/s (Derivatives)

**특징**:
- V5 통합 API (Spot + Derivatives)
- 응답 구조: `{"retCode":0,"retMsg":"OK","result":{...}}`

### Upbit

**API 문서**: https://docs.upbit.com/reference

**인증**:
- JWT (JSON Web Token)
- PyJWT 라이브러리 사용
- 헤더: `Authorization: Bearer <token>`

**심볼 형식**:
- 입력: "BTC/KRW"
- 거래소: "KRW-BTC" (순서 반대, dash 구분)

**Rate Limit**:
- 30 req/s (일반 조회)
- 8 req/s (주문 API)

**특징**:
- 한국 거래소, KRW 마켓
- Market 주문 시 매수는 금액 지정, 매도는 수량 지정
- Testnet 없음

---

## 에러 처리

### 예외 계층

```
ExchangeException (기본)
├── ExchangeAPIError (4xx)
├── ExchangeServerError (5xx)
├── ExchangeNetworkError (네트워크)
├── ExchangeAuthError (인증)
├── OrderNotFoundException (주문 없음)
├── InsufficientBalanceError (잔고 부족)
└── RateLimitExceededError (Rate Limit)
```

### 에러 처리 예시

```python
from app.exchanges import get_exchange_adapter
from app.exchanges.exceptions import (
    OrderNotFoundException,
    InsufficientBalanceError,
    ExchangeAPIError,
    ExchangeServerError,
    ExchangeNetworkError
)

adapter = get_exchange_adapter("binance")

try:
    order = await adapter.create_order(
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        quantity=0.001
    )
except InsufficientBalanceError as e:
    # 잔고 부족
    logger.error(f"Insufficient balance: {e.details}")

except ExchangeAPIError as e:
    # API 에러 (4xx) - 재시도 불필요
    logger.error(f"API error {e.status_code}: {e.message}")

except ExchangeServerError as e:
    # 서버 에러 (5xx) - 이미 재시도 완료
    logger.error(f"Server error after retries: {e.message}")

except ExchangeNetworkError as e:
    # 네트워크 에러
    logger.error(f"Network error: {e.message}")

except Exception as e:
    # 기타 에러
    logger.exception(f"Unexpected error: {e}")
```

---

## 재시도 메커니즘

### Exponential Backoff

**재시도 대상**:
- ✅ 500 Internal Server Error
- ✅ 502 Bad Gateway
- ✅ 503 Service Unavailable
- ✅ 504 Gateway Timeout
- ✅ 네트워크 타임아웃
- ✅ 연결 실패

**재시도 지연**:
```
Attempt 1: 즉시
Attempt 2: 1초 후 (2^0)
Attempt 3: 2초 후 (2^1)
Attempt 4: 4초 후 (2^2)
```

**재시도 안함**:
- ❌ 4xx 에러 (클라이언트 에러)
- ❌ 401 Unauthorized
- ❌ 403 Forbidden
- ❌ 404 Not Found

**설정**:
```python
# config.py 또는 .env
EXCHANGE_MAX_RETRIES=3       # 최대 재시도 횟수
EXCHANGE_TIMEOUT=30          # 요청 타임아웃 (초)
```

---

## Rate Limiting

### 거래소별 Rate Limit

| 거래소 | 기본 설정 | 권장 설정 | 최대 |
|--------|----------|----------|------|
| Binance | 10 req/s | 10-20 req/s | 20 req/s |
| Bybit | 10 req/s | 10-20 req/s | 20 req/s |
| Upbit | 8 req/s | 5-8 req/s | 8 req/s (주문) |

**설정 방법**:
```bash
# .env
BINANCE_RATE_LIMIT=10.0
BYBIT_RATE_LIMIT=10.0
UPBIT_RATE_LIMIT=8.0
```

**동작 방식**:
- Token Bucket 알고리즘
- asyncio.Lock으로 동시성 제어
- 최소 간격 준수 (1/rate_limit 초)

**Rate Limit 초과 시**:
- 429 응답 수신
- `Retry-After` 헤더 확인
- 지정된 시간만큼 대기 후 재시도
- 최대 재시도 횟수 초과 시 `RateLimitExceededError` 발생

---

## 보안

### API Key 관리

**환경 변수 사용**:
```bash
# .env 파일 (절대 Git 커밋 금지!)
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
```

**코드에서 로드**:
```python
from app.config import settings

# 자동으로 환경 변수에서 로드
adapter = get_exchange_adapter("binance")

# 또는 직접 전달
adapter = get_exchange_adapter(
    "binance",
    api_key=settings.BINANCE_API_KEY,
    api_secret=settings.BINANCE_API_SECRET
)
```

### 권한 최소화

거래소 API Key 생성 시 다음 권한만 부여:
- ✅ Read (조회)
- ✅ Trade (거래)
- ❌ Withdraw (출금) - **절대 비활성화**

### IP 화이트리스트

거래소 설정에서 서버 IP만 허용:
```
# 예시
Binance API 설정 > IP 화이트리스트 > 서버 IP 추가
```

### API Key 로깅 마스킹

```python
# 로그에는 앞 8자만 표시
logger.info(f"Using API Key: {api_key[:8]}***")
```

---

## 테스트

### Unit Tests (Mock)

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.exchanges.binance import BinanceAdapter

@pytest.mark.asyncio
async def test_binance_cancel_order():
    adapter = BinanceAdapter(
        api_key="test_key",
        api_secret="test_secret"
    )

    # httpx.AsyncClient Mock
    with patch.object(adapter.http_client, 'delete') as mock_delete:
        mock_delete.return_value = {
            "orderId": 123456,
            "symbol": "BTCUSDT",
            "status": "CANCELED"
        }

        result = await adapter.cancel_order("BTC/USDT", "123456")

        assert result["order_id"] == "123456"
        assert result["status"] == "CANCELLED"
```

### Integration Tests (실제 API)

```python
@pytest.mark.skip(reason="Requires API credentials")
@pytest.mark.asyncio
async def test_binance_real_api():
    adapter = get_exchange_adapter("binance")

    # Testnet 사용 권장
    orders = await adapter.get_open_orders()

    assert isinstance(orders, list)
```

---

## 트러블슈팅

### API Key 오류

**증상**: `ExchangeAuthError: Binance authentication failed`

**원인**:
- API Key/Secret 오류
- IP 화이트리스트 미설정
- 권한 부족

**해결**:
1. .env 파일 확인
2. 거래소에서 API Key 재확인
3. IP 화이트리스트 설정
4. API Key 권한 확인

### Rate Limit 오류

**증상**: `RateLimitExceededError: Rate limit exceeded`

**원인**:
- 요청이 너무 많음
- Rate limit 설정 초과

**해결**:
```bash
# .env에서 Rate Limit 감소
BINANCE_RATE_LIMIT=5.0  # 10 → 5로 감소
```

### 타임아웃 오류

**증상**: `ExchangeNetworkError: Request timeout`

**원인**:
- 네트워크 지연
- 거래소 서버 느림

**해결**:
```bash
# .env에서 타임아웃 증가
EXCHANGE_TIMEOUT=60  # 30 → 60초로 증가
```

### 주문 없음 오류

**증상**: `OrderNotFoundException: Order not found`

**원인**:
- 잘못된 order_id
- 이미 체결/취소된 주문

**해결**:
```python
try:
    order = await adapter.get_order(symbol, order_id)
except OrderNotFoundException:
    # 주문이 없으면 무시하거나 로깅
    logger.warning(f"Order {order_id} not found, may be already filled")
```

---

## Phase 4+ 확장

Phase 3 이후 추가 예정 기능:

### 추가 메서드
- `get_balance()` - 잔고 조회
- `get_trades()` - 거래 이력
- `get_ticker()` - 시세 조회
- `get_orderbook()` - 호가 조회

### WebSocket
- 실시간 주문 업데이트
- 실시간 시세
- 실시간 체결

### Testnet 지원
- Binance Testnet
- Bybit Testnet

---

## 참고 자료

### 공식 API 문서
- **Binance**: https://binance-docs.github.io/apidocs/spot/en/
- **Bybit**: https://bybit-exchange.github.io/docs/v5/intro
- **Upbit**: https://docs.upbit.com/reference

### 관련 문서
- [Cancel Queue 문서](CANCEL_QUEUE.md)
- [모델 문서](MODELS.md)
- [설정 문서](CONFIGURATION.md)

---

**최종 업데이트**: 2025-10-31
**Phase**: Phase 3 - Exchange Adapters
**버전**: 1.0.0-alpha
