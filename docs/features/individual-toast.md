# Individual Order Toast Notification

## Summary
Individual toast notifications for single order events (order_created, order_filled, order_cancelled), separated from batch order notifications. Provides immediate user feedback with PendingOrder filtering to eliminate duplicate notifications (3 events → 1 toast).

**Tag**: `@FEAT:individual-toast @COMP:integration @TYPE:core` (Line 174 in realtime-openorders.js)

## Implementation Details

### Frontend Integration
**File**: `/Users/binee/Desktop/quant/webserver/web_server/app/static/js/positions/realtime-openorders.js`

#### Method: `handleOrderUpdate(data)` (Lines 179-248)
**Purpose**: Handle SSE `order_update` events with PendingOrder filtering

**Workflow**:
1. Flatten account structure (`data.account.name` → `data.account_name`)
2. **Detect PendingOrder** via status or order_id prefix (`p_`)
3. **Set source field** (`pending_order` | `open_order`)
4. **Filter by event type**:
   - `order_created`: Show toast only if `data.source === 'open_order'`
   - `order_filled`/`order_cancelled`: Show toast only if `data.source === 'open_order'`
   - `order_updated`: Always process (no toast)

**Why PendingOrder filtering**: Single limit order creates 3 events in 1 second:
- PendingOrder created → filtered out
- PendingOrder deleted → filtered out
- OpenOrder created → **1 toast shown**

#### Method: `showOrderNotification(eventType, data)` (Lines 971-1006)
**Purpose**: Display individual toast with order type and action

**Toast Format**: `"📦 {ORDER_TYPE} 주문 {ACTION} 1건"`
- Example: "📦 LIMIT 주문 생성 1건", "📦 STOP_LIMIT 주문 취소 1건"

**Toast Types**:
- `order_filled` → info (blue)
- `order_cancelled` → warning (orange)
- `order_created` → info (blue)

**FIFO Management** (Lines 1018-1050):
- Max 10 toasts (`MAX_TOASTS = 10`)
- Oldest toast auto-removed when limit exceeded
- Fade-out animation (300ms via `TOAST_FADE_DURATION_MS`)

#### Related: `handleBatchOrderUpdate(data)` (Lines 268-283)
**Purpose**: Handle batch order SSE events separately from individual orders
**Integration**: Batch toasts remain independent; no conflict with individual filtering

### PendingOrder Filtering Logic

**Problem**: Single limit order triggers 3 notifications in ~1 second:
1. PendingOrder created (내부 큐 상태)
2. PendingOrder deleted (제거 됨)
3. OpenOrder created (거래소 제출 완료) ✓

**Solution**: Filter at `handleOrderUpdate()` level using `data.source` field

**Implementation** (Lines 189-231):
```javascript
// Detect PendingOrder
const isPendingOrder = data.status === 'PENDING_QUEUE' ||
                      (data.order_id && data.order_id.startsWith('p_'));

// Add source field
data.source = isPendingOrder ? 'pending_order' : 'open_order';

// Show toast only for open_order
if (data.source === 'open_order') {
    this.showOrderNotification(eventType, data);
}
```

**Result**: 3 events → 1 toast (최종 거래소 주문만 표시)

## Related Features
- **batch-sse**: Batch order toast notifications for bulk operations (complementary)
- **open-orders-sorting**: Open orders table management with SSE integration
- **toast-system**: Core FIFO queue and auto-remove logic

## Testing Scenarios

### Test 1: Single Order Limit Creation
**Action**: Create single LIMIT order
**Expected**:
- 1 toast appears: "📦 LIMIT 주문 생성 1건"
- No duplicate toasts for PendingOrder events

### Test 2: Single Order Cancellation
**Action**: Cancel single open order
**Expected**: Toast appears: "📦 LIMIT 주문 취소 1건" (warning type)

### Test 3: Single Order Fill
**Action**: Order gets filled via exchange
**Expected**: Toast appears: "📦 LIMIT 주문 체결 1건" (info type)

### Test 4: Batch Orders (Regression)
**Action**: Create batch orders (5+ orders) via webhook
**Expected**:
- Batch toasts appear (one per order type: "📦 LIMIT 주문 생성 5건")
- No individual order creation toasts
- Separate from individual toast system

### Test 5: FIFO Queue Management
**Action**: Create 11+ individual orders rapidly
**Expected**:
- First 10 toasts display simultaneously
- 11th toast triggers oldest toast removal
- Queue stays at max 10

### Test 6: Order Table Visualization
**Action**: Create order in queue (PendingOrder state)
**Expected**:
- Row shows "대기열" badge (not toast)
- No toast notification for queue state
- Toast appears only when OpenOrder created

## Known Issues

**Order Status Transition** (Lines 189-199): Detecting PendingOrder via dual checks (`status === 'PENDING_QUEUE'` AND `order_id.startsWith('p_')`) ensures robustness across API response variations. If backend changes order ID format, code remains stable via status field fallback.

---

*Last Updated: 2025-10-30*
*Status: Active*
*Phase: Phase 1 - PendingOrder Filtering Complete*
