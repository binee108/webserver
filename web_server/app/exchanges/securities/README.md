# Securities Exchange Adapters

증권 거래소 통합 어댑터 모듈

## 지원 증권사

| 증권사 | 코드 | 지원 시장 | OAuth | 실시간 |
|--------|------|----------|-------|--------|
| 한국투자증권 | KIS | 국내주식, 해외주식 | ✅ | ✅ |

## 사용 예시

### Factory 사용 (권장)
```python
from app.exchanges.securities import SecuritiesExchangeFactory
from app.models import Account
from decimal import Decimal

# 계좌 기반 생성
account = Account.query.filter_by(exchange='KIS').first()
exchange = SecuritiesExchangeFactory.create(account)

# 국내주식 주문 (삼성전자)
order = await exchange.create_stock_order(
    symbol='005930',
    side='buy',
    order_type='LIMIT',
    quantity=10,
    price=Decimal('70000')
)

# 해외주식 주문 (Apple)
order = await exchange.create_stock_order(
    symbol='AAPL',
    side='buy',
    order_type='LIMIT',
    quantity=5,
    price=Decimal('150.50')
)
```

### 직접 생성
```python
from app.exchanges.securities import KoreaInvestmentExchange

exchange = KoreaInvestmentExchange(account)
```

## OAuth 토큰 관리

토큰은 자동으로 관리됩니다:
- **유효기간**: 24시간
- **자동 갱신**: 6시간마다 (Background Job)
- **Race Condition 방지**: DB 레벨 락 (`SELECT FOR UPDATE`)

### 수동 토큰 발급
```python
# 토큰 발급
token_data = await exchange.authenticate()
print(f"토큰: {token_data['access_token']}")
print(f"만료: {token_data['expires_at']}")

# 토큰 자동 관리 (권장)
token = await exchange.ensure_token()  # 만료 시 자동 갱신
```

### Background Job 설정
`app/jobs/securities_token_refresh.py`에서 자동으로 토큰을 갱신합니다:
```python
from app.jobs.securities_token_refresh import SecuritiesTokenRefreshJob

# APScheduler 등록 (6시간 주기)
scheduler.add_job(
    func=lambda: SecuritiesTokenRefreshJob.run(app),
    trigger='interval',
    hours=6,
    id='securities_token_refresh'
)
```

## 계좌 설정

### 한국투자증권 (KIS)
Account 모델의 `securities_config` 필드에 설정:
```python
account.securities_config = {
    'appkey': '발급받은 App Key',
    'appsecret': '발급받은 App Secret',
    'account_number': '12345678-01',  # 계좌번호-상품코드
    'is_virtual': False  # True: 모의투자, False: 실전투자
}
```

## 새 증권사 추가 방법

### Step 1: 어댑터 구현
`app/exchanges/securities/kiwoom.py`:
```python
from app.exchanges.securities.base import BaseSecuritiesExchange
from app.exchanges.securities.models import StockOrder

class KiwoomExchange(BaseSecuritiesExchange):
    async def authenticate(self):
        # OAuth 토큰 발급 구현
        pass

    async def create_stock_order(self, symbol, side, order_type, quantity, price=None):
        # 주문 생성 구현
        pass
```

### Step 2: Constants 등록
`app/constants.py`:
```python
class Exchange:
    KIS = 'KIS'
    KIWOOM = 'KIWOOM'  # 추가
```

### Step 3: Factory 등록
`app/exchanges/securities/factory.py`:
```python
from .kiwoom import KiwoomExchange

class SecuritiesExchangeFactory:
    _EXCHANGE_CLASSES = {
        Exchange.KIS: KoreaInvestmentExchange,
        Exchange.KIWOOM: KiwoomExchange,  # 추가
    }
```

### Step 4: Export
`app/exchanges/securities/__init__.py`:
```python
from .kiwoom import KiwoomExchange

__all__ = [
    'BaseSecuritiesExchange',
    'SecuritiesExchangeFactory',
    'KoreaInvestmentExchange',
    'KiwoomExchange',  # 추가
]
```

## 데이터 모델

### StockOrder
```python
@dataclass
class StockOrder:
    order_id: str           # 주문번호
    symbol: str             # 종목코드
    side: str               # buy/sell
    order_type: str         # LIMIT/MARKET
    quantity: int           # 주문수량
    price: Optional[Decimal]  # 주문가격
    filled_quantity: int    # 체결수량
    average_price: Optional[Decimal]  # 평균체결가
    status: str             # NEW/FILLED/CANCELLED
    timestamp: datetime     # 주문시각
```

### StockBalance
```python
@dataclass
class StockBalance:
    total: Decimal          # 총 평가금액
    available: Decimal      # 주문가능금액
    stocks: List[Dict]      # 보유 종목 목록
```

## API 문서
- [한국투자증권 API 인증](../../../../docs/korea_investment_api_auth.md)
- [국내주식 API](../../../../docs/korea_investment_api_domestic_stock.md)
- [해외주식 API](../../../../docs/korea_investment_api_overseas_stock.md)

## 참고 자료
- [BaseSecuritiesExchange](./base.py)
- [한국투자증권 어댑터](./korea_investment.py)
- [통합 Factory](../unified_factory.py)
