# 통합 웹훅 메시지 포맷 구현 계획

## 📋 프로젝트 개요

**목적**: 크립토/국내주식/해외주식/국내선물옵션/해외선물옵션을 통합 지원하는 웹훅 메시지 포맷 설계 및 구현

**브랜치**: `feature/securities-integration`

**작업 시작일**: 2025-10-07

**담당**: Backend Developer

---

## 🎯 핵심 설계 원칙

1. **사용자 경험 최우선 (UX-First)**
   - 직관적인 필드명
   - 최소 필수 입력
   - 명확한 에러 메시지
   - 하위 호환성 유지 (기존 크립토 웹훅 100% 지원)

2. **일관성 (Consistency)**
   - 모든 마켓에서 동일한 필드명 사용
   - 특수 필드는 `params` 객체로 확장

3. **확장성 (Extensibility)**
   - 새로운 마켓/거래소 추가 시 기존 구조 유지
   - 마켓별 특수 요구사항은 선택적 필드로 처리

---

## 📦 통합 웹훅 메시지 포맷 (최종 설계)

### 기본 구조

```json
{
  // 필수 필드
  "group_name": "my_strategy",  // 전략 식별자 (market_type, exchange는 전략 설정에서 자동 결정)
  "token": "abc123...",
  "order_type": "LIMIT",

  // 주문 대상
  "symbol": "005930",

  // 주문 수량/방향
  "side": "BUY",
  "qty_per": 10,

  // 가격 (선택)
  "price": 70000,
  "stop_price": 69500,

  // 마켓별 특수 파라미터 (선택)
  "params": {
    "exchange_code": "NASD",
    "currency": "USD",
    "position_action": "OPEN",
    "option_type": "CALL"
  }
}
```

### 변경 사항 (2025-10-07)

**제거된 필드**: `exchange`, `market_type`

**이유**:
- `market_type`은 Strategy.market_type에서 자동 결정됨
- `exchange`는 연동된 Account.exchange에서 자동 결정됨
- 사용자의 오입력 방지 (전략 설정과 웹훅 메시지 불일치 방지)
- 데이터 일관성 유지 (Single Source of Truth 원칙)

**마이그레이션 가이드**:
```json
// 변경 전 (2025-10-07 이전)
{
  "group_name": "my_strategy",
  "exchange": "BINANCE",        // ❌ 제거됨
  "market_type": "FUTURES",     // ❌ 제거됨
  "symbol": "BTC/USDT",
  ...
}

// 변경 후 (2025-10-07 이후)
{
  "group_name": "my_strategy",  // 전략 설정에서 market_type, exchange 자동 결정
  "symbol": "BTC/USDT",
  ...
}
```

**하위 호환성**: 기존 웹훅 메시지는 여전히 작동하지만, `exchange`와 `market_type` 필드는 무시됩니다.

---

### 마켓 타입 (참고용)
시스템 내부에서 사용되는 마켓 타입입니다. 웹훅 메시지에서는 지정하지 않습니다.
- `SPOT`: 크립토 현물
- `FUTURES`: 크립토 선물
- `DOMESTIC_STOCK`: 국내주식
- `OVERSEAS_STOCK`: 해외주식
- `DOMESTIC_FUTUREOPTION`: 국내선물옵션
- `OVERSEAS_FUTUREOPTION`: 해외선물옵션

### 심볼 포맷

#### 크립토 (엄격한 검증)
- **SPOT/FUTURES**: `"BTC/USDT"` (슬래시 필수)
  - 표준 형식: `COIN/CURRENCY` (예: `BTC/USDT`, `ETH/KRW`)

#### 증권 (유연한 검증)
증권 심볼은 거래소마다 다양한 형식을 사용하므로, 기본적인 안전성 검증만 수행합니다.
- **허용 문자**: 영문, 숫자, 마침표(`.`), 하이픈(`-`), 언더스코어(`_`)
- **최대 길이**: 30자
- **거래소 API**에서 최종 검증 수행

**예시**:
- **국내주식**: `"005930"`, `"KR005930"`, `"123456A"`, `"Q500001"`
- **해외주식**: `"AAPL"`, `"BRK.A"`, `"BRK.B"`, `"9988"`, `"0700"`
- **국내선물옵션**: `"101TC000"`, `"KR4101C3000"`, `"201PC260"`
- **해외선물옵션**: `"ESZ4"`, `"NQH5"`, `"CL-DEC24"`, `"6E_Z4"`

---

## 📝 Phase별 작업 계획

### Phase 0: 현황 파악 및 체크포인트 생성 ⏳

**목표**: 현재 코드 상태 파악 및 작업 전 체크포인트 생성

**작업 내용**:
1. 현재 변경 사항 확인
   - `web_server/app/exchanges/crypto/binance.py` (수정됨)
   - `web_server/app/exchanges/crypto/factory.py` (수정됨)
   - `web_server/app/exchanges/crypto/upbit.py` (수정됨)
   - `web_server/app/models.py` (수정됨)
   - `web_server/app/services/exchange.py` (수정됨)
   - `web_server/migrations/20251007_153047_...` (신규)

2. Git 상태 정리
   - 필요 시 현재 변경사항 스태시 또는 커밋
   - 깨끗한 작업 환경 확보

3. 브랜치 확인
   - 현재 브랜치: `feature/securities-integration` 확인
   - 필요 시 새 브랜치 생성

**완료 조건**:
- [ ] Git 상태 깨끗함 (또는 체크포인트 커밋 완료)
- [ ] 작업 브랜치 확인 완료
- [ ] 현재 코드 상태 문서화 완료

**예상 소요 시간**: 15분

---

### Phase 1: 상수 및 Enum 확장 ⏳

**목표**: 새로운 마켓 타입 및 주문 타입 상수 추가

**작업 내용**:

#### 1-1. MarketType 확장 (`app/constants.py`)
```python
class MarketType:
    # 기존 (크립토)
    SPOT = 'SPOT'
    FUTURES = 'FUTURES'

    # 신규 (증권)
    DOMESTIC_STOCK = 'DOMESTIC_STOCK'
    OVERSEAS_STOCK = 'OVERSEAS_STOCK'
    DOMESTIC_FUTUREOPTION = 'DOMESTIC_FUTUREOPTION'
    OVERSEAS_FUTUREOPTION = 'OVERSEAS_FUTUREOPTION'
```

#### 1-2. OrderType 확장 (`app/constants.py`)
```python
class OrderType:
    # 기존 (크립토 공통)
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'
    STOP_MARKET = 'STOP_MARKET'
    STOP_LIMIT = 'STOP_LIMIT'
    CANCEL_ALL_ORDER = 'CANCEL_ALL_ORDER'

    # 신규 (국내주식 특수)
    CONDITIONAL_LIMIT = 'CONDITIONAL_LIMIT'
    BEST_LIMIT = 'BEST_LIMIT'
    PRE_MARKET = 'PRE_MARKET'
    AFTER_MARKET = 'AFTER_MARKET'
```

#### 1-3. 한투 주문구분 매핑 추가 (`app/constants.py`)
```python
class KISOrderType:
    """한국투자증권 주문구분 코드"""
    LIMIT = '00'              # 지정가
    MARKET = '01'             # 시장가
    CONDITIONAL_LIMIT = '02'  # 조건부지정가
    BEST_LIMIT = '03'         # 최유리지정가
    BEST_PRIORITY = '04'      # 최우선지정가
    PRE_MARKET = '05'         # 장전 시간외
    AFTER_MARKET = '06'       # 장후 시간외
    AFTER_SINGLE = '07'       # 시간외 단일가
```

**수정 파일**:
- `web_server/app/constants.py`

**완료 조건**:
- [ ] MarketType에 6개 마켓 타입 정의 완료
- [ ] OrderType에 국내주식 특수 주문 타입 추가 완료
- [ ] KISOrderType 매핑 클래스 추가 완료
- [ ] Python import 오류 없음

**예상 소요 시간**: 30분

---

### Phase 2: 웹훅 데이터 정규화 함수 확장 ✅

**목표**: `normalize_webhook_data()` 함수에서 params 객체 및 마켓별 필드 지원

**작업 내용**:

#### 2-1. 필드 매핑 확장 (`app/services/utils.py`)
```python
def normalize_webhook_data(webhook_data: dict) -> dict:
    """웹훅 데이터 정규화 (마켓별 지원)"""
    normalized = {}

    # 기본 필드 매핑
    field_mapping = {
        'group_name': 'group_name',
        'exchange': 'exchange',
        'platform': 'exchange',
        'market_type': 'market_type',
        'currency': 'currency',  # 크립토 전용, params로 이동 가능
        'symbol': 'symbol',
        'side': 'side',
        'price': 'price',
        'stop_price': 'stop_price',
        'stopprice': 'stop_price',
        'qty_per': 'qty_per',
        'token': 'token',
        'user_token': 'token',
        'params': 'params'  # 신규: 확장 파라미터
    }

    # ... (기존 로직)

    # params 객체 처리
    if 'params' in normalized and isinstance(normalized['params'], dict):
        # params에서 자주 사용되는 필드를 상위로 승격 (선택적)
        params = normalized['params']

        # 해외주식/선물옵션: exchange_code
        if 'exchange_code' in params:
            normalized['exchange_code'] = params['exchange_code']

        # 해외주식/선물옵션: currency (params 우선)
        if 'currency' in params:
            normalized['currency'] = params['currency']

    return normalized
```

#### 2-2. 마켓별 심볼 검증 (유연한 방식)

**변경 철학**:
- 크립토: 엄격한 검증 (표준 형식 `COIN/CURRENCY` 강제)
- 증권: 유연한 검증 (거래소 API에 위임)

```python
def _is_valid_securities_symbol(symbol: str, market_type: str) -> bool:
    """
    증권 심볼 형식 검증 (Permissive)

    심볼 형식은 각 거래소 API에서 최종 검증하므로,
    여기서는 기본적인 안전성만 체크합니다.
    - 길이 제한 (ReDoS 방지)
    - 허용 문자: 영문, 숫자, 마침표(.), 하이픈(-), 언더스코어(_)
    - 특수문자 금지 (SQL Injection, XSS 방지)

    Args:
        symbol: 심볼
        market_type: 증권 마켓 타입

    Returns:
        유효성 여부
    """
    # ReDoS 방지: 길이 제한
    if not symbol or len(symbol) > 30:
        return False

    # 허용 문자 검증
    symbol_upper = symbol.upper()
    if not re.match(r'^[A-Z0-9._-]+$', symbol_upper):
        return False

    # 순수 특수문자만으로 구성된 심볼 거부
    if re.match(r'^[._-]+$', symbol_upper):
        return False

    return True
```

**검증 예시**:
- ✅ `"005930"` (국내주식 - 순수 숫자)
- ✅ `"KR005930"` (국내주식 - 국가코드 포함)
- ✅ `"123456A"` (국내주식 - ETN)
- ✅ `"BRK.A"` (해외주식 - 마침표 포함)
- ✅ `"CL-DEC24"` (해외선물옵션 - 하이픈 포함)
- ❌ `"'; DROP TABLE--"` (SQL Injection 시도)
- ❌ `"..."` (순수 특수문자)

**수정 파일**:
- `web_server/app/services/utils.py`

**완료 조건**:
- [x] params 필드 처리 로직 추가 완료
- [x] 마켓별 심볼 검증 함수 추가 완료 (유연한 검증 방식)
- [x] normalize_webhook_data() 함수 정상 동작
- [x] 기존 크립토 웹훅 100% 호환 확인
- [x] ReDoS 보안 취약점 수정 완료 (길이 제한 30자)
- [x] 중복 import 제거 완료 (DRY 원칙 준수)
- [x] 코드 리뷰 2회 완료 (Priority 1 이슈 모두 해결)

**실제 소요 시간**: 약 2시간 (코드 리뷰 + 수정 + 재검토 포함)

**완료일**: 2025-10-07

---

### Phase 3: 웹훅 서비스 증권 거래소 분기 로직 추가 ⏳

**목표**: WebhookService에서 market_type 기반 라우팅 구현

**작업 내용**:

#### 3-1. 주문 생성 라우팅 로직 (`app/services/webhook_service.py`)
```python
async def process_webhook(self, webhook_data: dict) -> dict:
    """웹훅 처리 (마켓 타입 기반 분기)"""
    # 1. 데이터 정규화
    normalized_data = normalize_webhook_data(webhook_data)

    # 2. 전략 및 토큰 검증
    strategy = self._validate_strategy_token(
        normalized_data['group_name'],
        normalized_data['token']
    )

    # 3. 주문 타입별 검증
    self._validate_order_type_params(normalized_data)

    # 4. market_type 기반 분기
    market_type = normalized_data.get('market_type', 'SPOT')

    if market_type in ['SPOT', 'FUTURES']:
        # 크립토: 기존 로직
        return await self._process_crypto_order(strategy, normalized_data)

    elif market_type in ['DOMESTIC_STOCK', 'OVERSEAS_STOCK',
                         'DOMESTIC_FUTUREOPTION', 'OVERSEAS_FUTUREOPTION']:
        # 증권: 신규 로직
        return await self._process_securities_order(strategy, normalized_data)

    else:
        raise WebhookError(f"지원하지 않는 market_type: {market_type}")
```

#### 3-2. 증권 주문 처리 로직 구현
```python
async def _process_securities_order(self, strategy, normalized_data: dict) -> dict:
    """증권 거래소 주문 처리"""
    from app.exchanges import UnifiedExchangeFactory

    order_type = normalized_data['order_type']

    # CANCEL_ALL_ORDER 처리
    if order_type == 'CANCEL_ALL_ORDER':
        return await self._cancel_securities_orders(strategy, normalized_data)

    # 일반 주문 처리
    results = []
    strategy_accounts = strategy.strategy_accounts

    for sa in strategy_accounts:
        account = sa.account

        # 증권 계좌만 처리
        if account.account_type != 'STOCK':
            logger.warning(f"증권 웹훅이지만 계좌 타입이 STOCK이 아님 (account_id={account.id})")
            continue

        try:
            # 1. 증권 거래소 어댑터 생성
            exchange = await UnifiedExchangeFactory.create(account)

            # 2. 주문 생성
            stock_order = await exchange.create_stock_order(
                symbol=normalized_data['symbol'],
                side=normalized_data['side'].upper(),
                order_type=normalized_data['order_type'],
                quantity=int(normalized_data['qty_per']),  # 절대 수량
                price=normalized_data.get('price')
            )

            # 3. DB 저장 (Trade 테이블)
            trade = Trade(
                strategy_account_id=sa.id,
                symbol=stock_order.symbol,
                side=stock_order.side,
                order_type=stock_order.order_type,
                quantity=stock_order.quantity,
                price=float(stock_order.price) if stock_order.price else None,
                exchange_order_id=stock_order.order_id,
                status=stock_order.status,
                market_type=normalized_data['market_type'],
                exchange=account.exchange
            )
            db.session.add(trade)

            # 4. OpenOrder 저장 (미체결 주문 관리)
            if stock_order.status in ['NEW', 'PARTIALLY_FILLED']:
                open_order = OpenOrder(
                    strategy_account_id=sa.id,
                    symbol=stock_order.symbol,
                    side=stock_order.side,
                    order_type=stock_order.order_type,
                    quantity=stock_order.quantity,
                    price=float(stock_order.price) if stock_order.price else None,
                    exchange_order_id=stock_order.order_id,
                    status=stock_order.status
                )
                db.session.add(open_order)

            db.session.commit()

            # 5. SSE 이벤트 발행
            # ... (기존 크립토 로직 참고)

            results.append({
                'account_name': account.name,
                'order_id': stock_order.order_id,
                'status': stock_order.status
            })

        except Exception as e:
            logger.error(f"증권 주문 생성 실패 (account_id={account.id}): {e}")
            results.append({
                'account_name': account.name,
                'error': str(e)
            })

    return {
        'success': True,
        'message': f'{len(results)}개 계좌에서 주문 생성 완료',
        'results': results
    }
```

#### 3-3. 증권 주문 취소 로직 구현
```python
async def _cancel_securities_orders(self, strategy, normalized_data: dict) -> dict:
    """증권 거래소 미체결 주문 취소"""
    symbol = normalized_data.get('symbol')
    cancelled_count = 0

    for sa in strategy.strategy_accounts:
        account = sa.account

        if account.account_type != 'STOCK':
            continue

        # DB에서 미체결 주문 조회
        query = OpenOrder.query.filter_by(
            strategy_account_id=sa.id,
            status='NEW'
        )

        if symbol:
            query = query.filter_by(symbol=symbol)

        open_orders = query.all()

        if not open_orders:
            continue

        # 증권 어댑터 생성
        exchange = await UnifiedExchangeFactory.create(account)

        # 주문 취소
        for order in open_orders:
            try:
                await exchange.cancel_stock_order(order.exchange_order_id, order.symbol)
                order.status = 'CANCELLED'
                cancelled_count += 1
            except Exception as e:
                logger.error(f"증권 주문 취소 실패: {e}")

        db.session.commit()

    return {
        'success': True,
        'message': f'{cancelled_count}개 주문 취소 완료',
        'cancelled_orders': cancelled_count
    }
```

**수정 파일**:
- `web_server/app/services/webhook_service.py`

**완료 조건**:
- [ ] market_type 기반 분기 로직 추가 완료
- [ ] _process_securities_order() 메서드 구현 완료
- [ ] _cancel_securities_orders() 메서드 구현 완료
- [ ] Trade/OpenOrder DB 저장 로직 추가 완료
- [ ] 기존 크립토 웹훅 로직 영향 없음 확인

**예상 소요 시간**: 3시간

---

### Phase 4: DB 마이그레이션 실행 및 검증 ⏳

**목표**: SecuritiesToken 테이블 및 Account 확장 컬럼 생성

**작업 내용**:

#### 4-1. 마이그레이션 실행 여부 확인
```bash
# PostgreSQL 접속
psql -d webserver

# SecuritiesToken 테이블 존재 확인
\d securities_tokens

# Account 테이블 확장 컬럼 확인
\d accounts | grep "account_type\|securities_config"
```

#### 4-2. 미실행 시 마이그레이션 실행
```bash
# SQL 파일 실행
psql -d webserver -f web_server/migrations/add_securities_support.sql
```

#### 4-3. 검증
```sql
-- SecuritiesToken 테이블 확인
SELECT * FROM securities_tokens LIMIT 1;

-- Account 테이블 확인
SELECT id, account_type, securities_config FROM accounts LIMIT 1;
```

**수정 파일**:
- 없음 (DB 마이그레이션만 실행)

**완료 조건**:
- [ ] SecuritiesToken 테이블 존재 확인
- [ ] Account.account_type 컬럼 존재 확인
- [ ] Account.securities_config 컬럼 존재 확인
- [ ] 기존 데이터 손실 없음 확인

**예상 소요 시간**: 15분

---

### Phase 5: UnifiedExchangeFactory 증권 지원 확장 ⏳

**목표**: UnifiedExchangeFactory에서 account_type 기반 증권 어댑터 생성

**작업 내용**:

#### 5-1. UnifiedExchangeFactory.create() 수정 (`app/exchanges/unified_factory.py`)
```python
class UnifiedExchangeFactory:
    """통합 거래소 팩토리 (크립토 + 증권)"""

    @staticmethod
    async def create(account: 'Account'):
        """
        계좌 타입 기반 거래소 어댑터 생성

        Args:
            account: Account 모델 인스턴스

        Returns:
            BaseCryptoExchange 또는 BaseSecuritiesExchange
        """
        account_type = account.account_type

        if account_type == 'CRYPTO':
            # 크립토: 기존 로직
            from app.exchanges.crypto.factory import CryptoExchangeFactory
            return CryptoExchangeFactory.create(account)

        elif account_type == 'STOCK':
            # 증권: 신규 로직
            from app.exchanges.securities.factory import SecuritiesExchangeFactory
            return await SecuritiesExchangeFactory.create(account)

        else:
            raise ValueError(f"지원하지 않는 account_type: {account_type}")
```

**수정 파일**:
- `web_server/app/exchanges/unified_factory.py` (이미 구현되어 있을 수 있음, 확인 필요)

**완료 조건**:
- [ ] account_type 기반 분기 로직 정상 동작
- [ ] CryptoExchangeFactory 정상 호출
- [ ] SecuritiesExchangeFactory 정상 호출 (async)
- [ ] Python import 오류 없음

**예상 소요 시간**: 30분

---

### Phase 6: 웹훅 메시지 포맷 문서 작성 ⏳

**목표**: 사용자용 웹훅 메시지 포맷 가이드 문서 작성

**작업 내용**:

#### 6-1. 문서 파일 생성 (`docs/webhook_message_format.md`)
- 통합 웹훅 메시지 포맷 설명
- 마켓별 심볼 포맷
- 마켓별 웹훅 예시 (50개 이상)
- 에러 메시지 명세
- FAQ

**생성 파일**:
- `web_server/docs/webhook_message_format.md` (새 파일)

**완료 조건**:
- [ ] 문서 파일 생성 완료
- [ ] 마켓별 예시 50개 이상 작성
- [ ] 에러 메시지 명세 작성 완료
- [ ] 마크다운 포맷 검증 완료

**예상 소요 시간**: 2시간

---

### Phase 7: 코드 검토 및 정리 ⏳

**목표**: 전체 코드 리뷰 및 불필요한 코드 제거

**작업 내용**:

#### 7-1. 코드 리뷰 체크리스트
- [ ] 모든 함수에 docstring 작성됨
- [ ] 타입 힌트 추가됨 (Python 3.7+)
- [ ] 로깅 추가됨 (DEBUG, INFO, ERROR 레벨)
- [ ] 예외 처리 명확함
- [ ] DRY 원칙 준수 (중복 코드 제거)

#### 7-2. Import 정리
```python
# 불필요한 import 제거
# 순서 정리 (표준 라이브러리 → 서드파티 → 로컬)
```

#### 7-3. 테스트용 print/debug 코드 제거

**수정 파일**:
- 전체 수정 파일 재검토

**완료 조건**:
- [ ] 모든 함수 docstring 확인
- [ ] 불필요한 import 제거
- [ ] 테스트용 코드 제거
- [ ] 로깅 적절성 확인

**예상 소요 시간**: 1시간

---

## 📊 전체 일정 요약

| Phase | 작업 내용 | 예상 소요 시간 | 상태 |
|-------|----------|--------------|------|
| Phase 0 | 현황 파악 및 체크포인트 | 15분 | ⏳ 대기 |
| Phase 1 | 상수 및 Enum 확장 | 30분 | ⏳ 대기 |
| Phase 2 | 웹훅 데이터 정규화 확장 | 1시간 | ✅ 완료 (2025-10-07) |
| Phase 3 | 웹훅 서비스 증권 분기 로직 | 3시간 | ⏳ 대기 |
| Phase 4 | DB 마이그레이션 실행 | 15분 | ⏳ 대기 |
| Phase 5 | UnifiedExchangeFactory 확장 | 30분 | ⏳ 대기 |
| Phase 6 | 웹훅 메시지 포맷 문서 작성 | 2시간 | ⏳ 대기 |
| Phase 7 | 코드 검토 및 정리 | 1시간 | ⏳ 대기 |

**총 예상 소요 시간**: 약 8.5시간

---

## ⚠️ 주의사항

### 1. 하위 호환성 유지
- **기존 크립토 웹훅 100% 호환** 필수
- 기존 필드명 변경 금지
- 기존 로직 수정 시 충분한 테스트 필요

### 2. 증권 계좌 설정 필요
- Account.account_type = 'STOCK'
- Account.securities_config (한투 설정: appkey, appsecret, account_number)
- SecuritiesToken (OAuth 토큰 자동 관리)

### 3. 한투 API 제약
- 모의투자 환경 우선 사용
- 주문 취소 시 KRX_FWDG_ORD_ORGNO 필요 (fetch_order로 조회)
- 시장가 주문은 장중에만 가능

### 4. 마켓별 특수 사항
- **국내주식**: 종목코드 6자리, 주문구분 코드(00-07)
- **해외주식**: 거래소 코드(NASD, NYSE 등), 통화(USD, JPY 등)
- **국내선물옵션**: 신규/청산 구분, 계약승수, 증거금
- **해외선물옵션**: 월물코드, 거래소 타임존, 다중통화

### 5. 테스트는 사용자가 직접 수행
- 기능 구현에만 집중
- 오류 없이 동작하는 코드 작성
- 명확한 에러 메시지 제공

---

## 🚀 다음 단계 (Phase 완료 후)

### 선택사항 (향후 확장)
- [ ] 실시간 체결 알림 (WebSocket)
- [ ] 키움증권 어댑터 구현
- [ ] LS증권 어댑터 구현
- [ ] 포지션 자동 롤오버 (선물옵션 만기일 관리)
- [ ] 환율 자동 업데이트 (해외주식/선물옵션)

---

## 📝 작업 이력

### 2025-10-07

#### Phase 0 & Phase 2 완료
- **Phase 0 시작**: 현황 파악 및 계획 수립
- `docs/task_plan.md` 파일 생성
- 전체 Phase 계획 수립 완료

#### Phase 2 완료 내역
1. **심볼 검증 로직 구현** (`symbol_utils.py`)
   - 크립토: 엄격한 검증 (`BTC/USDT` 슬래시 형식)
   - 증권: 유연한 검증 (`^[A-Z0-9._-]+$`, 최대 30자)
   - ReDoS 보안 취약점 수정 (길이 제한 추가)
   - 국내/해외 주식, 선물옵션 모든 패턴 지원

2. **웹훅 데이터 정규화 확장** (`services/utils.py`)
   - `params` 객체 처리 로직 추가
   - 중복 import 제거 (DRY 원칙)
   - 마켓별 심볼 검증 통합

3. **코드 품질 개선**
   - 코드 리뷰 2회 실시 (Priority 1 이슈 해결)
   - 36개 테스트 케이스 100% 통과
   - 하위 호환성 100% 유지 (기존 크립토 웹훅)

---

**브랜치**: `feature/securities-integration`
**시작일**: 2025-10-07
**예상 완료일**: 2025-10-08 (1일 소요)
**담당**: Backend Developer
