# Phase 3: 웹훅 서비스 증권 거래소 분기 로직 구현 - 상세 계획서

## 📋 개요

**목표**: WebhookService에서 market_type 기반으로 크립토/증권 거래를 자동 라우팅하는 로직 구현

**담당**: Backend Developer Agent

**예상 소요 시간**: 3시간

**작업일**: 2025-10-07

---

## 🎯 핵심 요구사항

### 1. 기존 아키텍처 이해

현재 코드베이스는 다음과 같은 구조를 가지고 있습니다:

- **WebhookService** (`webhook_service.py`): 웹훅 처리 진입점
  - 현재 모든 주문을 `trading_service.process_trading_signal()`로 위임
  - 크립토 전용으로 설계됨

- **TradingService** (추정 경로: `services/trading/`): 거래 신호 처리
  - 크립토 거래 로직 포함
  - exchange_service를 통해 거래소 API 호출

- **UnifiedExchangeFactory** (`exchanges/unified_factory.py`): 이미 구현됨
  - `account.account_type` 기반으로 Crypto/Securities 분기
  - CryptoExchangeFactory, SecuritiesExchangeFactory 호출

### 2. 제약사항

1. **하위 호환성 유지**: 기존 크립토 웹훅은 100% 정상 동작해야 함
2. **테스트 금지**: 코드 구현만 진행, 테스트는 사용자가 직접 수행
3. **단일 소스 원칙**: 중복 코드 금지, 기존 함수 최대한 재사용
4. **CLAUDE.md 준수**: 스파게티 방지 지침 엄격히 적용

---

## 🔍 현재 코드 분석 결과

### WebhookService.process_webhook() 흐름

```python
def process_webhook(self, webhook_data: Dict[str, Any], webhook_received_at: Optional[float] = None):
    # 1. 데이터 정규화
    normalized_data = normalize_webhook_data(webhook_data)

    # 2. 전략 및 토큰 검증
    strategy = self._validate_strategy_token(group_name, token)

    # 3. 주문 타입별 검증
    if OrderType.is_trading_type(order_type):
        self._validate_order_type_params(normalized_data)

    # 4. 주문 처리 분기 (현재)
    if order_type == OrderType.CANCEL_ALL_ORDER:
        result = self.process_cancel_all_orders(...)
    elif order_type == OrderType.CANCEL:
        result = self.process_cancel_order(...)
    else:
        # ⚠️ 문제: 모든 거래를 trading_service로 위임 (크립토 전용)
        result = trading_service.process_trading_signal(normalized_data, timing_context)
```

### 필요한 변경사항

**현재**: 모든 거래 → `trading_service` (크립토 전용)

**변경 후**:
- `market_type in ['SPOT', 'FUTURES']` → `trading_service` (크립토)
- `market_type in ['DOMESTIC_STOCK', 'OVERSEAS_STOCK', 'DOMESTIC_FUTUREOPTION', 'OVERSEAS_FUTUREOPTION']` → 새로운 증권 처리 로직

---

## 📝 구현 작업 상세

### 작업 1: WebhookService에 market_type 분기 로직 추가

**파일**: `web_server/app/services/webhook_service.py`

**위치**: `process_webhook()` 메서드의 주문 처리 블록 (약 185-221줄)

**구현 내용**:

```python
# 기존 코드 (185-221줄):
if order_type == OrderType.CANCEL_ALL_ORDER:
    result = self.process_cancel_all_orders(normalized_data, webhook_received_at)
elif order_type == OrderType.CANCEL:
    result = self.process_cancel_order(normalized_data, webhook_received_at)
else:
    # 거래 신호는 trading_service로 위임
    from app.services.trading import trading_service
    # ... 기존 로직

# 변경 후:
if order_type == OrderType.CANCEL_ALL_ORDER:
    # market_type 기반 취소 로직 분기
    market_type = normalized_data.get('market_type', MarketType.SPOT)

    if MarketType.is_crypto(market_type):
        result = self.process_cancel_all_orders(normalized_data, webhook_received_at)
    else:
        result = self._cancel_securities_orders(strategy, normalized_data, webhook_received_at)

elif order_type == OrderType.CANCEL:
    result = self.process_cancel_order(normalized_data, webhook_received_at)
else:
    # market_type 기반 거래 처리 분기
    market_type = normalized_data.get('market_type', MarketType.SPOT)

    if MarketType.is_crypto(market_type):
        # 크립토: 기존 로직
        from app.services.trading import trading_service
        # ... 기존 로직 유지
        result = trading_service.process_trading_signal(normalized_data, timing_context)
    elif MarketType.is_securities(market_type):
        # 증권: 신규 로직
        result = self._process_securities_order(strategy, normalized_data, timing_context)
    else:
        raise WebhookError(f"지원하지 않는 market_type: {market_type}")
```

**핵심 포인트**:
- `market_type` 기본값은 `SPOT` (기존 크립토 웹훅 호환)
- `MarketType.is_crypto()`, `MarketType.is_securities()` 헬퍼 메서드 사용 (이미 구현됨)
- 기존 크립토 로직은 **한 줄도 수정하지 않음**

---

### 작업 2: 증권 주문 처리 메서드 구현

**파일**: `web_server/app/services/webhook_service.py`

**새로 추가할 메서드**: `_process_securities_order()`

**위치**: 클래스 메서드 끝부분 (기존 메서드 다음)

**구현 내용**:

```python
def _process_securities_order(
    self,
    strategy: Strategy,
    normalized_data: Dict[str, Any],
    timing_context: Dict[str, float]
) -> Dict[str, Any]:
    """
    증권 거래소 주문 처리

    Args:
        strategy: 검증된 Strategy 객체
        normalized_data: 정규화된 웹훅 데이터
        timing_context: 타이밍 정보 (webhook_received_at, trade_started_at 등)

    Returns:
        dict: 주문 처리 결과
        {
            'success': bool,
            'message': str,
            'results': [
                {
                    'account_name': str,
                    'order_id': str,
                    'status': str
                }
            ],
            'timing': {...}
        }

    Raises:
        WebhookError: 주문 처리 실패 시
    """
    from app.exchanges import UnifiedExchangeFactory
    from app.models import Trade, OpenOrder
    import time

    logger.info(f"🏛️ 증권 주문 처리 시작 - 전략: {strategy.group_name}, "
                f"심볼: {normalized_data.get('symbol')}, "
                f"side: {normalized_data.get('side')}")

    # 필수 필드 검증
    required_fields = ['symbol', 'side', 'order_type']
    for field in required_fields:
        if field not in normalized_data:
            raise WebhookError(f"증권 주문에 필수 필드 누락: {field}")

    # 전략에 연결된 계좌 조회
    strategy_accounts = strategy.strategy_accounts
    if not strategy_accounts:
        raise WebhookError(f"전략 '{strategy.group_name}'에 연결된 계좌가 없습니다")

    results = []
    successful_orders = 0
    failed_orders = 0

    for sa in strategy_accounts:
        account = sa.account

        # 증권 계좌만 처리
        if account.account_type != 'STOCK':
            logger.warning(f"⚠️ 증권 웹훅이지만 계좌 타입이 STOCK이 아님 "
                          f"(account_id={account.id}, type={account.account_type})")
            continue

        try:
            # 1. 증권 거래소 어댑터 생성
            trade_request_start = time.time()
            exchange = UnifiedExchangeFactory.create(account)

            # 2. 주문 생성 (거래소 API 호출)
            order_params = {
                'symbol': normalized_data['symbol'],
                'side': normalized_data['side'].upper(),
                'order_type': normalized_data['order_type'],
                'quantity': int(normalized_data.get('qty_per', 0)),
                'price': normalized_data.get('price')
            }

            logger.info(f"📤 증권 주문 생성 시도 (계좌={account.name}): {order_params}")

            # create_order 또는 create_stock_order 메서드 호출 (어댑터에 따라)
            stock_order = exchange.create_order(**order_params)

            trade_request_end = time.time()

            logger.info(f"✅ 증권 주문 생성 완료 - order_id: {stock_order.order_id}, "
                       f"status: {stock_order.status}")

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
                market_type=normalized_data.get('market_type'),
                exchange=account.exchange,
                # 타이밍 정보
                webhook_received_at=timing_context.get('webhook_received_at'),
                trade_requested_at=trade_request_start,
                trade_responded_at=trade_request_end
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

            # 5. SSE 이벤트 발행 (기존 크립토 로직 참고)
            self._emit_order_event(
                account_id=account.id,
                order_id=stock_order.order_id,
                symbol=stock_order.symbol,
                side=stock_order.side,
                order_type=stock_order.order_type,
                status=stock_order.status,
                quantity=stock_order.quantity,
                price=stock_order.price,
                event_type='order_created'
            )

            results.append({
                'account_name': account.name,
                'order_id': stock_order.order_id,
                'status': stock_order.status,
                'symbol': stock_order.symbol,
                'side': stock_order.side
            })
            successful_orders += 1

        except Exception as e:
            logger.error(f"❌ 증권 주문 생성 실패 (account_id={account.id}, "
                        f"account_name={account.name}): {e}", exc_info=True)
            results.append({
                'account_name': account.name,
                'error': str(e),
                'status': 'failed'
            })
            failed_orders += 1

    # 6. 결과 반환
    if not results:
        raise WebhookError("처리할 증권 계좌가 없습니다. STOCK 타입 계좌를 확인하세요.")

    return {
        'success': successful_orders > 0,
        'message': f'증권 주문 처리 완료 - 성공: {successful_orders}, 실패: {failed_orders}',
        'results': results,
        'summary': {
            'total_accounts': len(results),
            'successful': successful_orders,
            'failed': failed_orders
        },
        'timing': timing_context  # 타이밍 정보 전달
    }
```

**핵심 포인트**:
- Trade, OpenOrder 모델에 데이터 저장 (기존 크립토와 동일)
- SSE 이벤트 발행 (실시간 알림)
- 계좌별 처리 결과 수집 (일부 실패해도 전체 진행)
- 상세한 로깅 (디버깅 용이성)

---

### 작업 3: 증권 주문 취소 메서드 구현

**파일**: `web_server/app/services/webhook_service.py`

**새로 추가할 메서드**: `_cancel_securities_orders()`

**구현 내용**:

```python
def _cancel_securities_orders(
    self,
    strategy: Strategy,
    normalized_data: Dict[str, Any],
    webhook_received_at: float
) -> Dict[str, Any]:
    """
    증권 거래소 미체결 주문 취소 (CANCEL_ALL_ORDER 타입)

    Args:
        strategy: 검증된 Strategy 객체
        normalized_data: 정규화된 웹훅 데이터
        webhook_received_at: 웹훅 수신 시각

    Returns:
        dict: 취소 처리 결과
        {
            'success': bool,
            'message': str,
            'cancelled_orders': int,
            'results': [...]
        }
    """
    from app.exchanges import UnifiedExchangeFactory
    from app.models import OpenOrder

    symbol = normalized_data.get('symbol')  # 선택적 (특정 심볼만 취소)

    logger.info(f"🏛️ 증권 주문 취소 시작 - 전략: {strategy.group_name}, "
                f"심볼: {symbol or '전체'}")

    cancelled_count = 0
    failed_count = 0
    results = []

    for sa in strategy.strategy_accounts:
        account = sa.account

        # 증권 계좌만 처리
        if account.account_type != 'STOCK':
            continue

        try:
            # DB에서 미체결 주문 조회
            query = OpenOrder.query.filter_by(
                strategy_account_id=sa.id,
                status='NEW'
            )

            # 심볼 필터 (선택적)
            if symbol:
                query = query.filter_by(symbol=symbol)

            open_orders = query.all()

            if not open_orders:
                logger.info(f"ℹ️ 취소할 미체결 주문 없음 (계좌={account.name}, 심볼={symbol or '전체'})")
                continue

            logger.info(f"📋 취소 대상 주문: {len(open_orders)}개 (계좌={account.name})")

            # 증권 어댑터 생성
            exchange = UnifiedExchangeFactory.create(account)

            # 주문 취소
            account_cancelled = 0
            account_failed = 0

            for order in open_orders:
                try:
                    # 거래소 API 호출
                    exchange.cancel_order(
                        order_id=order.exchange_order_id,
                        symbol=order.symbol
                    )

                    # DB 상태 업데이트
                    order.status = 'CANCELLED'

                    # SSE 이벤트 발행
                    self._emit_order_event(
                        account_id=account.id,
                        order_id=order.exchange_order_id,
                        symbol=order.symbol,
                        side=order.side,
                        order_type=order.order_type,
                        status='CANCELLED',
                        quantity=order.quantity,
                        price=order.price,
                        event_type='order_cancelled'
                    )

                    account_cancelled += 1
                    logger.info(f"✅ 주문 취소 완료 - order_id: {order.exchange_order_id}")

                except Exception as e:
                    logger.error(f"❌ 주문 취소 실패 - order_id: {order.exchange_order_id}, "
                               f"error: {e}")
                    account_failed += 1

            db.session.commit()

            cancelled_count += account_cancelled
            failed_count += account_failed

            results.append({
                'account_name': account.name,
                'cancelled': account_cancelled,
                'failed': account_failed
            })

        except Exception as e:
            logger.error(f"❌ 증권 주문 취소 실패 (account_id={account.id}): {e}",
                        exc_info=True)
            results.append({
                'account_name': account.name,
                'error': str(e)
            })

    # 결과 메시지 생성
    if cancelled_count == 0 and failed_count == 0:
        message = "취소할 미체결 주문이 없습니다"
    else:
        message = f"증권 주문 취소 완료 - 성공: {cancelled_count}, 실패: {failed_count}"

    return {
        'success': True,  # 취소 대상이 없어도 success=True
        'message': message,
        'cancelled_orders': cancelled_count,
        'failed_orders': failed_count,
        'results': results
    }
```

**핵심 포인트**:
- DB 기반 주문 조회 (전략 격리 자동 보장)
- 심볼별 필터링 지원 (선택적)
- 부분 실패 허용 (일부 계좌 실패해도 진행)
- SSE 이벤트 발행

---

### 작업 4: SSE 이벤트 발행 헬퍼 메서드 추가

**파일**: `web_server/app/services/webhook_service.py`

**새로 추가할 메서드**: `_emit_order_event()`

**구현 내용**:

```python
def _emit_order_event(
    self,
    account_id: int,
    order_id: str,
    symbol: str,
    side: str,
    order_type: str,
    status: str,
    quantity: float,
    price: Optional[float],
    event_type: str = 'order_created'
) -> None:
    """
    SSE 이벤트 발행 (주문 생성/취소/체결 알림)

    Args:
        account_id: 계좌 ID
        order_id: 거래소 주문 ID
        symbol: 심볼
        side: 주문 방향 (BUY/SELL)
        order_type: 주문 타입 (LIMIT/MARKET 등)
        status: 주문 상태 (NEW/FILLED/CANCELLED 등)
        quantity: 주문 수량
        price: 주문 가격 (선택적)
        event_type: 이벤트 타입 (order_created/order_cancelled 등)
    """
    try:
        from app.services.event_service import event_service

        event_data = {
            'account_id': account_id,
            'order_id': order_id,
            'symbol': symbol,
            'side': side,
            'order_type': order_type,
            'status': status,
            'quantity': quantity,
            'price': price,
            'timestamp': time.time()
        }

        event_service.emit_order_event(
            account_id=account_id,
            event_type=event_type,
            data=event_data
        )

        logger.debug(f"📡 SSE 이벤트 발행 완료 - event_type: {event_type}, "
                    f"order_id: {order_id}")

    except Exception as e:
        # SSE 이벤트 발행 실패는 치명적 에러가 아님 (경고 로그만 출력)
        logger.warning(f"⚠️ SSE 이벤트 발행 실패: {e}")
```

**핵심 포인트**:
- 기존 `event_service` 활용 (새로운 서비스 생성 X)
- 실패해도 주문 처리는 계속 진행 (비치명적 에러)
- 크립토와 동일한 이벤트 구조 사용

---

## ⚠️ 중요 체크리스트

### 1. 하위 호환성 검증

- [ ] 기존 크립토 웹훅 (market_type 없음) → `SPOT` 기본값 적용
- [ ] 기존 크립토 웹훅 로직 한 줄도 수정 안 됨
- [ ] `MarketType.SPOT`, `MarketType.FUTURES` → 기존 `trading_service` 호출

### 2. 에러 처리

- [ ] 필수 필드 누락 시 명확한 에러 메시지
- [ ] 증권 계좌 없을 때 명확한 안내
- [ ] 일부 계좌 실패해도 전체 진행 (results에 실패 정보 포함)

### 3. 로깅

- [ ] 모든 주요 단계에 DEBUG/INFO/ERROR 로그
- [ ] 계좌별 처리 결과 로깅
- [ ] 타이밍 정보 로깅 (성능 분석용)

### 4. DB 트랜잭션

- [ ] 계좌별 처리 후 `db.session.commit()` (독립적 실패 허용)
- [ ] 예외 발생 시 자동 롤백

### 5. 단일 소스 원칙

- [ ] 중복 코드 없음
- [ ] 기존 헬퍼 메서드 최대한 재사용
- [ ] 새로운 메서드는 명확한 책임 분리

---

## 📚 참고 자료

### 기존 크립토 주문 처리 흐름

**파일**: `web_server/app/services/trading/core.py` (추정)

**흐름**:
1. `trading_service.process_trading_signal()` 호출
2. 전략 계좌 순회
3. `UnifiedExchangeFactory.create(account)` → CryptoExchangeFactory
4. `exchange.create_order()` 호출
5. Trade, OpenOrder DB 저장
6. SSE 이벤트 발행

### 증권 주문 처리 흐름 (신규)

**흐름**:
1. `webhook_service._process_securities_order()` 호출
2. 전략 계좌 순회 (**STOCK 타입만**)
3. `UnifiedExchangeFactory.create(account)` → SecuritiesExchangeFactory
4. `exchange.create_order()` 호출
5. Trade, OpenOrder DB 저장
6. SSE 이벤트 발행

→ **동일한 패턴, 다른 Factory만 사용**

---

## 🚀 구현 순서

### Step 1: WebhookService에 분기 로직 추가 (30분)
- `process_webhook()` 메서드의 주문 처리 블록 수정
- `market_type` 기반 if/elif 분기 추가
- 기존 크립토 로직 유지

### Step 2: 증권 주문 처리 메서드 구현 (1시간 30분)
- `_process_securities_order()` 메서드 작성
- Trade, OpenOrder DB 저장
- SSE 이벤트 발행
- 에러 처리 및 로깅

### Step 3: 증권 주문 취소 메서드 구현 (45분)
- `_cancel_securities_orders()` 메서드 작성
- DB 기반 주문 조회
- 거래소 API 호출
- SSE 이벤트 발행

### Step 4: SSE 헬퍼 메서드 추가 (15분)
- `_emit_order_event()` 메서드 작성
- 기존 event_service 통합

---

## ✅ 완료 조건

- [ ] `market_type` 기반 분기 로직 추가 완료
- [ ] `_process_securities_order()` 메서드 구현 완료
- [ ] `_cancel_securities_orders()` 메서드 구현 완료
- [ ] `_emit_order_event()` 헬퍼 메서드 추가 완료
- [ ] Trade/OpenOrder DB 저장 로직 추가 완료
- [ ] SSE 이벤트 발행 로직 추가 완료
- [ ] 기존 크립토 웹훅 로직 영향 없음 확인 (코드 리뷰)
- [ ] Python import 오류 없음 (문법 검증)
- [ ] 모든 메서드에 docstring 작성 완료
- [ ] 로깅 적절성 확인 (DEBUG/INFO/ERROR 레벨)

---

## 📌 주의사항

### 1. 테스트 금지
- 코드 구현만 진행
- 테스트는 사용자가 직접 수행
- 테스트 코드 작성 금지

### 2. 기존 로직 보존
- 크립토 웹훅 처리 로직은 **한 줄도 수정하지 않음**
- 새로운 메서드만 추가
- 분기 로직만 변경

### 3. CLAUDE.md 준수
- 단일 소스·단일 경로 원칙
- 중복 코드 금지
- 함수 분리는 DRY 목적일 때만

### 4. 에러 메시지 명확성
- "증권 주문에 필수 필드 누락: {field}"
- "처리할 증권 계좌가 없습니다. STOCK 타입 계좌를 확인하세요."
- "지원하지 않는 market_type: {market_type}"

### 5. 로깅 가이드라인
- 🏛️: 증권 처리 시작/완료
- ✅: 성공
- ❌: 실패
- ⚠️: 경고
- 📡: SSE 이벤트
- 📋: 정보

---

## 🔗 연관 파일

### 수정 파일
- `web_server/app/services/webhook_service.py` (주 작업 파일)

### 참조 파일 (읽기 전용)
- `web_server/app/exchanges/unified_factory.py` (UnifiedExchangeFactory)
- `web_server/app/constants.py` (MarketType, OrderType)
- `web_server/app/models.py` (Trade, OpenOrder, Strategy)
- `web_server/app/services/event_service.py` (SSE 이벤트)

---

**작성일**: 2025-10-07
**담당**: Backend Developer Agent
**검토**: 사용자 직접 테스트 예정
