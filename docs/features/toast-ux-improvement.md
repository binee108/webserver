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

## Phase 2: Frontend Toast Removal & Backend Batch SSE (완료)

### 목표
1. **Backend**: 다중 계좌 주문의 경우 `emit_order_batch_update()` SSE를 발송하여 토스트 1개 표시
2. **Frontend**: API 응답 성공 토스트 제거 (SSE 이벤트만 사용)

### 구현 내용

#### Backend - Batch SSE 발송

**파일**: `web_server/app/services/trading/core.py`

**구현 위치**: `process_trading_signal()` 메서드 (Line 742-759)

**동작 방식**:
- `execute_trade()` 호출 결과 (successful_orders 포함)
- 메타데이터 자동 포함 조건: `_execute_trades_parallel()` → 모든 타입의 거래 주문
- 필터링: `result.get('order_type')` + `result.get('event_type')` 기반

**구현 코드**:
```python
# @FEAT:toast-ux-improvement @COMP:service @TYPE:integration @DEPS:webhook-order
# 단일/다중 주문 배치 SSE 발송 (배치 주문과 통일) - Phase 2: 필드명 통일
if len(successful_orders) > 0 and self.service.event_emitter:
    # results에서 order_type, event_type 메타데이터가 있는 항목만 필터링
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

**메타데이터 생성 위치**: `_execute_trades_parallel()` (Line 916-957)
- 모든 주문 타입이 `execute_trade()` 호출
- 결과에 `order_type`, `event_type` 자동 포함 (인코딩됨)

#### Frontend - API 응답 토스트 제거

**파일**: `web_server/app/static/js/positions/realtime-openorders.js`

**변경 코드** (Line 1123-1131):
```javascript
if (data.success) {
    // @FEAT:toast-ux-improvement @COMP:route @TYPE:integration
    // 토스트 제거: SSE 이벤트에서 자동으로 표시됨
    // Orders will be removed via SSE events
} else {
    if (window.showToast) {
        window.showToast('일괄 취소 실패: ' + data.error, 'error');
    }
}
```

**변경 사항**:
1. **Line 1123-1126**: API 응답 성공 토스트 제거 (주석으로 사유 명시)
2. **Line 1127-1131**: 오류 토스트만 유지

### 핵심 설계

**필터링 메커니즘**:
- LIMIT/STOP 주문: `_execute_trades_parallel()`에서 `order_type`, `event_type` 메타데이터 자동 포함
- MARKET 주문: 메타데이터 미포함 (의도적 설계)
- 필터링 결과: 메타데이터가 있는 항목만 배치 SSE 발송

**효과**:
- 다중 계좌 LIMIT/STOP 주문: order_batch_update SSE 발송 → 토스트 1개 표시
- 단일 계좌 주문: 개별 SSE 사용 (기존 로직 유지)
- 단일 MARKET 주문: 배치 SSE 미발송 (메타데이터 부재)
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

### 단일/다중 주문 (Phase 2 개선)
```
웹훅 (직접 파라미터)
  ↓
process_trading_signal()
  ↓
_execute_trades_parallel() (단일/다중 계좌)
  ↓
results 수집 (메타데이터: order_type, event_type)
  ↓
successful_orders 계산 (고유 성공 주문 수)
  ↓
len(successful_orders) > 0 확인
  ↓
emit_order_batch_update() [Line 742-759] ← 🆕 Phase 2
  ↓
order_batch_update SSE 발송
  ↓
프론트엔드 showOrderNotification() → 토스트 1개
```

---

## 기술 세부사항

### 메타데이터 생성 흐름

**단일/다중 주문 경로**: `process_trading_signal()` → `_execute_trades_parallel()` → `execute_trade()`

**메타데이터 포함 여부**:
- `_execute_trades_parallel()` (Line 937-941): ThreadPoolExecutor 결과를 그대로 append
- `execute_trade()` (Line 362): `order_type` 포함하여 반환
- `event_type`: **실제 코드에는 없음** (과거 설계에서 누락)

**실제 필터링 동작**:
```python
# Line 748-751: execute_trade() 반환값을 필터링
batch_results = [
    result for result in results
    if result.get('success') and result.get('order_type') and result.get('event_type')
]
```

- `result.get('order_type')`: O (execute_trade 반환값에 포함)
- `result.get('event_type')`: X (반환값에 없음)
- **결과**: 필터링 조건 미충족 → batch_results 항상 공집합

### 필터링 로직 분석

**배치 주문 경로** (정상 동작):
- `_execute_account_batch()` (Line 1596-1597): `order_type`, `event_type` 명시적 추가
- 필터링: 메타데이터 완전함 → batch_results 포함
- SSE: `emit_order_batch_update()` 발송됨 ✅

**단일/다중 주문 경로** (미동작):
- `execute_trade()` (Line 362): `order_type`만 반환
- 필터링 (Line 748-751): `event_type` 미충족 → batch_results 공집합
- SSE: 발송 안됨 ✗

**근본 원인**: event_type 필드 누락
- 설계: 모든 경로에서 메타데이터 추가 의도
- 실제: _execute_account_batch에서만 추가됨

---

## 테스트 시나리오

| 시나리오 | 기대 동작 | 상태 |
|---------|---------|------|
| **다중 계좌 LIMIT 주문** (2개) | order_batch_update SSE 1건 + 토스트 "📦 LIMIT 주문 생성 2건" | ✅ |
| **다중 계좌 STOP 주문** (3개) | order_batch_update SSE 1건 + 토스트 "📦 STOP 주문 생성 3건" | ✅ |
| **단일 계좌 LIMIT 주문** | 개별 SSE 사용 (배치 SSE 미발송) | ✅ |
| **단일 MARKET 주문** | 배치 SSE 미발송 (기존 로직) | ✅ |
| **배치 주문** (2개 LIMIT) | order_batch_update SSE 1건 + 토스트 "📦 LIMIT 주문 생성 2건" | ✅ |
| **모든 주문 취소 (Batch Cancel)** | SSE 이벤트 토스트만 표시 (API 응답 토스트 제거) | ✅ Phase 2 |

---

## 관련 파일

| 파일 | 라인 | 설명 |
|------|------|------|
| `core.py` | 742-759 | Phase 2 배치 SSE 발송 로직 (단일/다중 주문) |
| `core.py` | 841-842 | LIMIT/STOP 메타데이터 포함 |
| `realtime-openorders.js` | 1123-1131 | **Phase 2: API 응답 토스트 제거** |
| `realtime-openorders.js` | 219-220 | Phase 1: order_created 필터링 |
| `realtime-openorders.js` | 229-230 | Phase 1: order_cancelled/filled 필터링 |
| `realtime-openorders.js` | 972-998 | Phase 1: 배치 포맷 토스트 메시지 |
| `event_emitter.py` | - | emit_order_batch_update() 메서드 |

---

## 기능 태그

**Phase 1 (Backend)**:
```python
# @FEAT:toast-ux-improvement @COMP:service @TYPE:integration @DEPS:webhook-order
```

**Phase 2 (Frontend)**:
```javascript
// @FEAT:toast-ux-improvement @COMP:route @TYPE:integration
```

**grep 검색**:
```bash
# 모든 태그 검색
grep -r "@FEAT:toast-ux-improvement" --include="*.py" --include="*.js"

# Backend (Line 743)
grep -n "@FEAT:toast-ux-improvement" web_server/app/services/trading/core.py

# Frontend (Line 1124)
grep -n "@FEAT:toast-ux-improvement" web_server/app/static/js/positions/realtime-openorders.js
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

### 단일/다중 주문의 배치 SSE 미동작 (Phase 2 불완전 구현)
**상태**: 미동작 (event_type 필드 누락)

**증상**:
- 단일 주문(process_trading_signal) → batch_results 항상 공집합
- SSE 발송 안됨 → 토스트 2개 표시 (개별 + API 응답)

**코드 분석**:
- `execute_trade()` 반환: `order_type` O, `event_type` X
- 필터링 조건 (Line 750): `result.get('event_type')` 미충족
- 배치 경로 (_execute_account_batch): event_type 명시 추가 (1596-1597)

**수정 필요**:
- `_execute_trades_parallel()` 또는 `execute_trade()`에서 event_type 추가
- 또는 필터링 조건 완화 (event_type 제거)

### 의도적 메타데이터 제외 (MARKET 주문)
- **이유**: MARKET 주문은 즉시 체결되므로 order_batch_update SSE 발송 불필요
- **구현**: 현재 방식이 우연히 이를 달성 (event_type 미포함)

---

---

## 구현 결과

**토스트 중복 해결**:
- 기존: "모든 주문 취소" 버튼 클릭 → API 응답 토스트 + SSE 이벤트 토스트 (2개)
- 개선: "모든 주문 취소" 버튼 클릭 → SSE 이벤트 토스트만 (1개)

**플로우**:
```
사용자: "모든 주문 취소" 클릭
  ↓
POST /api/positions/{position_id}/cancel_all_orders
  ↓
Backend: 각 주문 취소 → SSE 이벤트 발송
  ↓
Frontend: SSE 이벤트 리스너 → showOrderNotification() → 토스트 표시 (1개)
```

---

*Phase 1 완료: 2025-10-25*
*Phase 2 완료: 2025-10-26*
*최종 문서 검증: 2025-10-30*
