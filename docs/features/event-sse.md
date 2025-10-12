# 실시간 이벤트 스트리밍 (SSE - Server-Sent Events)

## 1. 개요 (Purpose)

Server-Sent Events(SSE)를 사용하여 백엔드 트레이딩 이벤트(주문 생성/체결/취소, 포지션 업데이트)를 웹 대시보드로 실시간 전송하는 단방향 스트리밍 시스템입니다.

**핵심 특징**:
- 단방향 통신 (서버 → 클라이언트): 트레이딩 알림에 최적화
- HTTP 기반: 기존 인프라 활용, 브라우저 자동 재연결 지원
- 사용자별 격리: user_id 기반 이벤트 큐 분리 (보안)
- 메모리 효율: deque(maxlen=100)로 과거 이벤트 자동 제거

**SSE 선택 이유**: 트레이딩 시스템에서는 서버→클라이언트 알림만 필요하므로 WebSocket의 양방향 통신은 불필요한 복잡도. SSE의 자동 재연결과 HTTP/2 멀티플렉싱이 더 적합.

---

## 2. 실행 플로우 (Execution Flow)

```
[클라이언트 연결]
브라우저 → GET /api/events/stream → positions.py:event_stream()
                                            ↓
                    event_service.get_event_stream(user_id)
                                            ↓
                    - 사용자별 Queue 생성 (maxsize=50)
                    - clients[user_id]에 Queue 등록
                    - SSE Response 반환

[이벤트 발생]
주문 생성: webhook_service → trading/core.py → event_emitter.emit_trading_event()
                                                        ↓
                                        event_service.emit_order_event(OrderEvent)
                                                        ↓
                                        event_queues[user_id].append(event_data)
                                                        ↓
                                        client_queue.put(event_data, timeout=1.0)

포지션 업데이트: position_manager → event_emitter.emit_position_event()
                                                ↓
                                event_service.emit_position_event(PositionEvent)

[클라이언트 수신]
event_generator() 무한 루프:
    ├─ client_queue.get(timeout=10) → 이벤트 수신 → SSE 포맷 변환 → 브라우저 전송
    └─ Queue.Empty (10초 타임아웃) → Heartbeat 전송 ("event: heartbeat\ndata: {...}\n\n")

[연결 종료]
GeneratorExit 예외 → event_service.remove_client(user_id, client_queue)
```

---

## 3. 데이터 플로우 (Data Flow)

**Input**: 거래 이벤트 (OrderEvent, PositionEvent)
**Process**:
1. user_id 기반 이벤트 필터링
2. 사용자별 Queue에 이벤트 추가
3. SSE 포맷 변환 ("event: order_update\ndata: {...}\n\n")
**Output**: 브라우저 EventSource로 실시간 전송

**주요 의존성**:
- `event_service.py` (Level 1): SSE 연결 관리 및 이벤트 발송
- `event_emitter.py` (Level 2): 거래 로직에서 이벤트 발행 추상화
- 거래 서비스 (Level 3): trading/core.py, position_manager.py 등

---

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `event_service.py` | SSE 연결 관리 및 이벤트 발송 | `@FEAT:event-sse @COMP:service @TYPE:core` | `get_event_stream()`, `emit_order_event()`, `emit_position_event()`, `add_client()`, `remove_client()` |
| `event_emitter.py` | 거래 로직 이벤트 발행 헬퍼 | `@FEAT:event-sse @COMP:service @TYPE:helper` | `emit_trading_event()`, `emit_order_events_smart()`, `emit_position_event()`, `emit_order_cancelled_event()`, `emit_pending_order_event()` |
| `positions.py` | SSE 엔드포인트 | `@FEAT:event-sse @COMP:route @TYPE:core` | `event_stream()`, `check_auth()`, `event_stats()` |

### EventService 핵심 구조
```python
# @FEAT:event-sse @COMP:service @TYPE:core
class EventService:
    def __init__(self):
        self.clients = defaultdict(set)              # user_id → set of Queue
        self.event_queues = defaultdict(lambda: deque(maxlen=100))  # 최근 100개
        self.lock = threading.RLock()                # 스레드 안전성
```

### 스마트 이벤트 발행 (emit_order_events_smart)
주문 상태에 따라 적절한 이벤트 자동 선택:
- MARKET 주문 → `ORDER_FILLED` 이벤트만
- NEW/OPEN → `ORDER_CREATED`
- PARTIALLY_FILLED → `ORDER_CREATED` (신규) 또는 `ORDER_UPDATED` (기존) + `ORDER_FILLED`
- FILLED → `ORDER_FILLED` (차액만)
- CANCELLED → `ORDER_CANCELLED`

### 이벤트 타입 상수 (OrderEventType)
`app/constants.py`에 정의된 표준 이벤트 타입:
- `ORDER_CREATED = 'order_created'` - 새 주문 생성
- `ORDER_UPDATED = 'order_updated'` - 주문 정보 업데이트 (부분 체결 등)
- `ORDER_FILLED = 'order_filled'` - 주문 체결
- `ORDER_CANCELLED = 'order_cancelled'` - 주문 취소
- `TRADE_EXECUTED = 'trade_executed'` - 거래 실행 (레거시, MARKET 주문 시 사용)
- `POSITION_UPDATED = 'position_updated'` - 포지션 업데이트

---

## 5. 이벤트 타입 (Event Types)

### OrderEvent (주문 이벤트)
**이벤트 타입**: `order_created`, `order_filled`, `order_cancelled`, `order_updated`, `trade_executed`

**필드**: `event_type`, `order_id`, `symbol`, `strategy_id`, `user_id`, `side`, `quantity`, `price`, `status`, `timestamp`, `order_type`, `stop_price`, `account`

**계좌 정보 (account 필드 - 중첩 구조)**:
```python
account = {
    'account_id': int,  # 계좌 ID
    'name': str,        # 계좌명
    'exchange': str     # 거래소명 (BINANCE, BYBIT 등)
}
```

**SSE 메시지 예시**:
```
event: order_update
data: {"event_type":"order_created","order_id":"12345","symbol":"BTC/USDT","strategy_id":1,"user_id":10,"side":"BUY","quantity":0.001,"price":95000.0,"status":"NEW",...}

```

### PositionEvent (포지션 이벤트)
**이벤트 타입**: `position_created`, `position_updated`, `position_closed`

**필드**: `event_type`, `position_id`, `symbol`, `strategy_id`, `user_id`, `quantity`, `entry_price`, `timestamp`, `previous_quantity`, `account`, `account_name`, `exchange`

**계좌 정보 (account 필드 - 중첩 구조)**:
```python
account = {
    'account_id': int,  # 계좌 ID (✅ 표준화 완료: 모든 이벤트 타입에서 통일)
    'name': str,        # 계좌명
    'exchange': str     # 거래소명
}
```

**✅ 2025-10-12 표준화 완료:** 이전에는 PositionEvent가 `account.id`를 사용했으나, 이제 모든 이벤트 타입(OrderEvent, PositionEvent, PendingOrderEvent)이 `account.account_id`로 통일되었습니다.

**SSE 메시지 예시**:
```
event: position_update
data: {"event_type":"position_updated","position_id":42,"symbol":"BTC/USDT","quantity":0.005,"entry_price":96000.0,...}

```

### 시스템 이벤트
- **Connection**: 연결 확인 (`event: connection`)
- **Heartbeat**: 10초마다 전송, 연결 유지 (`event: heartbeat`)

### PendingOrder 이벤트 (대기열 주문)
대기열에 추가/제거되는 주문에 대한 이벤트 (`emit_pending_order_event` 사용):
- **이벤트 타입**: `order_created` (대기열 추가), `order_cancelled` (대기열 제거)
- **order_id 형식**: `p_{pending_order.id}` (prefix `p_` 추가로 OpenOrder와 구분)
- **status**: `PENDING_QUEUE` (대기열 상태 표시)
- **특징**: 거래소에 제출 전 대기 중인 주문, PendingOrder 테이블 기반

---

## 6. 사용자별 격리 (User Isolation)

**격리 메커니즘**:
```python
# event_service.py
def _emit_to_user(self, user_id: int, event_data: Dict[str, Any]):
    with self.lock:
        # 1. 사용자별 이벤트 큐에 추가
        self.event_queues[user_id].append(event_data)

        # 2. 해당 사용자의 연결된 클라이언트들에게만 전송
        for client in self.clients.get(user_id, set()):
            try:
                client.put(event_data, timeout=1.0)
            except:
                dead_clients.add(client)
```

**보안 검증**:
- `@login_required` 데코레이터로 인증된 사용자만 접근
- `current_user.id` 기반으로 이벤트 필터링
- 사용자 A의 이벤트는 사용자 B에게 절대 전송되지 않음

**다중 탭 지원**: 한 사용자가 여러 탭을 열어도 모두 이벤트 수신 (clients[user_id]는 set이므로 여러 Queue 동시 관리)

---

## 7. 성능 최적화 (Performance)

### 메모리 관리
- `deque(maxlen=100)`: 사용자별 최근 100개 이벤트만 유지 (메모리 누수 방지)
- 타임아웃 설정: `client.put(event_data, timeout=1.0)`, `client_queue.get(timeout=10)`

### 주기적 정리 (_periodic_cleanup)
60초마다 실행:
- 빈 클라이언트 집합 제거 (`clients[user_id]`)
- 연결 없는 사용자의 이벤트 큐 제거 (`event_queues[user_id]`)

### 죽은 클라이언트 즉시 제거
전송 실패 시 `dead_clients` 집합에 추가 후 일괄 제거

### Nginx 버퍼링 비활성화
```python
response = Response(
    event_generator(),
    mimetype='text/event-stream',
    headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache', ...}
)
```

---

## 8. 설계 결정 히스토리 (Design Decisions)

### 결정 1: SSE vs WebSocket
**선택**: SSE (Server-Sent Events)
**이유**:
- 트레이딩 시스템에서는 서버→클라이언트 방향 알림만 필요
- 클라이언트→서버 요청은 기존 REST API로 충분
- WebSocket의 양방향 통신은 불필요한 복잡도 추가
- SSE의 브라우저 자동 재연결 기능이 연결 안정성 향상

### 결정 2: 과거 이벤트 재전송하지 않음
**선택**: 신규 연결 시 과거 이벤트 재전송 안 함 (실시간만)
**이유**:
- `event_queues`에는 최근 100개 저장되지만, 현재는 실시간 이벤트만 전송
- 과거 이벤트 필요 시 REST API (`/api/orders`, `/api/positions`)로 조회
- SSE는 실시간 업데이트 전용, 초기 데이터 로딩은 REST API 역할 분리

### 결정 3: Heartbeat 10초 간격
**선택**: 10초마다 Heartbeat 전송
**이유**:
- Nginx `proxy_read_timeout` 방지
- 연결 유지 및 죽은 연결 조기 감지
- 너무 짧으면 네트워크 부하, 너무 길면 타임아웃 위험

---

## 9. 코드 예시 (Code Examples)

### 클라이언트 연결 (JavaScript)
```javascript
const eventSource = new EventSource('/api/events/stream');

// 주문 이벤트 수신
eventSource.addEventListener('order_update', (event) => {
    const orderData = JSON.parse(event.data);
    if (orderData.event_type === 'order_created') {
        addOrderToTable(orderData);
    } else if (orderData.event_type === 'order_filled') {
        updateOrderStatus(orderData.order_id, 'FILLED');
    }
});

// 포지션 이벤트 수신
eventSource.addEventListener('position_update', (event) => {
    const positionData = JSON.parse(event.data);
    updatePosition(positionData.position_id, positionData);
});

// 에러 처리
eventSource.onerror = (error) => {
    console.error('SSE 에러:', error);
    // 브라우저가 자동으로 재연결 시도
};
```

### 백엔드 이벤트 발송 (Python)
```python
from app.services.event_service import event_service, OrderEvent, PositionEvent
from datetime import datetime

# OrderEvent 발송 예시 (account 필드에 account_id 사용)
order_event = OrderEvent(
    event_type='order_created',
    order_id='12345',
    symbol='BTC/USDT',
    strategy_id=strategy.id,
    user_id=strategy.user_id,
    side='BUY',
    quantity=0.001,
    price=95000.0,
    status='NEW',
    timestamp=datetime.utcnow().isoformat(),
    order_type='LIMIT',
    stop_price=None,
    account={'account_id': account.id, 'name': account.name, 'exchange': account.exchange}
)
event_service.emit_order_event(order_event)

# PositionEvent 발송 예시 (✅ 표준화: account_id 사용)
position_event = PositionEvent(
    event_type='position_updated',
    position_id=42,
    symbol='BTC/USDT',
    strategy_id=strategy.id,
    user_id=strategy.user_id,
    quantity=0.005,
    entry_price=96000.0,
    timestamp=datetime.utcnow().isoformat(),
    previous_quantity=0.003,
    account={'account_id': account.id, 'name': account.name, 'exchange': account.exchange},
    account_name=account.name,
    exchange=account.exchange
)
event_service.emit_position_event(position_event)
```

---

## 10. 트러블슈팅 (Troubleshooting)

| 문제 | 원인 | 해결 방법 |
|------|------|-----------|
| 이벤트 수신 안 됨 | 사용자 ID 불일치 | 로그 확인: `current_user.id`와 이벤트 `user_id` 일치 여부 |
| | 이벤트 미발행 | `event_service.emit_order_event()` 호출 여부 확인 |
| 연결 자주 끊김 | Nginx 타임아웃 | `proxy_read_timeout 300s` 설정 |
| | Heartbeat 미전송 | `event_generator()` timeout=10 확인 |
| 메모리 증가 | 죽은 클라이언트 미정리 | `get_statistics()` 호출 후 `total_connections` 확인 |
| | 이벤트 큐 무제한 | `deque(maxlen=100)` 설정 확인 |
| 이벤트 중복 수신 | 여러 탭 연결 (정상) | 클라이언트에서 중복 제거 로직 구현 |
| 관리자 통계 조회 실패 | 권한 부족 | `current_user.is_admin == True` 확인 |

---

## 11. 유지보수 가이드 (Maintenance Guide)

### 주의사항
- `event_service.emit_*()` 호출 시 반드시 `user_id` 전달 필요 (격리 보장)
- `OrderEvent`/`PositionEvent` 데이터클래스 필드 수정 시 클라이언트 코드도 업데이트
- Nginx 타임아웃 설정 (`proxy_read_timeout`, `proxy_send_timeout`)은 Heartbeat 간격(10초)보다 길어야 함

### 확장 포인트
- 과거 이벤트 재전송 기능: `get_event_stream()`에서 `event_queues[user_id]` 전송 로직 추가
- 새로운 이벤트 타입 추가: `EventEmitter`에 `emit_*()` 메서드 추가 후 `event_service.py`에 발송 로직 추가
- 관리자 대시보드: `/api/events/stats` 엔드포인트 활용하여 실시간 연결 모니터링

### 테스트 방법
```bash
# SSE 연결 테스트 (로그인 필요)
curl -N -H "Accept: text/event-stream" \
  -H "Cookie: session=<your_session_cookie>" \
  https://222.98.151.163/api/events/stream

# 주문 생성 후 이벤트 수신 확인
curl -k -X POST https://222.98.151.163/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"group_name":"test1","symbol":"BTC/USDT","order_type":"LIMIT","side":"buy","price":"90000","qty_per":5,"token":"..."}'
```

---

## 12. 관련 파일 (Related Files)

**핵심 파일**:
- `web_server/app/services/event_service.py` - SSE 이벤트 서비스 (Level 1)
- `web_server/app/services/trading/event_emitter.py` - 이벤트 발행 헬퍼 (Level 2)
- `web_server/app/routes/positions.py` - SSE 엔드포인트 (Level 3)

**이벤트 발송 위치**:
- `web_server/app/services/webhook_service.py` - 증권 주문 이벤트
- `web_server/app/services/trading/core.py` - 거래 실행 시 이벤트
- `web_server/app/services/trading/order_manager.py` - 주문 취소 이벤트
- `web_server/app/services/trading/position_manager.py` - 포지션 업데이트 이벤트
- `web_server/app/services/trading/order_queue_manager.py` - 대기열 주문 이벤트

**grep 검색**:
```bash
# SSE 관련 모든 코드 찾기
grep -r "@FEAT:event-sse" --include="*.py"

# 핵심 로직만 찾기
grep -r "@FEAT:event-sse" --include="*.py" | grep "@TYPE:core"

# 이벤트 발행 위치 찾기
grep -r "emit_order_event\|emit_position_event" --include="*.py"
```

---

*Last Updated: 2025-10-12*
*Version: 2.2.0 (필드 표준화 완료)*
*Maintainer: documentation-manager*
*Changes:*
- *✅ 표준화 완료: 모든 이벤트 타입이 `account.account_id` 사용 (코드 수정 완료)*
- *추가: `trade_executed` 이벤트 타입 (누락 정보 보완)*
- *추가: `emit_pending_order_event()` 메서드 문서화 (대기열 주문 이벤트)*
- *수정: OrderEvent/PositionEvent `account` 필드 중첩 구조 명확화*
- *추가: OrderEventType 상수 목록 (constants.py 기반)*
- *개선: 코드 예시에 PositionEvent 발송 샘플 추가*
