# Toast UX Improvement Feature

## 개요

단일 주문(Single Order)과 배치 주문(Batch Order)의 Toast 알림을 통일하여 일관된 사용자 경험(UX) 제공

**목표**:
- Phase 1: PendingOrder 토스트 필터링 + 배치 포맷 통일
- Phase 2: 단일 주문도 배치 SSE 발송하여 토스트 1개 표시

---

## Phase 1: Frontend Toast Filtering & Format (완료)

### 목표
PendingOrder(내부 큐)의 토스트 필터링 및 OpenOrder(거래소 주문) 토스트를 배치 포맷으로 통일

### 구현 내용

**파일**: `web_server/app/static/js/positions/realtime-openorders.js`

**변경 사항**:
1. **Line 219-220**: `order_created` 이벤트 필터링
   - 조건: `data.source === 'open_order'`
   - 효과: PendingOrder 토스트 차단, OpenOrder만 표시

2. **Line 229-230**: `order_cancelled`/`order_filled` 이벤트 필터링
   - 조건: `data.source === 'open_order'`
   - 효과: PendingOrder 제거 이벤트 토스트 차단

3. **Line 972-998**: `showOrderNotification()` 메서드 배치 포맷 적용
   - 포맷: `"📦 {주문타입} 주문 {액션} 1건"`
   - 예시: "📦 LIMIT 주문 생성 1건", "📦 MARKET 주문 체결 1건"
   - 배치 주문과 동일한 포맷으로 통일

### 효과
- **토스트 감소**: 단일 주문당 3개 → 0개 (PendingOrder 필터링)
- **포맷 통일**: 배치 주문과 동일한 "📦" 아이콘 + 카운트 포맷
- **사용자 경험**: 거래소 체결 주문만 명확한 피드백 제공

---

## Phase 2: Backend Batch SSE for Single Orders (완료)

### 목표
단일 주문(`process_trading_signal()`)도 배치 주문과 동일하게 `emit_order_batch_update()` SSE를 발송하여 토스트 1개 표시

### 구현 내용

**파일**: `web_server/app/services/trading/core.py`

**추가 코드** (Line 726-743):
```python
# 🆕 Phase 2: 단일 주문도 배치 SSE 발송 (배치 주문과 통일)
# @FEAT:toast-ux-improvement @COMP:service @TYPE:integration @DEPS:webhook-order
if len(successful_trades) > 0 and self.service.event_emitter:
    # results에서 order_type, event_type 메타데이터가 있는 항목만 필터링
    # LIMIT/STOP 주문은 _execute_trades_parallel()에서 메타데이터 포함
    # MARKET 주문은 메타데이터 없음 (자연스럽게 제외)
    batch_results = [
        result for result in results
        if result.get('success') and result.get('order_type') and result.get('event_type')
    ]

    # 배치 SSE 발송 (메타데이터가 있는 경우만)
    if batch_results:
        self.service.event_emitter.emit_order_batch_update(
            user_id=strategy.user_id,
            strategy_id=strategy.id,
            batch_results=batch_results
        )
```

### 핵심 설계

**필터링 메커니즘**:
- LIMIT/STOP 주문: `_execute_trades_parallel()`에서 `order_type`, `event_type` 메타데이터 자동 포함
- MARKET 주문: 메타데이터 미포함 (의도적 설계)
- 필터링 결과: 메타데이터가 있는 항목만 배치 SSE 발송

**효과**:
- 단일 LIMIT/STOP 주문: order_batch_update SSE 발송 → 토스트 1개 표시
- 단일 MARKET 주문: 배치 SSE 미발송 (기존 로직 유지)
- 배치 주문: 기존 동작 유지 (회귀 방지)

---

## SSE 플로우 비교

### 배치 주문 (정상 동작)
```
웹훅 (orders 배열)
  ↓
process_batch_trading_signal()
  ↓
_execute_account_batch()
  ↓
results 수집 (메타데이터 포함)
  ↓
emit_order_batch_update() [Line 1342]
  ↓
order_batch_update SSE 발송
  ↓
프론트엔드 showOrderNotification() → 토스트 1개
```

### 단일 주문 (Phase 2 개선)
```
웹훅 (직접 파라미터)
  ↓
process_trading_signal()
  ↓
_execute_trades_parallel()
  ↓
results 수집 (메타데이터: order_type, event_type)
  ↓
emit_order_batch_update() [Line 726-743] ← 🆕 Phase 2
  ↓
order_batch_update SSE 발송
  ↓
프론트엔드 showOrderNotification() → 토스트 1개
```

---

## 기술 세부사항

### 메타데이터 소스

**`_execute_trades_parallel()` (core.py Line 841-842)**:
```python
# LIMIT/STOP 주문 결과에 메타데이터 자동 포함
result['order_type'] = 'LIMIT'  # 또는 'STOP_LIMIT'
result['event_type'] = 'order_created'
```

**MARKET 주문**:
- `order_type`, `event_type` 미포함
- 필터링 로직에서 자동 제외됨

### 필터링 로직

**Phase 2 필터링** (Line 732-735):
```python
batch_results = [
    result for result in results
    if result.get('success') and result.get('order_type') and result.get('event_type')
]
```

**동작**:
- `result.get('success')`: 성공한 주문만
- `result.get('order_type')`: 주문 타입 존재 여부
- `result.get('event_type')`: 이벤트 타입 존재 여부

---

## 테스트 시나리오

| 시나리오 | 기대 동작 | 상태 |
|---------|---------|------|
| 단일 LIMIT 주문 | order_batch_update SSE 1건 + 토스트 "📦 LIMIT 주문 생성 1건" | ✅ |
| 단일 STOP 주문 | order_batch_update SSE 1건 + 토스트 "📦 STOP 주문 생성 1건" | ✅ |
| 단일 MARKET 주문 | 배치 SSE 미발송 (기존 로직) | ✅ |
| 배치 주문 (2개 LIMIT) | order_batch_update SSE 1건 + 토스트 "📦 LIMIT 주문 생성 2건" | ✅ |

---

## 관련 파일

| 파일 | 라인 | 설명 |
|------|------|------|
| `core.py` | 726-743 | Phase 2 배치 SSE 발송 로직 |
| `core.py` | 841-842 | LIMIT/STOP 메타데이터 포함 |
| `realtime-openorders.js` | 219-220 | order_created 필터링 |
| `realtime-openorders.js` | 229-230 | order_cancelled/filled 필터링 |
| `realtime-openorders.js` | 972-998 | 배치 포맷 토스트 메시지 |
| `event_emitter.py` | - | emit_order_batch_update() 메서드 |

---

## 기능 태그

```python
# @FEAT:toast-ux-improvement
# @COMP:service (backend), route (frontend)
# @TYPE:integration
# @DEPS:webhook-order, event-sse
```

**grep 검색**:
```bash
# Phase 1 (Frontend)
grep -n "@FEAT:toast-ux-improvement" web_server/app/static/js/positions/realtime-openorders.js

# Phase 2 (Backend)
grep -n "@FEAT:toast-ux-improvement" web_server/app/services/trading/core.py
```

---

## 유지보수 가이드

### 새로운 주문 타입 추가 시
1. `_execute_trades_parallel()`에서 해당 주문 타입 결과에 `order_type`, `event_type` 메타데이터 포함
2. 자동으로 배치 SSE 발송 및 토스트 표시됨 (추가 코드 불필요)

### SSE 포맷 변경 시
- `event_emitter.py`의 `emit_order_batch_update()` 메서드만 수정
- 단일 주문/배치 주문 모두 자동 반영 (단일 소스)

### 토스트 포맷 변경 시
- `realtime-openorders.js`의 `showOrderNotification()` 메서드만 수정
- Phase 1 + Phase 2 모든 주문이 동일한 포맷으로 통일됨

---

## Known Issues & Design Decisions

### 의도적 메타데이터 제외 (MARKET 주문)
- **이유**: MARKET 주문은 즉시 체결되므로 order_batch_update SSE 발송 불필요
- **구현**: `_execute_trades_parallel()`에서 MARKET 결과에 메타데이터 미포함
- **효과**: 필터링 로직에서 자연스럽게 제외

---

*Phase 1 완료: 2025-10-25*
*Phase 2 완료: 2025-10-25*
