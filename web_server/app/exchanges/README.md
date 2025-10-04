# Crypto Exchange Adapter Architecture

## 개요
크립토 거래소 통합 어댑터 - **플러그인 구조**로 확장 용이

## 지원 거래소

| 거래소 | 지역 | 마켓 | 레버리지 | Testnet |
|--------|------|------|----------|---------|
| Binance | 해외 | Spot, Futures | ✅ | ✅ |
| Upbit | 국내 | Spot | ❌ | ❌ |

## 사용 예시

### 1. 기본 사용법
```python
from app.exchanges.factory import ExchangeFactory

# Binance
binance = ExchangeFactory.create_binance(api_key, secret, testnet=True)
balance = await binance.fetch_balance('spot')
print(f"잔액: {balance['free']} USDT")

# Upbit
upbit = ExchangeFactory.create_upbit(api_key, secret)
balance = await upbit.fetch_balance('spot')
print(f"잔액: {balance['free']} KRW")

# 주문 생성 (Binance)
order = await binance.create_order(
    symbol='BTCUSDT',
    order_type='LIMIT',
    side='buy',
    amount=Decimal('0.001'),
    price=Decimal('95000'),
    market_type='futures'
)

# 주문 생성 (Upbit)
order = await upbit.create_order(
    symbol='BTCKRW',
    order_type='LIMIT',
    side='buy',
    amount=Decimal('0.001'),
    price=Decimal('95000000'),  # KRW
    market_type='spot'
)
```

### 2. 거래소 필터링
```python
from app.exchanges.metadata import ExchangeRegion, MarketType

# 해외 거래소만 조회
global_ex = ExchangeFactory.list_exchanges(region=ExchangeRegion.GLOBAL)
# ['binance']

# 국내 거래소만 조회
domestic_ex = ExchangeFactory.list_exchanges(region=ExchangeRegion.DOMESTIC)
# ['upbit']

# 선물 지원 거래소
futures = ExchangeFactory.list_exchanges(market_type=MarketType.FUTURES)
# ['binance']

# Spot 지원 거래소
spot = ExchangeFactory.list_exchanges(market_type=MarketType.SPOT)
# ['binance', 'upbit']

# 레버리지 지원 거래소
leverage = ExchangeFactory.list_exchanges(feature='leverage')
# ['binance']
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
    'features': {'leverage': True, 'position_mode': True, 'unified_account': True}
}
```

### Step 2: 어댑터 구현
`app/exchanges/bybit.py`:
```python
class BybitExchange(BaseExchange):
    # BaseExchange 필수 메서드 구현
    async def create_order(...): ...
    async def fetch_balance(...): ...
    # features 기반 선택적 메서드
    async def set_leverage(...): ...  # if supports_feature('leverage')
```

### Step 3: Factory 등록
`app/exchanges/factory.py`:
```python
_EXCHANGE_CLASSES = {
    'binance': BinanceExchange,
    'bybit': BybitExchange,  # 추가
}
```

## 아키텍처 특징

### 1. 메타데이터 기반 관리
- 거래소 정보를 `metadata.py`에 중앙 집중 관리
- Region, MarketType, Features 등 체계적 분류
- Rate Limit 정보 포함

### 2. Features 기반 검증
```python
# 레버리지 지원 확인 후 호출
if exchange.supports_feature('leverage'):
    await exchange.set_leverage('BTCUSDT', 10)
```

### 3. 표준 응답 포맷
- `fetch_balance()`: `{'free', 'used', 'total'}`
- `create_order()`: `{'order_id', 'status', 'filled_quantity', 'average_price'}`

### 4. 플러그인 구조
- `_EXCHANGE_CLASSES` 딕셔너리에만 등록
- 기존 코드 수정 최소화
- 확장성 극대화

## 향후 확장 계획

### Phase 2 (단기)
- [x] Upbit (국내, Spot 전용) ✅ 완료
- [ ] Bybit (해외, Spot + Perpetual)
- [ ] Bithumb (국내, Spot)

### Phase 3 (중기)
- [ ] OKX, Bitget (해외, Spot + Futures)

## 웹훅 통합

현재 시스템의 웹훅 기능은 이 확장성 구조와 완전히 호환됩니다:
- ✅ LIMIT/MARKET 주문 정상 작동
- ✅ CANCEL_ALL_ORDER 정상 작동
- ✅ 포지션 청산 (qty_per=-100) 정상 작동
- ✅ 기존 Binance 어댑터 완전 호환
