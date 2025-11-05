# Order Cancellation (주문 취소)

**Feature Tag**: `@FEAT:order-cancellation`
**Component**: `@COMP:service`
**Type**: `@TYPE:core`
**Related Features**: `@FEAT:orphan-order-prevention`

---

## Overview

주문 취소 시스템은 **DB-First 패턴**을 사용하여 타임아웃 시 orphan order를 방지하고, Binance API Error -2011 (Unknown order) 특수 처리를 통해 DB 정합성을 자동으로 복구합니다.

### Key Features

1. **DB-First 상태 관리**: 거래소 API 호출 전 DB 상태를 먼저 변경
2. **6가지 처리 경로**: 정상, 실패, Binance Error -2011 (3 cases), 예외
3. **Race Condition 방어**: 모든 DB 작업 전 재조회
4. **자동 재시도**: FailedOrder 시스템 통합 (최대 5회)

---

## Implementation

### File Location
**Path**: `web_server/app/services/trading/order_manager.py`
**Function**: `cancel_order(order_id, symbol, account_id, ...)`
**Lines**: 77-550

### Architecture

```
cancel_order() 호출
    ↓
Step 1: DB 상태 → CANCELLING (Line 157)
    ↓
Step 2: 거래소 API 호출 (Line 173-180, 타임아웃 10초, 재시도 3회)
    ↓
Step 3: 성공 시 → CANCELLED (DB 삭제, Line 185-253)
    ↓
Step 4: 실패 시 → 2가지 경로
    ├─ Binance Error -2011 → fetch_order() 재조회 (Line 283-399)
    │   ├─ FILLED/CANCELED/EXPIRED → DB 삭제 (정합성 복구)
    │   ├─ NEW/OPEN/PARTIALLY_FILLED → FailedOrder 추가 (재시도)
    │   └─ 조회 실패 → 안전 삭제
    │
    └─ 기타 오류 (-1021, -2015) → OPEN 복원 + FailedOrder 추가 (Line 401-426)
    ↓
Step 5: 예외 시 → 하이브리드 처리 (1회 재확인 + 백그라운드, Line 428-532)
```

---

## Phase History

### Phase 1 (Initial) - DB-First 패턴
- DB 상태를 먼저 CANCELLING으로 변경
- 거래소 API 호출 후 결과에 따라 CANCELLED/OPEN 전환
- Race condition 방어 (재조회 로직)

### Phase 2 - 취소 실패 추적
- FailedOrder 시스템 통합
- `create_failed_cancellation()` 자동 호출
- 최대 5회 재시도 메커니즘

### Phase 3 - 타임아웃/재시도 강화
- `cancel_order_with_retry()` 도입
- 타임아웃 10초, 최대 3회 재시도
- 네트워크 오류 복원력 향상

### Phase 4 (Issue #32, 2025-11-05) - Binance Error -2011 처리
- **Problem**: 즉시 체결 LIMIT 주문 취소 시 `-2011: Unknown order sent` 오류 발생
- **Solution**: Error -2011 감지 → `fetch_order()` 재조회 → 3-case 분기 처리
- **Impact**: DB 정합성 자동 복구, 체결된 OpenOrder 즉시 정리

---

## Edge Cases

### 1. Already Cancelling
**Scenario**: 주문이 이미 CANCELLING 상태
**Handling**: 즉시 반환 (`error_type: 'already_cancelling'`)
**Code**: Line 137-142

### 2. Order Not Found
**Scenario**: OpenOrder DB에 없음
**Handling**: 즉시 반환 (`error_type: 'order_not_found'`)
**Code**: Line 129-134

### 3. Race Condition
**Scenario**: 다른 프로세스가 동시에 주문 삭제
**Handling**: 재조회 후 없으면 안전 종료
**Code**: Line 262-268, 316-321, 353-359, 387-393

### 4. Binance Error -2011 (Issue #32)
**Scenario**: 즉시 체결 LIMIT 주문 취소 시 "Unknown order" 오류
**Root Cause**: 주문이 매우 빠르게 체결되어 거래소에서 이미 제거됨
**Handling**: 3-case 분기 처리 (아래 상세 설명)
**Code**: Line 283-399

---

## Known Issues & Workarounds

### Binance Error -2011: Unknown order sent (Issue #32)

#### 현상
즉시 체결되는 LIMIT 주문의 취소 요청 시 거래소에서 "Unknown order sent" 에러 반환

#### 원인
1. 주문이 매우 빠르게 체결됨 (수백 밀리초 내)
2. 취소 요청이 체결 직후 도착
3. 거래소 입장: 이미 없는 주문을 취소하려고 함
4. OpenOrder는 DB에 남아있지만 거래소에는 없음 → DB 정합성 문제

#### 해결 방법 (Phase 4)

**Step 1**: Error -2011 감지 (Line 293)
```python
if '-2011' in error_msg or 'Unknown order' in error_msg:
```

**Step 2**: `fetch_order()` 재조회 (Line 299-304)
```python
fetched_order = exchange_service.fetch_order(
    account=account,
    symbol=symbol,
    order_id=order_id,
    market_type=market_type
)
```

**Step 3**: 주문 상태 확인 후 3가지 케이스 분기

##### Case 1: FILLED/CANCELED/EXPIRED (Line 310-339)
- **의미**: 주문이 거래소에서 이미 종료됨
- **처리**:
  1. OpenOrder DB에서 즉시 삭제
  2. SSE 이벤트 발송 (UI 업데이트)
  3. 성공 반환 (`action: 'removed'`)
- **로그**: `✅ 주문 이미 종료 (FILLED) → DB 삭제`

##### Case 2: NEW/OPEN/PARTIALLY_FILLED (Line 342-379)
- **의미**: 취소 실패했지만 주문은 여전히 거래소에 존재
- **처리**:
  1. OpenOrder 상태를 원래대로 복원 (CANCELLING → OPEN)
  2. FailedOrder 큐에 추가 (자동 재시도 활성화)
  3. 최대 5회까지 재시도
- **로그**: `⚠️ 취소 실패하지만 주문 존재 (OPEN) → FailedOrder 추가 (재시도 대기)`
- **Note**: PARTIALLY_FILLED는 Phase 2에서 filled_quantity 확인 추가 고려 (TODO: Line 348-350)

##### Case 3: 조회 실패 또는 주문 없음 (Line 381-399)
- **의미**: 재조회 자체가 실패하거나 주문이 거래소에 없음
- **처리**:
  1. OpenOrder DB에서 안전하게 삭제
  2. 성공 반환 (거래소에 없으므로 취소 목적 달성)
- **로그**: `⚠️ 주문 조회 실패 또는 거래소에 없음 → DB 정리`

#### 코드 예시

```python
# Line 283-399: Binance Error -2011 특수 처리
if '-2011' in error_msg or 'Unknown order' in error_msg:
    logger.info(f"🔍 Binance Error -2011 감지 → 주문 상태 재조회: {order_id}")

    fetched_order = exchange_service.fetch_order(...)

    if fetched_order and fetched_order.get('success'):
        final_status = fetched_order.get('status', '').upper()

        # Case 1: 종료된 주문 → DB 정리
        if final_status in ['FILLED', 'CANCELED', 'EXPIRED']:
            db.session.delete(open_order)
            db.session.commit()
            return {'success': True, 'action': 'removed'}

        # Case 2: 활성 주문 → 재시도
        elif final_status in ['NEW', 'OPEN', 'PARTIALLY_FILLED']:
            open_order.status = old_status
            db.session.commit()
            failed_order_manager.create_failed_cancellation(open_order)
            return {'success': False, 'error_type': 'pending_retry'}

    # Case 3: 조회 실패 → 안전 삭제
    else:
        db.session.delete(open_order)
        db.session.commit()
        return {'success': True, 'message': 'Order not found on exchange'}
```

---

## Performance Characteristics

### API Calls
- **정상 경로**: 1× `cancel_order_with_retry()` (최대 3회 재시도)
- **Binance Error -2011**: +1× `fetch_order()` (재조회)
- **예외 경로**: +1× `fetch_order()` (재확인)

### Database Operations
- **정상 경로**: 2× commit (CANCELLING → CANCELLED)
- **실패 경로**: 2× commit (CANCELLING → OPEN)
- **-2011 Case 1**: 2× commit (CANCELLING → DELETE)
- **-2011 Case 2**: 2× commit (CANCELLING → OPEN)

### Expected Latency
- **정상 취소**: 100-300ms
- **-2011 처리**: +100-200ms (fetch_order 추가)
- **예외 처리**: +200-500ms (재확인 추가)

---

## Debugging Guide

### Log Message Patterns

#### 정상 경로
```
🔄 주문 취소 시작: OPEN → CANCELLING
✅ 거래소 취소 확인 → DB 삭제
✅ 취소된 주문이 정리되었습니다
```

#### Binance Error -2011 (Case 1: FILLED)
```
🔄 주문 취소 시작: OPEN → CANCELLING
🔍 Binance Error -2011 감지 → 주문 상태 재조회
✅ 주문 이미 종료 (FILLED) → DB 삭제
```

#### Binance Error -2011 (Case 2: OPEN)
```
🔄 주문 취소 시작: OPEN → CANCELLING
🔍 Binance Error -2011 감지 → 주문 상태 재조회
⚠️ 취소 실패하지만 주문 존재 (OPEN) → FailedOrder 추가 (재시도 대기)
```

#### Binance Error -2011 (Case 3: Not Found)
```
🔄 주문 취소 시작: OPEN → CANCELLING
🔍 Binance Error -2011 감지 → 주문 상태 재조회
⚠️ 주문 조회 실패 또는 거래소에 없음 → DB 정리
```

#### 기타 오류
```
🔄 주문 취소 시작: OPEN → CANCELLING
⚠️ 거래소 취소 실패 → OPEN 복원
```

### Monitoring Recommendations

**Key Metrics**:
1. `order_cancel.error_2011.total` - Error -2011 발생 빈도
2. `order_cancel.error_2011.case_filled` - Case 1 (FILLED) 빈도
3. `order_cancel.error_2011.case_open` - Case 2 (OPEN) 빈도
4. `order_cancel.error_2011.case_not_found` - Case 3 (조회 실패) 빈도

**Alert Thresholds**:
- Case 1 (FILLED): 정상, 알람 불필요
- Case 2 (OPEN): > 5회/시간 → 조사 필요 (API 문제 또는 로직 버그)
- Case 3 (Not Found): > 1회/시간 → 데이터 정합성 조사 필요

---

## Related Features

### FailedOrder Retry System
- **Feature**: `@FEAT:orphan-order-prevention`
- **Integration**: `failed_order_manager.create_failed_cancellation()`
- **Retry Logic**: 최대 5회, 재시도 간격 증가 (exponential backoff)
- **File**: `web_server/app/services/trading/failed_order_manager.py`

### SSE Event System
- **Event**: `order_cancelled`
- **Purpose**: UI 실시간 업데이트
- **File**: `web_server/app/services/event_emitter.py`

### Exchange Service
- **Methods**: `cancel_order_with_retry()`, `fetch_order()`
- **Features**: 타임아웃 10초, 재시도 3회
- **File**: `web_server/app/services/exchange/exchange_service.py`

---

## Testing Recommendations

### Unit Tests
1. `test_cancel_order_success` - 정상 취소
2. `test_cancel_order_already_cancelling` - 중복 취소 방어
3. `test_cancel_order_not_found` - 주문 없음 처리
4. `test_cancel_order_error_2011_filled` - Binance -2011 Case 1
5. `test_cancel_order_error_2011_open` - Binance -2011 Case 2
6. `test_cancel_order_error_2011_fetch_failure` - Binance -2011 Case 3
7. `test_cancel_order_other_error` - 기타 오류 처리
8. `test_cancel_order_race_condition` - Race condition 방어

### Integration Tests
1. Binance testnet에서 즉시 체결 LIMIT 주문 생성 → 취소
2. logs/app.log에서 `🔍 Binance Error -2011 감지` 확인
3. OpenOrder 테이블에서 삭제 확인
4. FailedOrder 테이블 확인 (Case 2인 경우)

---

## Future Enhancements (Phase 2)

### PARTIALLY_FILLED 처리 개선
**Current**: 재시도 큐에 추가하여 재취소 시도
**Phase 2**: `fetch_order()` 결과의 `filled_quantity` 확인 → Trade 레코드 생성 후 재취소
**Benefit**: 부분 체결 정보 보존, 데이터 정합성 향상

### 메트릭 추가
```python
self.service.metrics.increment('order_cancel.error_2011.case_filled')
self.service.metrics.increment('order_cancel.error_2011.case_open')
self.service.metrics.increment('order_cancel.error_2011.case_not_found')
```

---

## References

- **Issue**: [#32 - 즉시 체결 LIMIT 주문의 OpenOrder 생성 및 취소 실패 처리 개선](https://github.com/binee108/webserver/issues/32)
- **Related Issue**: [#30 - LIMIT Order Fill Processing Bug Fix](https://github.com/binee108/webserver/issues/30)
- **Binance API Error Codes**: https://binance-docs.github.io/apidocs/spot/en/#error-codes
- **Feature Catalog**: `docs/FEATURE_CATALOG.md`

---

*Last Updated: 2025-11-05 (Phase 4 - Issue #32)*
*Maintainer: Trading System Team*
