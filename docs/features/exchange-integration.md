# 거래소 통합 (Exchange Integration)

## 1. 개요 (Purpose)

**목적**: 다양한 거래소(Binance, Bybit, 한국투자증권 등)를 통일된 인터페이스로 추상화하여, 상위 레이어(Trading Service)가 거래소 종류에 무관하게 동일한 방식으로 주문을 실행할 수 있도록 합니다.

**핵심 원칙**:
- 통일된 인터페이스: 모든 거래소는 동일한 메서드 시그니처 구현
- 응답 데이터 정규화: 거래소별 다른 응답 형식을 표준 형식으로 변환
- 에러 처리 표준화: 거래소별 다른 에러 코드를 통일된 예외로 변환

## 2. 실행 플로우 (Execution Flow)

```
┌────────────────────────────────────┐
│      Trading Service               │
│  (거래소 무관 비즈니스 로직)        │
└──────────────┬─────────────────────┘
               │ create_order(...)
               ▼
┌──────────────────────────────────────┐
│    UnifiedExchangeFactory            │
│  create(account) → Adapter           │
└──────┬───────────────────────────────┘
       │
       ├─────────────┬─────────────┬──────────┐
       ▼             ▼             ▼          ▼
   Binance       Bybit         KIS       ...
   Adapter       Adapter     Adapter
   (ccxt)        (ccxt)      (REST)
       │             │             │          │
       ▼             ▼             ▼          ▼
   Binance API   Bybit API    KIS API    Other API
```

**주요 실행 단계**:
1. Trading Service가 UnifiedExchangeFactory에 계좌 전달
2. Factory가 거래소 타입에 따라 적절한 Adapter 반환
3. Adapter가 거래소별 API 호출 후 응답을 표준 형식으로 변환
4. Trading Service가 표준화된 데이터 수신 및 처리

## 3. 데이터 플로우 (Data Flow)

**Input**: Account 객체 (거래소 종류, API 키, 시장 타입 등)
**Process**:
- Factory → Adapter 선택 → API 호출 → 응답 정규화
- 거래소별 차이를 Adapter 내부에서 흡수

**Output**: 표준화된 객체 (Order, Position, Balance)
**주요 의존성**:
- ccxt (Crypto 거래소)
- requests (Securities 거래소 REST API)
- DB (계좌 정보, 주문 추적)

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `app/exchanges/base.py` | 통합 인터페이스 정의 | `@FEAT:exchange-integration @COMP:exchange @TYPE:core` | `BaseExchange` (추상 클래스) |
| `app/exchanges/crypto/binance.py` | Binance 어댑터 | `@FEAT:exchange-integration @COMP:exchange @TYPE:integration` | `create_order()`, `cancel_order()`, `fetch_order()` |
| `app/exchanges/crypto/bybit.py` ⚠️ 미구현 | Bybit 어댑터 (계획됨) | `@FEAT:exchange-integration @COMP:exchange @TYPE:integration` | 미구현 |
| `app/exchanges/securities/korea_investment.py` | 한국투자증권 어댑터 | `@FEAT:exchange-integration @COMP:exchange @TYPE:integration` | OAuth 토큰 관리 (주문 API는 별도 구현) |
| `app/exchanges/unified_factory.py` | Factory 패턴 구현 | `@FEAT:exchange-integration @COMP:service @TYPE:core` | `UnifiedExchangeFactory.create()` |
| `app/services/exchange.py` | Exchange Service Orchestrator | `@FEAT:exchange-integration @COMP:service @TYPE:orchestrator` | Rate Limit, Precision Cache, Client Management |

### 통합 인터페이스 메서드

**필수 구현 메서드**:
- `create_order(symbol, side, order_type, quantity, price, stop_price)` → Order
- `cancel_order(order_id, symbol)` → bool
- `fetch_order(order_id, symbol)` → Order
- `fetch_balance()` → Dict[str, Any]
- `fetch_positions(symbol)` → List[Position]
- `fetch_ticker(symbol)` → Dict[str, Any]

### 표준 데이터 모델

**Order (주문)**:
```python
@dataclass
class Order:
    order_id: str              # 거래소 주문 ID
    symbol: str                # "BTC/USDT"
    side: str                  # "buy" or "sell"
    order_type: str            # "LIMIT", "MARKET", "STOP_LIMIT"
    quantity: float
    price: Optional[float]
    stop_price: Optional[float]
    status: str                # "NEW", "FILLED", "CANCELLED"
    filled_quantity: float
    average_price: Optional[float]
    created_at: float          # Unix timestamp
```

**Position (포지션)**:
```python
@dataclass
class Position:
    symbol: str
    side: str                  # "long" or "short"
    quantity: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: Optional[float]
```

## 5. 지원 거래소

| 거래소 | 타입 | 지원 마켓 | 기술 스택 | 어댑터 파일 |
|--------|------|-----------|-----------|-------------|
| **Binance** | Crypto | SPOT, FUTURES | ccxt | `app/exchanges/crypto/binance.py` |
| **Bybit** | Crypto | FUTURES | ccxt | `app/exchanges/crypto/bybit.py` |
| **한국투자증권** | Securities | 국내주식, 해외주식, 선물옵션 | REST API (OAuth 2.0) | `app/exchanges/securities/korea_investment.py` |

### Crypto 거래소 특징 (ccxt 기반)
- WebSocket 실시간 가격/체결 지원
- Testnet 지원 (`use_testnet=True`)
- Rate Limit 자동 관리 (`enableRateLimit=True`)

### Securities 거래소 특징 (REST API 직접 구현)
- OAuth 2.0 인증 (토큰 자동 갱신)
- 거래소별 헤더/바디 커스터마이징 필요
- 모의투자 지원 (`use_testnet=True`)

## 6. 설계 결정 히스토리 (Design Decisions)

### 1. Factory Pattern 선택 이유
- **문제**: Trading Service가 거래소별 Adapter 생성 로직을 알아야 함 (결합도 증가)
- **해결**: UnifiedExchangeFactory로 Adapter 생성 로직 중앙화
- **장점**: 새 거래소 추가 시 Trading Service 수정 불필요

### 2. ccxt vs REST API 직접 구현
- **ccxt 사용 (Crypto)**: 표준화된 API, 커뮤니티 지원, 빠른 개발
- **REST API 직접 구현 (Securities)**: ccxt 미지원, OAuth 2.0 등 복잡한 인증 필요

### 3. 응답 정규화 필수
- **문제**: 거래소마다 다른 응답 형식 (필드명, 타입, 단위)
- **해결**: `_normalize_order()`, `_normalize_position()` 메서드로 표준화
- **예시**: ccxt는 timestamp를 ms로 반환, KIS는 초 단위 → 모두 초 단위로 통일

## 7. 새 거래소 추가 가이드

### Step 1: 어댑터 클래스 생성
```python
# app/exchanges/crypto/new_exchange.py (Crypto 거래소)
from app.exchanges.crypto.base import BaseCryptoExchange
from app.exchanges.models import Order

class NewExchangeAdapter(BaseCryptoExchange):
    def __init__(self, account: Account):
        # 거래소 클라이언트 초기화
        pass

    def create_order(self, symbol, side, order_type, quantity, price=None, **kwargs) -> Order:
        # 1. API 호출
        # 2. 응답 → Order 객체로 변환 (_normalize_order)
        # 3. 에러 처리 (ExchangeError로 변환)
        pass

    # ... 기타 메서드 구현
```

### Step 2: Factory에 등록
```python
# app/exchanges/unified_factory.py
class UnifiedExchangeFactory:
    @staticmethod
    def create(account: Account):
        exchange = account.exchange.upper()

        if exchange == "NEW_EXCHANGE":
            from app.exchanges.crypto.new_exchange import NewExchangeAdapter
            return NewExchangeAdapter(account)
        # ...
```

### Step 3: Constants 업데이트
```python
# app/constants.py
class Exchange:
    NEW_EXCHANGE = "NEW_EXCHANGE"
    VALID_EXCHANGES = [BINANCE, BYBIT, NEW_EXCHANGE]
```

### Step 4: 테스트 작성
```bash
# Testnet 계좌 생성 → 주문 생성/조회/취소 전체 플로우 검증
pytest tests/test_new_exchange.py -v
```

## 8. 에러 처리

### 표준 예외 계층
```python
# app/exchanges/exceptions.py
ExchangeError (기본)
├── InsufficientFundsError  # 잔고 부족
├── InvalidOrderError       # 유효하지 않은 주문
├── RateLimitError          # API 호출 제한 초과
└── NetworkError            # 네트워크 오류
```

### 거래소별 에러 변환 예시
```python
try:
    ccxt_order = self.exchange.create_order(...)
except ccxt.InsufficientFunds as e:
    raise InsufficientFundsError(f"잔고 부족: {e}")
except ccxt.InvalidOrder as e:
    raise InvalidOrderError(f"유효하지 않은 주문: {e}")
except Exception as e:
    raise ExchangeError(f"주문 생성 실패: {e}")
```

## 9. 유지보수 가이드

### 주의사항
1. **응답 정규화 필수**: 모든 Adapter는 표준 데이터 모델(Order, Position) 반환
2. **에러 변환 필수**: 거래소별 예외를 표준 예외(ExchangeError)로 변환
3. **Rate Limit 고려**: ccxt는 `enableRateLimit=True`, REST API는 수동 구현
4. **Testnet 활용**: 실제 자금 없이 개발/테스트 (`use_testnet=True`)
5. **OAuth 토큰 갱신**: Securities 거래소는 토큰 만료 시 자동 재발급 로직 필요

### 확장 포인트
- **새 주문 타입 추가**: `create_order()` 메서드에 파라미터 추가, 거래소별 Adapter에서 처리
- **WebSocket 실시간 데이터**: `app/services/exchanges/{exchange}_websocket.py` 참고
- **마진/레버리지 관리**: 선물 거래소는 `set_leverage()` 메서드 추가 구현

### grep 검색 예시
```bash
# 거래소 통합 관련 코드 찾기
grep -r "@FEAT:exchange-integration" --include="*.py"

# 핵심 로직만 찾기
grep -r "@FEAT:exchange-integration" --include="*.py" | grep "@TYPE:core"

# 특정 거래소 어댑터 찾기
grep -r "BinanceAdapter\|BybitAdapter" --include="*.py"
```

## 10. 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [웹훅 주문 처리](./webhook-order-processing.md)
- [주문 큐 시스템](./order-queue-system.md)
- 한국투자증권 API: `docs/korea_investment_api_*.md`

---

*Last Updated: 2025-10-11*
*Lines: ~240 (reduced from 755)*
*Purpose: 간결성 및 검색 효율성 향상*
