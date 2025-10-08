# 열린 주문 대기열 시스템 구현 계획

**작성일**: 2025-10-08
**상태**: 🟡 설계 단계
**목표**: 거래소별 열린 주문 제한에 대응하는 동적 우선순위 대기열 시스템 구축

---

## 📋 목차

1. [배경 및 목표](#1-배경-및-목표)
2. [핵심 요구사항](#2-핵심-요구사항)
3. [아키텍처 설계](#3-아키텍처-설계)
4. [구현 계획](#4-구현-계획)
5. [진행 상황](#5-진행-상황)
6. [테스트 시나리오](#6-테스트-시나리오)

---

## 1. 배경 및 목표

### 배경

거래소별로 열린 주문 수 제한이 존재:
- **Binance FUTURES**: 심볼당 200개, 조건부 주문 10개
- **Binance SPOT**: 심볼당 25개, 조건부 주문 5개
- **Bybit FUTURES**: 심볼당 500개, 조건부 주문 10개
- **OKX**: 심볼당 500개, 계정당 4000개
- **Upbit SPOT**: 조건부 주문 20개

현재 시스템은 제한 초과 시 주문 실패만 반환하여 사용자 경험 저하.

### 목표

1. **자동 대기열 관리**: 제한 초과 주문을 대기열에 추가
2. **동적 우선순위 재정렬**: 가격/시간 기반 최적 순서로 거래소 실행
3. **실시간 체결 감지**: WebSocket으로 체결 모니터링 → 즉시 대기열 처리
4. **전략 격리 유지**: 주문 생성은 전략별, 대기열 관리는 계정 통합

---

## 2. 핵심 요구사항

### 2.1 동적 제한 계산

**우선순위**:
1. 심볼당 제한 10% (존재 시)
2. 계정당 제한 10% (심볼당 없을 시)
3. 20개 기본값 (모두 없을 시)

**제약 조건**:
- 최대 캡: 심볼당 20개
- 최소: 1개
- STOP 주문: 5개 별도 제한 (일반 카운트에도 포함)

**예시**:
| 거래소 | 마켓 | 심볼당 | 계정당 | 계산 | 최종 |
|--------|------|--------|--------|------|------|
| Binance | FUTURES | 200 | 10000 | 20 | **20개** (캡) |
| Binance | SPOT | 25 | 1000 | 2.5 | **3개** |
| Bybit | FUTURES | 500 | - | 50 | **20개** (캡) |
| Upbit | SPOT | - | - | - | **20개** (기본) |

### 2.2 통합 우선순위 정렬

**레벨 1: 주문 타입** (OrderType.PRIORITY)
- MARKET: 1 (최우선)
- CANCEL: 2
- LIMIT: 3
- STOP_MARKET: 4
- STOP_LIMIT: 5

**레벨 2: 가격 기반**
- **LIMIT 매수**: 가격 높을수록 우선 (예: 105000 > 104000)
- **LIMIT 매도**: 가격 낮을수록 우선 (예: 95000 > 96000)
- **STOP 매수**: stop_price 낮을수록 우선 (예: 90000 > 91000)
- **STOP 매도**: stop_price 높을수록 우선 (예: 110000 > 109000)

**레벨 3: 시간 순서**
- created_at ASC (FIFO)

**정렬 키 계산** (sort_price):
```python
LIMIT BUY:   sort_price = price          # 높을수록 우선 → DESC
LIMIT SELL:  sort_price = -price         # 낮을수록 우선 → DESC 변환
STOP BUY:    sort_price = -stop_price    # 낮을수록 우선 → DESC 변환
STOP SELL:   sort_price = stop_price     # 높을수록 우선 → DESC
MARKET:      sort_price = NULL
```

### 2.3 관리 단위

- **계정+심볼별 큐**: (account_id, symbol) 조합마다 독립적 대기열
- **전략 격리**:
  - 주문 생성/취소: 전략별 격리 유지
  - 대기열 관리: 계정 통합 (rate limit 최적화)

### 2.4 처리 방식

#### MARKET/CANCEL 주문
```
웹훅 수신 → 즉시 실행 (대기열 우회)
```

#### LIMIT/STOP 주문
```
웹훅 수신 → PendingOrder 테이블 추가
  ↓
스케줄러 (1초마다)
  ↓
동적 재정렬 → 거래소 실행
```

#### 체결 감지
```
WebSocket: ORDER_TRADE_UPDATE 이벤트
  ↓
REST API: fetch_order(order_id) 확인
  ↓
DB 업데이트: OpenOrder 상태 변경/삭제
  ↓
즉시 재정렬: rebalance_symbol(account_id, symbol)
```

---

## 3. 아키텍처 설계

### 3.1 컴포넌트 다이어그램

```
┌─────────────────────────────────────────────────┐
│ WebHook Service (Level 3 - Application)        │
│ - MARKET/CANCEL → 즉시 실행                    │
│ - LIMIT/STOP → PendingOrder 추가               │
└────────────┬────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────┐
│ OrderQueueManager (Level 2 - Domain)           │
│ - enqueue(): 대기열 추가                        │
│ - rebalance_symbol(): 동적 재정렬              │
│ - process_next(): 다음 주문 처리               │
└─────┬───────────────────────────────────────┬───┘
      ↓                                       ↓
┌─────────────────────┐         ┌─────────────────────┐
│ ExchangeLimitTracker│         │ OrderFillMonitor    │
│ (Level 2 - Domain)  │         │ (Level 1 - Infra)   │
│ - 제한 계산         │         │ - WebSocket 체결    │
│ - 주문 카운팅       │         │ - REST API 확인     │
└─────────────────────┘         └─────────────────────┘
      ↓                                       ↓
┌─────────────────────────────────────────────────┐
│ Database (PostgreSQL)                           │
│ - OpenOrder: 거래소 실행 주문 (DB 조회)        │
│ - PendingOrder: 대기열 주문                     │
│ - OrderFillEvent: 체결 이벤트 로그              │
└─────────────────────────────────────────────────┘
```

### 3.2 데이터베이스 스키마

#### PendingOrder 테이블 (신규)

```sql
CREATE TABLE pending_orders (
    -- 식별자
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),  -- 계정 레벨 관리
    strategy_account_id INTEGER NOT NULL REFERENCES strategy_accounts(id),  -- 전략 추적

    -- 주문 정보
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,        -- BUY, SELL
    order_type VARCHAR(20) NOT NULL,  -- LIMIT, STOP_LIMIT, STOP_MARKET
    price DECIMAL(20, 8),             -- LIMIT 가격
    stop_price DECIMAL(20, 8),        -- STOP 트리거 가격
    quantity DECIMAL(20, 8) NOT NULL,

    -- 우선순위 계산
    priority INTEGER NOT NULL,         -- OrderType.PRIORITY (1-5)
    sort_price DECIMAL(20, 8),        -- 정렬용 가격 (계산값)

    -- 메타데이터
    market_type VARCHAR(10) NOT NULL,  -- SPOT, FUTURES
    reason VARCHAR(50) NOT NULL DEFAULT 'QUEUE_LIMIT',
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- 인덱스
    INDEX idx_account_symbol (account_id, symbol),
    INDEX idx_priority_sort (account_id, symbol, priority, sort_price DESC, created_at ASC),
    INDEX idx_strategy_tracking (strategy_account_id)
);
```

#### OrderFillEvent 테이블 (신규)

```sql
CREATE TABLE order_fill_events (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    strategy_account_id INTEGER NOT NULL REFERENCES strategy_accounts(id),
    exchange_order_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    filled_quantity DECIMAL(20, 8) NOT NULL,
    average_price DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL,       -- FILLED, PARTIALLY_FILLED, CANCELED
    event_time TIMESTAMP NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_order_id (exchange_order_id),
    INDEX idx_processed (processed, event_time)
);
```

### 3.3 핵심 알고리즘: 동적 재정렬

#### OrderQueueManager.rebalance_symbol()

```python
def rebalance_symbol(self, account_id: int, symbol: str) -> dict:
    """
    특정 심볼의 거래소 주문과 대기열을 통합 재정렬

    처리 단계:
    1. 제한 계산 (ExchangeLimits.calculate_symbol_limit)
    2. OpenOrder 조회 (DB) + PendingOrder 조회 (DB)
    3. 전체 통합 정렬 (priority, sort_price, created_at)
    4. 상위 N개 선택 (STOP 이중 제한 적용)
    5. Sync:
       - 하위로 밀린 거래소 주문 → 취소 + 대기열 이동
       - 상위로 올라온 대기열 주문 → 거래소 실행

    Returns:
        {
            'success': bool,
            'cancelled': int,   # 취소된 주문 수
            'executed': int,    # 실행된 주문 수
            'total_orders': int,
            'active_orders': int,
            'pending_orders': int
        }
    """

    # Step 1: 제한 계산
    limits = ExchangeLimits.calculate_symbol_limit(
        exchange=account.exchange,
        market_type=account.market_type,
        symbol=symbol
    )
    max_orders = limits['max_orders']  # 예: 20
    max_stop_orders = limits['max_stop_orders']  # 예: 5

    # Step 2: 현재 주문 조회 (DB)
    active_orders = OpenOrder.query.join(StrategyAccount).filter(
        StrategyAccount.account_id == account_id,
        OpenOrder.symbol == symbol
    ).all()  # DB 조회 (REST API 아님!)

    pending_orders = PendingOrder.query.filter_by(
        account_id=account_id,
        symbol=symbol
    ).all()

    # Step 3: 통합 정렬
    all_orders = []
    for order in active_orders:
        all_orders.append({
            'source': 'active',
            'db_record': order,
            'priority': OrderType.PRIORITY.get(order.order_type, 999),
            'sort_price': calculate_sort_price(...),
            'created_at': order.created_at,
            'is_stop': order.order_type in ['STOP_LIMIT', 'STOP_MARKET']
        })

    for order in pending_orders:
        all_orders.append({
            'source': 'pending',
            'db_record': order,
            'priority': order.priority,
            'sort_price': order.sort_price,
            'created_at': order.created_at,
            'is_stop': order.order_type in ['STOP_LIMIT', 'STOP_MARKET']
        })

    # 정렬 키: (priority ASC, sort_price DESC, created_at ASC)
    all_orders.sort(key=lambda x: (
        x['priority'],
        -(x['sort_price'] if x['sort_price'] else float('-inf')),
        x['created_at']
    ))

    # Step 4: 상위 N개 선택 (이중 제한)
    selected_orders = []
    stop_count = 0

    for order in all_orders:
        if len(selected_orders) >= max_orders:
            break  # 전체 제한

        if order['is_stop']:
            if stop_count >= max_stop_orders:
                continue  # STOP 제한 초과 → 건너뛰기
            stop_count += 1

        selected_orders.append(order)

    # Step 5: 액션 결정
    to_cancel = []  # 취소할 거래소 주문
    to_execute = []  # 실행할 대기열 주문

    for order in all_orders:
        if order in selected_orders:
            if order['source'] == 'pending':
                to_execute.append(order['db_record'])
        else:
            if order['source'] == 'active':
                to_cancel.append(order['db_record'])

    # Step 6: 실제 실행
    cancelled_count = 0
    for open_order in to_cancel:
        result = cancel_order(open_order.exchange_order_id, symbol, account_id)
        if result['success']:
            move_to_pending(open_order)  # 대기열로 이동
            cancelled_count += 1

    executed_count = 0
    for pending_order in to_execute:
        result = execute_pending_order(pending_order)
        if result['success']:
            db.session.delete(pending_order)  # 대기열에서 제거
            executed_count += 1

    return {
        'success': True,
        'cancelled': cancelled_count,
        'executed': executed_count,
        ...
    }
```

### 3.4 WebSocket 체결 감지 흐름

```python
# OrderFillMonitor 클래스

def on_websocket_message(self, message: dict):
    """
    WebSocket 메시지 수신

    Binance 예시:
    {
        "e": "ORDER_TRADE_UPDATE",
        "o": {
            "s": "BTCUSDT",
            "i": 8886774,
            "X": "FILLED",
            "z": "0.001"
        }
    }
    """
    if message.get('e') == 'ORDER_TRADE_UPDATE':
        order_data = message['o']
        order_id = str(order_data['i'])
        status = order_data['X']

        # REST API로 실제 주문 상태 확인
        confirmed_order = self._confirm_order_status(order_id)

        if confirmed_order:
            # DB 업데이트
            self._update_order_in_db(confirmed_order)

            # 재정렬 트리거
            if status in ['FILLED', 'CANCELED', 'EXPIRED']:
                self.order_queue_manager.rebalance_symbol(
                    account_id=account_id,
                    symbol=order_data['s']
                )

def _confirm_order_status(self, order_id: str) -> dict:
    """
    REST API로 주문 상태 확인

    Returns:
        {
            'order_id': str,
            'status': str,
            'filled_quantity': Decimal,
            'average_price': Decimal,
            ...
        }
    """
    account = self._get_account_from_order_id(order_id)
    exchange = self.exchange_service.get_exchange(account)

    # REST API 호출
    order_info = exchange.fetch_order(
        order_id=order_id,
        symbol=symbol
    )

    return order_info

def _update_order_in_db(self, order_info: dict):
    """DB의 OpenOrder 업데이트 또는 삭제"""
    open_order = OpenOrder.query.filter_by(
        exchange_order_id=order_info['order_id']
    ).first()

    if not open_order:
        return

    if order_info['status'] in ['FILLED', 'CANCELED', 'EXPIRED']:
        # 완료된 주문은 삭제
        db.session.delete(open_order)
    else:
        # 부분 체결은 업데이트
        open_order.status = order_info['status']
        open_order.filled_quantity = order_info['filled_quantity']

    db.session.commit()
```

---

## 4. 구현 계획

### Phase 1: 기반 구조 (1주)

#### 1.1 ExchangeLimits 클래스 구현
- [ ] `web_server/app/constants.py`에 ExchangeLimits 클래스 추가
- [ ] `calculate_symbol_limit()` 메서드 구현
- [ ] 거래소별 제한 상수 정의
- [ ] 단위 테스트 작성

**예상 소요 시간**: 1일

#### 1.2 데이터베이스 마이그레이션
- [ ] PendingOrder 테이블 생성
- [ ] OrderFillEvent 테이블 생성
- [ ] 인덱스 추가
- [ ] 마이그레이션 스크립트 작성 (`scripts/migrations/`)

**예상 소요 시간**: 1일

#### 1.3 ExchangeLimitTracker 구현
- [ ] `web_server/app/services/trading/exchange_limit_tracker.py` 생성
- [ ] `count_active_orders()` 구현 (DB 조회)
- [ ] `can_place_order()` 구현
- [ ] `get_available_slots()` 구현

**예상 소요 시간**: 2일

#### 1.4 테스트 및 검증
- [ ] 제한 계산 로직 단위 테스트
- [ ] DB 마이그레이션 검증

**예상 소요 시간**: 1일

---

### Phase 2: 대기열 관리 (1주)

#### 2.1 OrderQueueManager 기본 구현
- [ ] `web_server/app/services/trading/order_queue_manager.py` 생성
- [ ] `enqueue()` 메서드 구현
- [ ] `_calculate_sort_price()` 구현
- [ ] `get_next_order()` 구현
- [ ] `_move_to_pending()` 구현 (거래소→대기열 이동)

**예상 소요 시간**: 2일

#### 2.2 동적 재정렬 알고리즘
- [ ] `rebalance_symbol()` 메서드 구현
- [ ] 통합 정렬 로직
- [ ] STOP 이중 제한 처리
- [ ] 거래소 주문 취소 로직
- [ ] 대기열 주문 실행 로직

**예상 소요 시간**: 2일

#### 2.3 WebhookService 수정
- [ ] MARKET/CANCEL 즉시 실행 경로 유지
- [ ] LIMIT/STOP → PendingOrder 분기 추가
- [ ] CANCEL_ALL_ORDER 대기열 처리 추가

**예상 소요 시간**: 1일

#### 2.4 TradingService 통합
- [ ] `TradingService.__init__()` 수정 (OrderQueueManager 추가)
- [ ] `execute_trade_with_queue()` 래퍼 메서드 추가
- [ ] 기존 호출 경로 호환성 유지

**예상 소요 시간**: 1일

#### 2.5 테스트
- [ ] 대기열 추가/제거 단위 테스트
- [ ] 재정렬 알고리즘 시나리오 테스트
- [ ] 통합 테스트 (웹훅 → 대기열 → 재정렬)

**예상 소요 시간**: 1일

---

### Phase 3: 스케줄러 통합 (1주)

#### 3.1 스케줄러 함수 구현
- [ ] `rebalance_all_symbols_with_context()` 구현
- [ ] 활성 계정 조회
- [ ] 심볼 목록 추출 (OpenOrder + PendingOrder 합집합)
- [ ] 심볼별 재정렬 루프

**예상 소요 시간**: 2일

#### 3.2 APScheduler 등록
- [ ] `app/__init__.py::register_background_jobs()` 수정
- [ ] 1초 주기 interval trigger 설정
- [ ] max_instances=1 설정
- [ ] 에러 핸들링 및 로깅

**예상 소요 시간**: 1일

#### 3.3 Admin 모니터링 페이지
- [ ] 대기열 현황 API (`/api/admin/queue-status`)
- [ ] 재정렬 통계 표시
- [ ] 수동 재정렬 트리거 버튼

**예상 소요 시간**: 2일

#### 3.4 테스트
- [ ] 스케줄러 작동 검증
- [ ] 1초 주기 성능 테스트
- [ ] 다중 심볼 동시 재정렬 부하 테스트

**예상 소요 시간**: 2일

---

### Phase 4: WebSocket 연동 (1.5주)

#### 4.1 WebSocketManager 구현
- [ ] `web_server/app/services/websocket_manager.py` 생성
- [ ] 연결 풀 관리 (계정별)
- [ ] 자동 재연결 (exponential backoff)
- [ ] Ping/Pong keep-alive
- [ ] 구독/구독 해제 API

**예상 소요 시간**: 3일

#### 4.2 Binance User Data Stream 통합
- [ ] Listen Key 생성 API
- [ ] WebSocket 연결 (`wss://fstream.binance.com/ws/{listenKey}`)
- [ ] ORDER_TRADE_UPDATE 이벤트 파싱
- [ ] Listen Key 갱신 스케줄러 (30분마다)

**예상 소요 시간**: 2일

#### 4.3 OrderFillMonitor 구현
- [ ] `web_server/app/services/order_fill_monitor.py` 생성
- [ ] `on_websocket_message()` 구현
- [ ] `_confirm_order_status()` 구현 (REST API)
- [ ] `_update_order_in_db()` 구현
- [ ] 재정렬 트리거 연동

**예상 소요 시간**: 2일

#### 4.4 심볼별 구독 관리
- [ ] 구독 카운트 추적 (심볼별)
- [ ] OpenOrder 생성 시 구독 증가
- [ ] OpenOrder 삭제 시 구독 감소
- [ ] 카운트 0 시 구독 해제

**예상 소요 시간**: 1일

#### 4.5 테스트
- [ ] WebSocket 연결 안정성 테스트
- [ ] 재연결 로직 검증
- [ ] 체결 이벤트 → 재정렬 E2E 테스트

**예상 소요 시간**: 2일

---

### Phase 5: 안정화 및 최적화 (0.5주)

#### 5.1 에러 처리 강화
- [ ] WebSocket 연결 실패 시 폴백
- [ ] REST API 타임아웃 처리
- [ ] DB 트랜잭션 롤백
- [ ] Telegram 알림 연동

**예상 소요 시간**: 1일

#### 5.2 로깅 및 모니터링
- [ ] 재정렬 실행 로그
- [ ] 대기열 크기 모니터링
- [ ] WebSocket 연결 상태 로그
- [ ] 성능 메트릭 (재정렬 소요 시간)

**예상 소요 시간**: 1일

#### 5.3 성능 최적화
- [ ] DB 쿼리 최적화 (인덱스 활용)
- [ ] 대량 주문 시나리오 테스트 (100개+)
- [ ] 메모리 사용량 프로파일링

**예상 소요 시간**: 1일

---

## 5. 진행 상황

### 전체 진척도

```
Phase 1: 🟩🟩🟩🟩🟩 5/5 (100%) ✅ 완료
Phase 2: 🟩🟩🟩🟩🟩 5/5 (100%) ✅ 완료
Phase 3: 🟩🟩🟩🟩 4/4 (100%) ✅ 완료
Phase 4: ⬜⬜⬜⬜⬜ 0/5 (0%)
Phase 5: ⬜⬜⬜ 0/3 (0%)

전체: 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜ 14/22 (64%)
```

### 현재 단계

🟢 **Phase 1-3 완료** (2025-10-08)

**완료된 작업**:
- ✅ Phase 1: ExchangeLimits, DB 스키마, ExchangeLimitTracker
- ✅ Phase 2: OrderQueueManager, 동적 재정렬, 웹훅 통합
- ✅ Phase 3: APScheduler 통합 (1초 주기), 자동 마이그레이션, Admin API
- ✅ 코드 리뷰 및 개선사항 적용 (Critical 10건, Important 4건 수정)

**검증 완료**:
- ✅ 웹훅 기능 정상 작동 (192ms 처리 시간)
- ✅ 스케줄러 1초마다 재정렬 실행
- ✅ 트랜잭션 무결성 강화
- ✅ PostgreSQL advisory lock (마이그레이션 동시성 제어)
- ✅ 부분 인덱스 최적화 (processed = FALSE)

**배포 가능 상태**: Phase 1-3는 WebSocket 없이도 작동 가능 (스케줄러 기반 재정렬)

### 다음 작업

**옵션 1: Phase 4-5 계속 진행** (추가 2주 예상)
- [ ] Phase 4: WebSocket 실시간 체결 감지
- [ ] Phase 5: 안정화 및 최적화

**옵션 2: Phase 1-3 배포 및 운영 검증**
- 스케줄러 기반 재정렬로 충분한 경우 Phase 4-5 연기 가능
- WebSocket은 선택적 최적화 (1초 주기 → 실시간)

---

## 6. 테스트 시나리오

### 시나리오 1: 기본 대기열 동작

**초기 상태**:
- Binance FUTURES BTC/USDT
- 제한: 20개
- 거래소 실행: 20개 (100% 사용)

**웹훅 수신**:
```json
{
  "order_type": "LIMIT",
  "side": "buy",
  "price": "110000",
  "qty_per": 10
}
```

**예상 결과**:
1. PendingOrder 테이블에 추가
2. 스케줄러 실행 (1초 후)
3. 재정렬: 110000이 최우선
4. 거래소 최하위 주문 취소
5. 110000 주문 거래소 실행

---

### 시나리오 2: STOP 이중 제한

**초기 상태**:
- 일반 주문: 15개
- STOP 주문: 5개 (제한 도달)

**웹훅 수신**:
```json
{
  "order_type": "STOP_LIMIT",
  "side": "buy",
  "price": "94000",
  "stop_price": "90000"
}
```

**예상 결과**:
1. PendingOrder 추가
2. 재정렬 시 STOP 제한 체크
3. 기존 STOP 주문 중 최하위 취소
4. 신규 STOP 주문 실행

---

### 시나리오 3: WebSocket 체결 감지

**초기 상태**:
- 거래소 실행: 20개
- 대기열: 5개

**WebSocket 이벤트**:
```json
{
  "e": "ORDER_TRADE_UPDATE",
  "o": {
    "s": "BTCUSDT",
    "i": 8886774,
    "X": "FILLED"
  }
}
```

**예상 결과**:
1. REST API로 주문 확인
2. OpenOrder 삭제
3. 즉시 재정렬 트리거
4. 대기열 1위 주문 거래소 실행

---

### 시나리오 4: CANCEL_ALL_ORDER

**초기 상태**:
- 거래소 실행: 10개
- 대기열: 5개

**웹훅 수신**:
```json
{
  "order_type": "CANCEL_ALL_ORDER",
  "symbol": "BTC/USDT"
}
```

**예상 결과**:
1. 거래소 10개 주문 취소 (REST API)
2. 대기열 5개 주문 삭제 (DB)
3. 전략별 격리 유지

---

### 시나리오 5: 다중 심볼 동시 재정렬

**초기 상태**:
- BTC/USDT: 거래소 20 + 대기열 10
- ETH/USDT: 거래소 15 + 대기열 5
- SOL/USDT: 거래소 10 + 대기열 0

**스케줄러 실행**:
- 각 심볼별 독립적 재정렬
- 상호 간섭 없음
- 병렬 처리 가능

---

## 7. 성공 지표

### 기능적 지표

- [ ] 열린 주문 제한 초과 오류 0건
- [ ] 대기열 → 거래소 전환 성공률 > 99%
- [ ] STOP 주문 이중 제한 위반 0건
- [ ] WebSocket 재연결 성공률 > 99%

### 성능 지표

- [ ] 재정렬 평균 소요 시간 < 500ms
- [ ] 체결 감지 → 재정렬 지연 < 1초
- [ ] 스케줄러 CPU 사용률 < 10%
- [ ] DB 쿼리 평균 응답 시간 < 100ms

### 사용자 경험

- [ ] 대기열 현황 실시간 표시
- [ ] 예상 대기 시간 안내
- [ ] 우선순위 변경 시 알림

---

## 8. 리스크 및 대응 방안

### 리스크 1: WebSocket 연결 불안정

**대응**:
- Exponential backoff 재연결
- REST API 폴백 (스케줄러 주기 유지)
- Telegram 연결 실패 알림

### 리스크 2: 재정렬 성능 저하

**대응**:
- 인덱스 최적화
- 심볼별 병렬 처리
- 대기열 크기 제한 (심볼당 최대 100개)

### 리스크 3: 거래소 API rate limit

**대응**:
- 재정렬 빈도 조절 (1초 → 3초)
- 배치 주문 취소 API 활용
- 우선순위 높은 심볼만 재정렬

---

## 9. 참고 자료

### 거래소 API 문서

- [Binance Futures API - Rate Limits](https://binance-docs.github.io/apidocs/futures/en/#limits)
- [Binance User Data Stream](https://binance-docs.github.io/apidocs/futures/en/#user-data-streams)
- [Bybit API v5 - Order Limits](https://bybit-exchange.github.io/docs/v5/order/create-order)
- [OKX API - Pending Order Limits](https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-place-order)

### 프로젝트 문서

- [웹훅 메시지 포맷](./webhook_message_format.md)
- [개발 가이드라인](../CLAUDE.md)
- [Trading Service 구조](../web_server/app/services/trading/)

---

**작성자**: Claude Code
**최종 수정**: 2025-10-08
**버전**: 1.0.0
