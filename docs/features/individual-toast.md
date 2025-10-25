# Individual Order Toast Notification

## Summary
Individual toast notifications for single order events (order_created, order_filled, order_cancelled), separated from batch order notifications. Provides immediate user feedback for individual order actions with order details (symbol, side, quantity).

## Implementation Details

### Frontend Integration
**File**: `web_server/app/static/js/positions/realtime-openorders.js`

#### Method: `handleOrderUpdate(data)`
- **Location**: Line 184
- **Purpose**: Handle SSE `order_update` events from backend
- **Behavior**:
  - Receives individual order events (order_created, order_filled, order_cancelled)
  - Extracts account and exchange information from nested structure
  - Determines PendingOrder vs OpenOrder status
  - Calls `showOrderNotification()` for each order event
- **Performance**: <10ms per event

#### Method: `showOrderNotification(eventType, data)`
- **Location**: Line 971
- **Purpose**: Display individual toast with order details
- **Toast Content**:
  - Event type (새 주문 / 주문 체결 / 주문 취소)
  - Symbol (e.g., BTC/USDT)
  - Side (BUY / SELL)
  - Quantity (e.g., 0.01 BTC)
  - PendingOrder suffix: "(대기열)"
- **Queue Management**: Uses FIFO queue (max 10 toasts, auto-remove oldest)
- **Duration**: Configurable via `TOAST_FADE_DURATION_MS` (default: 300ms)

### Design Decision

**Previous Policy**:
- "Batch SSE only" - all order updates used batch notifications
- Delayed feedback for individual orders

**New Policy**:
- Individual toasts for critical order events (order_created, order_filled, order_cancelled)
- Batch toasts remain for bulk operations (batch orders, rebalancing)

**Rationale**:
- **Immediate Feedback**: Users see individual order actions instantly
- **Critical Events**: Individual toasts for user-triggered actions, batch toasts for background operations
- **Complementary**: Not competing systems; batch toasts aggregate multiple orders

## Related Features
- **batch-sse**: Batch order toast notifications for bulk operations (complementary)
- **open-orders-sorting**: Open orders table management with SSE integration
- **toast-system**: Core FIFO queue and auto-remove logic

## Code References
- `handleOrderUpdate()`: realtime-openorders.js:184-243
- `showOrderNotification()`: realtime-openorders.js:971-1007

## Testing Scenarios

### Test 1: Single Order Creation
**Action**: Create single order via UI or webhook
**Expected**: Toast appears with format "새 주문: {SYMBOL} {SIDE} {QUANTITY}"

### Test 2: Single Order Cancellation
**Action**: Cancel single order
**Expected**: Toast appears with format "주문 취소: {SYMBOL} {SIDE} {QUANTITY}"

### Test 3: Single Order Fill
**Action**: Order gets filled via exchange
**Expected**: Toast appears with format "주문 체결: {SYMBOL} {SIDE} {QUANTITY}"

### Test 4: Batch Orders (Regression)
**Action**: Create batch orders (5+ orders) via webhook
**Expected**:
- Batch toast appears (single aggregated toast)
- Individual toasts do NOT appear
- Verification: Both notifications work together

### Test 5: FIFO Queue Management
**Action**: Create 10+ individual orders rapidly
**Expected**:
- First 10 toasts display
- 11th toast auto-removes oldest (FIFO)
- Queue stays at max 10

### Test 6: PendingOrder Display
**Action**: Order in queue (pending state)
**Expected**: Toast shows "(대기열)" suffix indicating pending order

## Edge Cases

**Multiple Orders Same Event**: Different symbols handled separately
**Rapid Burst**: Queue management prevents overflow (max 10)
**Missing Fields**: Fallback to default values (Unknown symbol, Missing quantity)

---

## PendingOrder Filtering (UX Improvement)

**문제**: 단일 지정가 주문 시 1초 내에 3개의 토스트가 발생하여 사용자 경험 저하
1. PendingOrder 생성 토스트
2. PendingOrder 삭제 토스트
3. OpenOrder(NEW) 생성 토스트

**해결**: OpenOrder 생성 시에만 1개 토스트 표시

### 구현 방식

`handleOrderUpdate()` 메서드에서 `data.source` 필드를 기준으로 필터링:

- `data.source === 'pending_order'` → 토스트 표시 안 함 (내부 큐 상태)
- `data.source === 'open_order'` → 토스트 표시 (거래소 주문)

### 적용 대상

- `order_created`: OpenOrder 생성 시에만 토스트
- `order_cancelled`: OpenOrder 취소 시에만 토스트
- `order_filled`: OpenOrder 체결 시에만 토스트

### 배치 주문 영향

배치 주문 토스트(`handleBatchOrderUpdate()`)는 별도 로직으로 영향 없음.

---

*Last Updated: 2025-10-25*
*Status: Active*
*Phase: Phase 1 - PendingOrder Filtering Complete*
