# Crypto Exchange Adapters

크립토 거래소 통합 어댑터 모듈

## 지원 거래소

| 거래소 | 지역 | 마켓 | 레버리지 | Testnet |
|--------|------|------|----------|---------|
| Binance | 해외 | Spot, Futures | ✅ | ✅ |
| Upbit | 국내 | Spot | ❌ | ❌ |

## 사용 예시

### Factory 사용 (권장)
```python
from app.exchanges.crypto import CryptoExchangeFactory

# Binance
exchange = CryptoExchangeFactory.create('binance', api_key, secret, testnet=True)
balance = await exchange.fetch_balance('futures')

# Upbit
exchange = CryptoExchangeFactory.create('upbit', api_key, secret)
balance = await exchange.fetch_balance('spot')
```

### 직접 생성
```python
from app.exchanges.crypto import BinanceExchange, UpbitExchange

binance = BinanceExchange(api_key, secret, testnet=True)
upbit = UpbitExchange(api_key, secret)
```

### 주문 생성 (표준 형식)
```python
from decimal import Decimal

# LIMIT 주문
order = await exchange.create_order(
    symbol='BTC/USDT',      # 표준 형식: BASE/QUOTE
    order_type='LIMIT',
    side='buy',
    amount=Decimal('0.001'),
    price=Decimal('95000'),
    market_type='futures'
)

# MARKET 주문
order = await exchange.create_order(
    symbol='BTC/USDT',
    order_type='MARKET',
    side='buy',
    amount=Decimal('0.001'),
    market_type='spot'
)
```

## 새 거래소 추가 방법

### Step 1: 메타데이터 등록
`app/exchanges/metadata.py`에 추가:
```python
'bybit': {
    'region': ExchangeRegion.GLOBAL,
    'name': 'Bybit',
    'supported_markets': [MarketType.SPOT, MarketType.PERPETUAL],
    'base_currency': ['USDT', 'USDC'],
    'auth_type': 'hmac_sha256',
    'testnet_available': True,
    'rate_limit': {'requests_per_minute': 600, 'orders_per_second': 20},
    'features': {'leverage': True, 'position_mode': True}
}
```

### Step 2: 어댑터 구현
`app/exchanges/crypto/bybit.py`:
```python
from app.exchanges.crypto.base import BaseCryptoExchange

class BybitExchange(BaseCryptoExchange):
    async def create_order(...):
        # 구현
        pass

    async def fetch_balance(...):
        # 구현
        pass
```

### Step 3: Factory 등록
`app/exchanges/crypto/factory.py`:
```python
from .bybit import BybitExchange

class CryptoExchangeFactory:
    _EXCHANGE_CLASSES = {
        'binance': BinanceExchange,
        'upbit': UpbitExchange,
        'bybit': BybitExchange,  # 추가
    }
```

### Step 4: Export
`app/exchanges/crypto/__init__.py`:
```python
from .bybit import BybitExchange

__all__ = [
    'BaseCryptoExchange',
    'CryptoExchangeFactory',
    'BinanceExchange',
    'UpbitExchange',
    'BybitExchange',  # 추가
]
```

## 아키텍처 특징

### 1. 메타데이터 기반 관리
- 거래소 정보를 `metadata.py`에 중앙 집중 관리
- Region, MarketType, Features 등 체계적 분류

### 2. Features 기반 검증
```python
# 레버리지 지원 확인 후 호출
if exchange.supports_feature('leverage'):
    await exchange.set_leverage('BTC/USDT', 10)
```

### 3. 표준 응답 포맷
- `fetch_balance()`: `{'free', 'used', 'total'}`
- `create_order()`: `{'order_id', 'status', 'filled_quantity', 'average_price'}`

### 4. 심볼 표준화
- 모든 심볼은 `BASE/QUOTE` 형식 (예: `BTC/USDT`, `ETH/KRW`)
- 내부적으로 거래소별 형식으로 자동 변환

## 참고 자료
- [메타데이터 정의](../metadata.py)
- [공통 Base 클래스](../base.py)
- [통합 Factory](../unified_factory.py)
