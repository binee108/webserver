# Cancel Queue 시스템 문서

Phase 2에서 구현된 Cancel Queue 시스템의 상세 문서입니다.

---

## 개요

**목적**: PENDING 상태 주문의 취소 요청을 안전하게 처리하여 고아 주문 완전 차단

**문제**:
- TradingView 웹훅으로 MARKET 주문 요청 → DB에 PENDING 저장
- 거래소 API 호출 전, 사용자가 "취소" 버튼 클릭
- 취소 요청이 들어왔지만 아직 exchange_order_id가 NULL (OPEN 전)
- 즉시 취소 불가 → **고아 주문 발생**

**해결**:
- PENDING 주문 취소 요청을 Cancel Queue에 등록
- 백그라운드 작업이 주기적으로 Queue 확인
- PENDING → OPEN 전환 완료 시 실제 거래소 취소 실행
- 실패 시 재시도 (exponential backoff)

---

## 아키텍처

### 컴포넌트

```
┌─────────────────┐
│  User Request   │ POST /cancel-queue/orders/{id}/cancel
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│  CancelQueueService         │
│  - add_to_queue()           │
│  - verify_order_status()    │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  CancelQueue (DB Model)     │
│  - status: PENDING          │
│  - retry_count: 0           │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Background Task            │ (매 10초)
│  - get_pending_cancels()    │
│  - process_cancel()         │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Exchange API               │
│  - cancel_order()           │
└─────────────────────────────┘
```

---

## 사용 방법

### 1. 주문 취소 요청

```bash
curl -X POST http://localhost:8000/api/v1/cancel-queue/orders/123/cancel
```

**응답 (PENDING 주문)**:
```json
{
  "message": "Cancel request added to queue",
  "order_id": 123,
  "status": "queued",
  "cancel_queue_id": 45,
  "immediate": false
}
```

**응답 (OPEN 주문)**:
```json
{
  "message": "Order cancelled immediately",
  "order_id": 123,
  "status": "cancelled",
  "cancel_queue_id": null,
  "immediate": true
}
```

### 2. Cancel Queue 조회

```bash
# 모든 항목 조회
curl http://localhost:8000/api/v1/cancel-queue

# PENDING 항목만 조회
curl http://localhost:8000/api/v1/cancel-queue?status=PENDING

# 페이지네이션
curl http://localhost:8000/api/v1/cancel-queue?limit=20&offset=0
```

### 3. Cancel Queue 항목 삭제 (관리자)

```bash
curl -X DELETE http://localhost:8000/api/v1/cancel-queue/45
```

---

## 재시도 메커니즘

### Exponential Backoff

```
Retry 1: 즉시
Retry 2: 2초 후 (2^1)
Retry 3: 4초 후 (2^2)
Retry 4: 8초 후 (2^3)
Retry 5: 16초 후 (2^4)

Max Retries (5회) 도달 → status = FAILED
```

### 상태 전환

```
PENDING ──(취소 시도)──▶ PROCESSING
   │                       │
   │                       ▼
   │              ┌─── SUCCESS (취소 성공)
   │              │
   │              ├─── PENDING (재시도)
   │              │    retry_count++
   │              │    next_retry_at = now + 2^retry_count
   │              │
   │              └─── FAILED (재시도 소진)
   │
   └──────────────────▶ (재처리)
```

---

## 백그라운드 작업

### 실행 주기

**설정**: `CANCEL_QUEUE_INTERVAL` (기본: 10초)

```bash
# .env
CANCEL_QUEUE_INTERVAL=10
```

### 처리 로직

```python
1. PENDING 상태 조회 (next_retry_at <= now)
2. 각 항목에 대해:
   a. order_status 확인
   b. PENDING → 재시도 스케줄링
   c. OPEN → 거래소 취소 실행
   d. FILLED/CANCELLED/EXPIRED → SUCCESS
3. 성공/실패 통계 로깅
```

### 로그 예시

```
[Iteration 1] Processing 3 cancel requests
[MOCK] Cancelling order on binance: exchange_order_id=mock_123
✅ Successfully cancelled order 123
[Iteration 1] ✅ 2 succeeded, 🔄 1 will retry, ❌ 0 failed
```

---

## 서비스 API

### CancelQueueService

#### add_to_queue()

```python
async def add_to_queue(
    db: AsyncSession,
    order_id: int,
    strategy_id: Optional[int] = None,
    account_id: Optional[int] = None,
) -> CancelQueue
```

**기능**: 취소 요청을 큐에 추가

**예외**:
- `ValidationException`: 이미 큐에 존재
- `DatabaseException`: DB 오류

#### get_pending_cancels()

```python
async def get_pending_cancels(
    db: AsyncSession,
    limit: int = 100
) -> List[CancelQueue]
```

**기능**: 처리 대기 중인 취소 요청 조회

**조건**:
- status = PENDING
- next_retry_at <= now OR NULL

#### process_cancel()

```python
async def process_cancel(
    db: AsyncSession,
    cancel_item: CancelQueue,
    exchange_service
) -> bool
```

**기능**: 개별 취소 요청 처리

**흐름**:
1. 주문 상태 확인
2. PENDING → 재시도
3. OPEN → 거래소 취소
4. 성공/실패 상태 업데이트

#### verify_order_status()

```python
async def verify_order_status(
    db: AsyncSession,
    order_id: int
) -> str
```

**기능**: 주문 현재 상태 확인

**반환**: PENDING, OPEN, FILLED, CANCELLED, EXPIRED

**Note**: Phase 2에서는 Mock, Phase 4+에서 실제 구현

---

## Mock Exchange Service

Phase 2/3 테스트용 가상 거래소 서비스

### 초기화

```python
from app.services.mock_exchange_service import MockExchangeService

exchange = MockExchangeService(
    success_rate=0.95,  # 95% 성공률
    delay_ms=50         # 50ms 지연
)
```

### cancel_order()

```python
await exchange.cancel_order(
    exchange="binance",
    exchange_order_id="abc123",
    symbol="BTC/USDT"
)
```

**시뮬레이션**:
- API 지연 (delay_ms)
- 성공/실패 (success_rate)
- 로깅

---

## 설정

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CANCEL_QUEUE_INTERVAL` | 10 | Cancel Queue 처리 간격 (초) |
| `MAX_CANCEL_RETRIES` | 5 | 최대 재시도 횟수 |

### 수정 방법

```bash
# .env
CANCEL_QUEUE_INTERVAL=5   # 5초마다 처리
MAX_CANCEL_RETRIES=10     # 최대 10회 재시도
```

---

## 모니터링

### 로그 레벨

```bash
# 상세 로깅 (개발)
LOG_LEVEL=DEBUG

# 운영
LOG_LEVEL=INFO
```

### 주요 로그

**INFO**:
- Cancel Queue 추가
- 백그라운드 작업 시작/종료
- 취소 성공/실패 통계

**DEBUG**:
- 대기 중인 항목 수
- 주문 상태 확인

**ERROR**:
- 취소 실패
- DB 오류
- 예외 발생

---

## 테스트

### Unit Tests

```bash
pytest tests/test_cancel_queue_service.py -v
```

**커버리지**:
- add_to_queue()
- get_pending_cancels()
- process_cancel()
- 재시도 로직
- Exponential Backoff

### Integration Tests

```bash
# DB 필요
pytest tests/test_cancel_queue_integration.py -v --skip-db
```

---

## 문제 해결

### Cancel Queue가 처리되지 않음

**원인**: 백그라운드 작업 미실행

**해결**:
1. 앱 재시작 확인
2. 로그에서 "Cancel Queue Processor started" 확인

### 재시도가 계속 실패

**원인**:
- Mock Exchange 성공률 낮음
- 주문 상태가 계속 PENDING

**해결**:
1. Mock Exchange success_rate 확인
2. 주문 상태 수동 확인
3. 로그에서 에러 메시지 확인

### 고아 주문 여전히 발생

**원인**:
- Cancel Queue가 추가되지 않음
- 백그라운드 작업 간격이 너무 길음

**해결**:
1. 취소 요청 API 호출 확인
2. `CANCEL_QUEUE_INTERVAL` 감소
3. DB에서 cancel_queue 테이블 확인

---

## Phase 3+ 계획

### 실제 거래소 연동

- `verify_order_status()`: open_orders 테이블 조회
- `process_cancel()`: 실제 exchange_order_id 사용
- Exchange Adapter: Binance, Bybit, Upbit 실제 API

### 성능 최적화

- 분산 락 (Redis)
- Bulk 처리
- 우선순위 큐

### 모니터링 강화

- 메트릭 수집
- 알람 설정
- 대시보드

---

**최종 업데이트**: 2025-10-31
**Phase**: Phase 2 - Cancel Queue System
