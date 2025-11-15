# Phase 2: Backend Batch SSE Implementation

## Summary
배치 주문 SSE 이벤트 구현 - 여러 주문 작업을 하나의 배치 이벤트로 통합하여 네트워크 트래픽 90% 감소

## Core Components

### 1. OrderBatchEvent Model (event_service.py:57-66)
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
- `strategy_id`, `user_id`: 대상 사용자/전략 식별 (전략별 격리 모드)
- `timestamp`: ISO 8601 형식 (UTC, 'Z' suffix 포함)

### 2. emit_order_batch_event() (event_service.py:163-194)
**Purpose**: 배치 이벤트를 전략별 SSE 클라이언트로 발송

**검증 로직**:
- strategy_id 존재 여부 확인 (0이면 차단)
- summaries 존재 여부 확인 (비어있으면 스킵)

**Event 포맷**:
- Type: `order_batch_update`
- 라우팅: (user_id, strategy_id) 키로 전략별 격리
- 로깅: `📦 Batch SSE sent` + summaries 개수

### 3. emit_order_batch_update() (event_emitter.py:453-517)
**Purpose**: 배치 결과 집계 및 SSE 발송

**알고리즘**:
```
1. batch_results 입력: success + order_type + event_type 필드
2. O(n) 반복: event_type == 'order_created' → created++, 'order_cancelled' → cancelled++
3. order_type별 grouping (defaultdict)
4. 공백 필터링: created=0 AND cancelled=0 제외
5. OrderBatchEvent 생성 후 emit_order_batch_event() 호출
```

**입력 파라미터**:
- `user_id`: 사용자 ID (SSE 라우팅용)
- `strategy_id`: 전략 ID (검증용)
- `batch_results`: order_type, event_type, success 필드 포함 딕셔너리 리스트

**로깅**:
- 성공: `Batch aggregation: {len(summaries)} order types`
- 실패: `No successful orders - batch SSE skipped`

### 4. 배치 이벤트 포맷 (event_service.py:185-191)
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

**주목**: event_emitter에서 `datetime.utcnow().isoformat() + 'Z'`로 생성

## 성능 최적화

| 메트릭 | 값 | 설명 |
|--------|-----|------|
| **시간 복잡도** | O(n) | order_type별 1회 순회 |
| **공간 복잡도** | O(k) | k = unique order_type (2-4) |
| **네트워크 감소** | 90% | 10개 개별 → 1개 배치 |

**Key Insight**: 배치 집계는 메인 스레드에서 O(n) 수행. 경량 연산이므로 성능 영향 무시할 수 있음.

## 통합 플로우

```
주문 생성/취소
    ↓
batch_results 리스트에 메타데이터 수집
  (order_type, event_type='order_created|order_cancelled', success=True)
    ↓
EventEmitter.emit_order_batch_update(user_id, strategy_id, batch_results)
    ↓
order_type별 집계 + 공백 필터링
    ↓
OrderBatchEvent 생성 (strategy_id, user_id, summaries, timestamp)
    ↓
EventService.emit_order_batch_event(batch_event)
    ↓
_emit_to_user() → SSE 클라이언트에 이벤트 발송 (전략별 격리)
    ↓
프론트엔드 수신: type='order_batch_update'
```

## 확장성 고려사항

**현재 구조의 장점**:
- order_type별 독립적 집계 (LIMIT, STOP_LIMIT, STOP_MARKET, MARKET)
- 빈 이벤트 자동 필터링으로 불필요한 네트워크 트래픽 제거
- 전략별 격리: 다중 사용자 환경에서 간섭 없음

**확장 가능 영역**:
- 시간대별 통계 추가 (매시간 요약)
- 이벤트 버스 큐잉 (고빈도 배치 환경)

---
**Last Updated**: 2025-10-30 (Code-Driven Sync)
- ✅ 라인 번호 최신화: event_service.py 57-194, event_emitter.py 453-517
- ✅ 검증 로직 상세화: strategy_id, summaries 검증 추가
- ✅ 알고리즘 정확화: 입력 파라미터, 로깅 메시지 추가
- ✅ 통합 플로우 다이어그램화: 실제 코드 흐름 반영
