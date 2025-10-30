# 주문 상태 추적 (Order Tracking)

## 1. 개요 (Purpose)

주문 생성 후 거래소에서 발생하는 상태 변화를 실시간으로 추적하고 DB에 동기화하여 정확한 포지션 관리와 실시간 모니터링을 제공합니다.

**핵심 가치**:
- WebSocket 기반 실시간 추적 (레이턴시 < 1초)
- REST API 폴백으로 100% 정확성 보장 (10초 주기 동기화)
- 체결 즉시 포지션 업데이트 및 SSE를 통한 프론트엔드 실시간 반영

---

## 2. 실행 플로우 (Execution Flow)

```
[웹훅 또는 수동 주문]
    ↓
[1] OrderManager.execute()
    ├─ 거래소 주문 전송
    ├─ OpenOrder DB 저장
    └─ WebSocket 구독 시작 (심볼별 참조 카운트)
    ↓
[2] WebSocket 이벤트 수신 (ORDER_TRADE_UPDATE)
    ↓
[3] OrderFillMonitor.on_order_update()
    ├─ 심볼 포맷 정규화 (Binance/Bybit)
    ├─ REST API 검증 (신뢰도 확보)
    ├─ OpenOrder 업데이트/삭제
    └─ process_order_fill() (FILLED 시)
    ↓
[4] 체결 처리 (event_emitter를 통해)
    ├─ Trade 기록 생성
    ├─ StrategyPosition 업데이트
    ├─ TradeExecution 상세 저장
    └─ PendingOrder SSE 발송 (프론트엔드 실시간 업데이트)
    ↓
[5] 폴백 동기화 (10초 주기)
    └─ WebSocket 끊김 시 REST API로 전체 동기화
```

**핵심 특징**:
- 즉시 실행 (immediate-order-execution) Phase 적용 후 웹훅 → WebSocket 직접 연동
- LIMIT/MARKET 주문 통합 처리
- PendingOrder SSE로 실시간 체결 상태 전달

---

## 3. 데이터 플로우 (Data Flow)

**Input**:
- 거래소 주문 생성 결과 (`exchange_order_id`, `symbol`, `side`, `status`)

**Process**:
1. **추적 시작**: `OpenOrder` 테이블에 INSERT (status='NEW')
2. **상태 업데이트**: WebSocket/REST API → `filled_quantity`, `status` 갱신
3. **완료 감지**: FILLED/CANCELLED → `OpenOrder` 삭제, `Trade` 생성

**Output**:
- 정확한 포지션 데이터 (`StrategyPosition`)
- 체결 히스토리 (`Trade`, `TradeExecution`)
- SSE 이벤트 (프론트엔드 실시간 업데이트)

**의존성**:
- `@DEPS:exchange-integration` - 거래소 API 호출
- `@DEPS:position-tracking` - 포지션 업데이트
- `@DEPS:websocket-manager` - 실시간 연결 관리
- `@DEPS:event-sse` - PendingOrder SSE 발송

---

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `order_tracking.py` | 추적 세션 관리 및 폴백 동기화 | `@FEAT:order-tracking @COMP:service @TYPE:core` | `create_session()`, `sync_open_orders()` |
| `order_fill_monitor.py` | WebSocket 이벤트 처리 및 DB 동기화 | `@FEAT:order-tracking @COMP:service @TYPE:integration` | `on_order_update()` |
| `event_emitter.py` | 체결 이벤트 처리 (Trade, SSE, FailedOrder) | `@FEAT:order-tracking @COMP:service @TYPE:integration` | `emit_trade_event()`, `emit_pending_order_sse()` |
| `websocket_manager.py` | 심볼별 구독 관리 (참조 카운트) | `@FEAT:order-tracking @COMP:service @TYPE:core` | `subscribe_symbol()`, `unsubscribe_symbol()` |
| `binance_websocket.py` | Binance User Data Stream | `@FEAT:order-tracking @COMP:exchange @TYPE:integration` | `on_message()` |
| `bybit_websocket.py` | Bybit User Data Stream | `@FEAT:order-tracking @COMP:exchange @TYPE:integration` | `on_message()` |

### 핵심 로직 위치

```bash
# 모든 order-tracking 코드
grep -r "@FEAT:order-tracking" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:order-tracking" --include="*.py" | grep "@TYPE:core"

# WebSocket 통합 코드
grep -r "@FEAT:order-tracking" --include="*.py" | grep "@TYPE:integration"
```

---

## 5. 데이터 모델 (Data Models)

### OpenOrder (미체결 주문 추적)
```python
# @FEAT:order-tracking @COMP:model @TYPE:core
class OpenOrder(db.Model):
    exchange_order_id  # 🔑 거래소 주문 ID (unique key)
    symbol             # 심볼
    status             # NEW, PARTIALLY_FILLED, FILLED, CANCELLED
    filled_quantity    # 체결된 수량
    market_type        # SPOT, FUTURES
```

**생명주기**:
- 생성: 주문 전송 시 INSERT
- 업데이트: 부분 체결 시 `filled_quantity` 증가
- 삭제: 완전 체결/취소 시 DELETE (더 이상 추적 불필요)

### OrderTrackingSession (세션 관리)
```python
# @FEAT:order-tracking @COMP:model @TYPE:core
class OrderTrackingSession(db.Model):
    session_id         # WebSocket 세션 ID
    status             # connecting, connected, disconnected, error
    last_ping          # Keep-alive (5분 타임아웃)
```

### TradeExecution (체결 상세)
```python
# @FEAT:order-tracking @COMP:model @TYPE:core
class TradeExecution(db.Model):
    exchange_trade_id  # 거래소 거래 ID
    execution_price    # 실제 체결가
    execution_quantity # 체결 수량
    is_maker           # Maker/Taker 여부
    realized_pnl       # 실현 손익 (선물)
```

**Trade vs TradeExecution**:
- `Trade`: 주문 단위 집계 (1 주문 → 1 Trade)
- `TradeExecution`: 체결 단위 상세 (1 주문 → N TradeExecution)

---

## 6. 실시간 추적 메커니즘

### Primary: WebSocket 기반 추적 (< 1초 레이턴시)

**흐름**:
```
거래소 WebSocket (User Data Stream)
    ↓
BinanceWebSocket/BybitWebSocket.on_message()
    ↓ ORDER_TRADE_UPDATE 이벤트
OrderFillMonitor.on_order_update()
    ├─ [1] 심볼 포맷 정규화 (BTCUSDT → BTC/USDT)
    ├─ [2] REST API 검증 (5초 타임아웃, 신뢰도 확보)
    ├─ [3] OpenOrder 업데이트 (filled_quantity)
    │      또는 삭제 (FILLED/CANCELLED)
    └─ [4] event_emitter.emit_trade_event() (체결 시)
        ├─ Trade 생성
        ├─ StrategyPosition 업데이트
        ├─ TradeExecution 저장
        └─ PendingOrder SSE 발송 (프론트엔드)
```

**특징**:
- LIMIT 주문: WebSocket으로 부분/완전 체결 추적
- MARKET 주문: 1회 WebSocket 이벤트로 즉시 완전 체결 처리
- 심볼별 참조 카운트로 중복 구독 방지

### Fallback: REST API 동기화 (10초 주기, WebSocket 끊김 시)

**용도**: WebSocket 연결 실패 시 자동 복구
**방식**: 폴링 기반 (10초마다 open_orders API 호출)
**정확도**: 100% (거래소가 source of truth)

**처리 로직**:
```
거래소 open_orders API 조회
    ↓
DB OpenOrder 전체 조회
    ↓
차이점 식별:
  1) 거래소 O, DB X → INSERT (새로운 주문)
  2) 거래소 X, DB O → FILLED/CANCELLED 판단 후 DELETE
  3) filled_quantity 불일치 → UPDATE + emit_trade_event()
```

**레이턴시**: 최대 10초 지연 (WebSocket 끊김 감지 후)

### WebSocket 참조 카운트 관리

```python
# @FEAT:order-tracking @COMP:service @TYPE:core
# 심볼별 구독 관리 (여러 주문이 동일 심볼 사용)
subscribe_symbol(account_id=1, symbol="BTC/USDT")    # count: 0 → 1 (WebSocket 구독 추가)
subscribe_symbol(account_id=1, symbol="BTC/USDT")    # count: 1 → 2 (재사용)
unsubscribe_symbol(account_id=1, symbol="BTC/USDT")  # count: 2 → 1 (유지)
unsubscribe_symbol(account_id=1, symbol="BTC/USDT")  # count: 1 → 0 (구독 해제)
```

---

## 7. 설계 결정 히스토리 (Design Decisions)

### WHY: 이중 검증 (WebSocket + REST API)
**문제**: WebSocket 이벤트는 빠르지만 신뢰도가 100%가 아님 (네트워크 순단, 메시지 손실)
**결정**: WebSocket 이벤트 수신 후 항상 REST API로 재확인 (5초 타임아웃)
**결과**: 속도 + 정확성 모두 확보

### WHY: OpenOrder 삭제 전략
**문제**: FILLED 주문을 DB에 계속 저장하면 쿼리 성능 저하
**결정**: 체결 완료 시 `OpenOrder` 삭제, `Trade`/`TradeExecution`에만 보관
**결과**: 미체결 주문 쿼리 속도 향상, 히스토리는 별도 테이블로 보존

### WHY: Token/Listen Key 갱신 (30분 주기)
**요구사항**: 거래소별 타임아웃 정책
- Binance: 60분 자동 만료
- Bybit: 30분 자동 만료
**결정**: 30분마다 토큰/Listen Key 갱신 (50% 안전 마진)
**결과**: 예상치 못한 연결 끊김 방지

---

## 8. 동기화 시나리오

### 시나리오 1: WebSocket 정상 동작 (LIMIT 주문)
```
T+0.0s: 웹훅/수동 주문 → OrderManager.execute()
T+0.1s: OpenOrder INSERT (filled=0.0) + WebSocket 구독
T+0.5s: WebSocket 이벤트 → PARTIALLY_FILLED (filled=0.3)
T+0.6s: OrderFillMonitor → OpenOrder UPDATE (filled=0.3)
T+2.5s: WebSocket 이벤트 → FILLED (filled=1.0)
T+2.6s: OrderFillMonitor → event_emitter.emit_trade_event()
        ├─ OpenOrder DELETE
        ├─ Trade INSERT + TradeExecution INSERT
        ├─ StrategyPosition UPDATE
        └─ PendingOrder SSE 발송 → 프론트엔드 ✅
```

### 시나리오 2: MARKET 주문 (즉시 완전 체결)
```
T+0.0s: 웹훅 → OrderManager.execute() (MARKET)
T+0.1s: 거래소 즉시 FILLED 응답
T+0.1s: OpenOrder INSERT + WebSocket 이벤트 즉시 수신
T+0.2s: OrderFillMonitor → event_emitter.emit_trade_event()
T+0.3s: PendingOrder SSE 발송 ✅
```

### 시나리오 3: WebSocket 끊김 (REST API 폴백)
```
T+0.0s: 주문 생성 → OpenOrder INSERT
T+1.0s: [WebSocket 연결 끊김]
T+10s:  sync_open_orders() 실행 (10초 주기)
        → REST API로 FILLED 감지
        → event_emitter.emit_trade_event()
T+10.1s: PendingOrder SSE 발송 (10초 지연) ✅
```

---

## 9. 유지보수 가이드

### 주의사항

1. **WebSocket 연결 상태 모니터링 필수**
   - Listen Key 갱신 실패 시 즉시 재연결
   - 로그: `grep "Listen Key" logs/app.log`

2. **DB 트랜잭션 원자성 보장**
   - OpenOrder 삭제 + Trade 생성은 단일 트랜잭션
   - 실패 시 롤백으로 데이터 일관성 유지

3. **SSE 클라이언트 큐 오버플로 방지**
   - maxsize=50, 초과 시 이벤트 드롭
   - 프론트엔드는 주기적으로 전체 데이터 새로고침 필요

### 확장 포인트

1. **다중 거래소 지원**
   - `BybitWebSocket`, `UpbitWebSocket` 추가 (동일 인터페이스)
   - `OrderFillMonitor.on_order_update()`는 거래소 독립적

2. **추가 이벤트 타입**
   - `order_rejected`, `order_expired` 등 SSE 이벤트 추가
   - `event_service.py`에 이벤트 타입만 추가

3. **고급 동기화 전략**
   - 심볼별 우선순위 동기화 (활발한 심볼 먼저)
   - 변경 감지 시만 동기화 (불필요한 API 호출 절감)

---

## 10. 트러블슈팅

### 문제 1: 주문 상태 업데이트 안 됨

**증상**: 거래소에서 체결되었지만 프론트엔드에 미체결 표시
**원인**: WebSocket 끊김, OrderFillMonitor 미실행
**해결**:
```bash
# 1. WebSocket 상태 확인 (관리자 페이지에서 확인 가능)
# /admin/api/metrics 엔드포인트에 websocket_stats 포함

# 2. 수동 동기화 (관리자 전용)
curl -X POST http://localhost:5001/admin/system/order-tracking/sync-orders \
  -H "Content-Type: application/json" \
  -d '{"account_id": 1}'

# 3. 로그 확인
tail -f logs/app.log | grep "OrderFillMonitor\|WebSocket"
```

### 문제 2: Listen Key 만료 (401 Unauthorized)

**증상**: `❌ Listen Key 갱신 실패: 401`
**원인**: API 키 권한 부족, 60분 미갱신
**해결**:
- API 키에 `User Data Stream` 권한 추가
- 로그에서 "Listen Key 갱신 성공" 30분마다 확인

### 문제 3: 체결 후 포지션 업데이트 누락

**증상**: Trade 기록 있지만 StrategyPosition 수량 불일치
**원인**: `process_order_fill()` 호출 실패, DB 트랜잭션 롤백
**해결**:
```bash
grep "체결 처리" logs/app.log | grep -i "failed\|error"
```
- 실패 시 텔레그램 알림 확인
- `trading_service.process_order_fill()` 호출 전후 로그 추가

### 문제 4: SSE 이벤트 미수신

**증상**: 로그에 "이벤트 발송" 있지만 프론트엔드 UI 업데이트 안 됨
**원인**: SSE 연결 끊김, 클라이언트 큐 full
**해결**:
```javascript
// 프론트엔드: SSE 재연결 로직 추가
const eventSource = new EventSource('/api/sse/events');
eventSource.onerror = () => {
    setTimeout(() => location.reload(), 3000);  // 3초 후 재연결
};
```

---

## 11. 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [웹훅 주문 처리](./webhook-order-processing.md)
- [주문 큐 시스템](./order-queue-system.md)
- [거래소 통합](./exchange-integration.md)

---

## 12. 핵심 구현 파일

**grep 검색**:
```bash
# 전체 기능
grep -r "@FEAT:order-tracking" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:order-tracking" --include="*.py" | grep "@TYPE:core"

# 통합 로직 (WebSocket, 이벤트)
grep -r "@FEAT:order-tracking" --include="*.py" | grep "@TYPE:integration"
```

**주요 파일**:
- `web_server/app/services/order_tracking.py` - 폴백 동기화
- `web_server/app/services/order_fill_monitor.py` - WebSocket 이벤트 처리
- `web_server/app/services/trading/event_emitter.py` - 체결 이벤트 발송
- `web_server/app/services/websocket_manager.py` - 심볼 구독 관리
- `web_server/app/services/exchanges/binance_websocket.py` - Binance 연동
- `web_server/app/services/exchanges/bybit_websocket.py` - Bybit 연동

---

*Last Updated: 2025-10-30*
*Version: 2.1.0 (Phase 4-7 완전 동기화)*
