# Exchange Adapters - Unified Architecture

크립토 거래소 + 증권 거래소 통합 어댑터

## 디렉토리 구조

```
exchanges/
├── crypto/           # 크립토 거래소 (Binance, Upbit)
├── securities/       # 증권 거래소 (한투, 키움 등)
├── base.py          # 공통 BaseExchange
├── models.py        # 공통 데이터 모델
├── exceptions.py    # 공통 예외
├── metadata.py      # 거래소 메타데이터
└── unified_factory.py  # 통합 팩토리
```

## 지원 거래소

### Crypto (크립토)
- **Binance**: Spot, Futures, Testnet 지원
- **Upbit**: Spot (국내)

### Securities (증권)
- **한국투자증권 (KIS)**: 국내주식, 해외주식

## 통합 사용법

### UnifiedExchangeFactory (권장)

```python
from app.exchanges import UnifiedExchangeFactory
from app.models import Account

# 자동 타입 감지
account = Account.query.get(1)
exchange = UnifiedExchangeFactory.create(account)

# account.account_type == 'CRYPTO' → BinanceExchange 등
# account.account_type == 'STOCK' → KoreaInvestmentExchange 등
```

### 타입별 직접 사용

```python
# Crypto
from app.exchanges.crypto import BinanceExchange, CryptoExchangeFactory

exchange = CryptoExchangeFactory.create('binance', api_key, secret, testnet=True)

# Securities
from app.exchanges.securities import KoreaInvestmentExchange, SecuritiesExchangeFactory

account = Account.query.filter_by(exchange='KIS').first()
exchange = SecuritiesExchangeFactory.create(account)
```

## 마이그레이션 가이드

### 기존 코드 (Deprecated)
```python
# ⚠️ 작동하지만 권장하지 않음
from app.exchanges import BinanceExchange

# ❌ 작동하지 않음 (디렉토리 이동)
from app.securities import KoreaInvestmentExchange
```

### 신규 코드 (권장)
```python
# ✅ 명시적 경로 (권장)
from app.exchanges.crypto import BinanceExchange
from app.exchanges.securities import KoreaInvestmentExchange

# ✅ 통합 사용 (권장)
from app.exchanges import UnifiedExchangeFactory
```

## 하위 호환성

기존 `from app.exchanges import BinanceExchange` 형태는 계속 작동하지만,
새 코드에서는 명시적인 경로 사용을 권장합니다.

```python
# 하위 호환 (Deprecated)
from app.exchanges import BinanceExchange  # ⚠️ 작동하지만 Deprecated

# 권장 방식
from app.exchanges.crypto import BinanceExchange  # ✅
```

## 사용 예시

### 1. Crypto 거래소 (Binance)
```python
from app.exchanges.crypto import CryptoExchangeFactory
from decimal import Decimal

exchange = CryptoExchangeFactory.create('binance', api_key, secret, testnet=True)

# 잔액 조회
balance = await exchange.fetch_balance('futures')
print(f"USDT: {balance['free']}")

# 주문 생성
order = await exchange.create_order(
    symbol='BTC/USDT',
    order_type='LIMIT',
    side='buy',
    amount=Decimal('0.001'),
    price=Decimal('95000'),
    market_type='futures'
)
```

### 2. Securities 거래소 (한국투자증권)
```python
from app.exchanges.securities import SecuritiesExchangeFactory
from app.models import Account
from decimal import Decimal

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
```

### 3. 통합 사용 (UnifiedExchangeFactory)
```python
from app.exchanges import UnifiedExchangeFactory
from app.models import Account

# Crypto 계좌
crypto_account = Account.query.filter_by(exchange='BINANCE').first()
crypto_exchange = UnifiedExchangeFactory.create(crypto_account)
# → BinanceExchange 반환

# Securities 계좌
securities_account = Account.query.filter_by(exchange='KIS').first()
securities_exchange = UnifiedExchangeFactory.create(securities_account)
# → KoreaInvestmentExchange 반환
```

## 확장성

### 새 Crypto 거래소 추가
1. `crypto/bybit.py` 생성
2. `crypto/factory.py`에 등록
3. `crypto/__init__.py`에서 export

[자세한 방법](crypto/README.md#새-거래소-추가-방법)

### 새 Securities 거래소 추가
1. `securities/kiwoom.py` 생성
2. `securities/factory.py`에 등록
3. `securities/__init__.py`에서 export

[자세한 방법](securities/README.md#새-증권사-추가-방법)

## 아키텍처 특징

### 1. 명확한 타입 분리
- **Crypto**: `app.exchanges.crypto` (Binance, Upbit)
- **Securities**: `app.exchanges.securities` (한국투자증권)

### 2. 단일 진입점
- `UnifiedExchangeFactory.create()`: account_type 기반 자동 분기

### 3. 공통 코드 재사용
- `base.py`: 모든 거래소의 공통 인터페이스
- `models.py`: 공통 데이터 모델 (Order, Balance, Position)
- `exceptions.py`: 공통 예외 클래스

### 4. 플러그인 구조
- Factory 패턴으로 새 거래소 추가 용이
- 기존 코드 수정 최소화

## 참고 자료
- [Crypto 거래소 가이드](crypto/README.md)
- [Securities 거래소 가이드](securities/README.md)
- [통합 팩토리](unified_factory.py)
- [공통 Base 클래스](base.py)
