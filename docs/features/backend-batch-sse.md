# Phase 2: Backend Batch SSE Implementation

## Summary
배치 주문 SSE 이벤트 구현 - 여러 주문 작업을 하나의 배치 이벤트로 통합하여 네트워크 트래픽 90% 감소

## Core Components

### 1. OrderBatchEvent Model (event_service.py:56-66)
**Purpose**: 배치 이벤트 데이터 구조 정의
```python
# @FEAT:event-sse @COMP:model @TYPE:core
@dataclass
class OrderBatchEvent:
    """Batch order update event for SSE
    Phase 2: Backend Batch SSE - Aggregate multiple order actions
    """
    summaries: List[Dict[str, Any]]  # [{order_type, created, cancelled}, ...]
    strategy_id: int
    user_id: int
    timestamp: str
```

**필드 설명**:
- `summaries`: order_type별 주문 생성/취소 카운트 (빈 항목은 필터링됨)
- `strategy_id`, `user_id`: 대상 사용자/전략 식별
- `timestamp`: ISO 8601 형식 (UTC)

### 2. emit_order_batch_event() (event_service.py:163+)
**Purpose**: 배치 이벤트를 전략별 SSE 클라이언트로 발송
- 검증: strategy_id와 summaries 확인
- Event Type: `order_batch_update`
- 라우팅: (user_id, strategy_id) 키로 해당 클라이언트만 수신

### 3. emit_order_batch_update() (event_emitter.py:475-517)
**Purpose**: 배치 결과 집계 및 SSE 발송
**알고리즘**:
```
1. O(n) 반복: order_created → created 카운트, order_cancelled → cancelled 카운트
2. order_type별 그룹화 (defaultdict)
3. 공백 필터링: created=0 AND cancelled=0 제외
4. OrderBatchEvent 생성 및 발송
```

**호출 위치**:
- `web_server/app/services/trading/core.py`: 배치 작업 완료 후
- 메타데이터 추적: order_created 플래그로 생성 판별

### 4. 배치 이벤트 포맷
```json
{
  "type": "order_batch_update",
  "data": {
    "summaries": [
      {"order_type": "LIMIT", "created": 5, "cancelled": 3},
      {"order_type": "STOP_LIMIT", "created": 2, "cancelled": 0}
    ],
    "timestamp": "2025-10-30T12:34:56.789Z"
  }
}
```

## 성능 최적화

| 메트릭 | 값 | 설명 |
|--------|-----|------|
| **시간 복잡도** | O(n) | order_type별 1회 순회 |
| **공간 복잡도** | O(k) | k = unique order_type (2-4) |
| **네트워크 감소** | 90% | 10개 개별 → 1개 배치 |

**Key Insight**: 배치 집계는 메인 스레드에서 O(n) 수행. 경량 연산이므로 성능 영향 무시할 수 있음.

## 통합 플로우

1. **Order Creation/Cancellation**: 주문 상태 변경 시 메타데이터 기록
2. **Batch Aggregation**: 배치 완료 후 emit_order_batch_update() 호출
3. **SSE Emission**: OrderBatchEvent 발송 → 프론트엔드 수신
4. **Toast Display** (frontend): createBatchToast()로 UI 업데이트

## 확장성 고려사항

**현재 구조의 장점**:
- order_type별 독립적 집계 (LIMIT, STOP_LIMIT, STOP_MARKET, MARKET)
- 빈 이벤트 자동 필터링으로 불필요한 네트워크 트래픽 제거
- 전략별 격리: 다중 사용자 환경에서 간섭 없음

**확장 가능 영역**:
- 시간대별 통계 추가 (매시간 요약)
- 이벤트 버스 큐잉 (고빈도 배치 환경)

---
*Updated: 2025-10-30 Code-Driven Documentation Sync*
