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
1. Flatten account structure (`data.account.name` → `data.account_name`, `data.account.exchange` → `data.exchange`)
2. **Detect PendingOrder** via dual checks: `status === 'PENDING_QUEUE'` OR `order_id.startsWith('p_')`
3. **Set source field** (`pending_order` | `open_order`)
4. **Validate event type** (must exist, else return early)
5. **Filter by event type**:
   - `order_created`: Show toast + upsert order only if `data.source === 'open_order'`
   - `order_filled`/`order_cancelled`: Show toast + remove order only if `data.source === 'open_order'`
   - `order_updated`: Always process (no toast)
6. **Warn on market orders** (unexpected in open orders table)

**Why PendingOrder filtering**: Single limit order creates 3 events in 1 second:
- PendingOrder created → filtered out
- PendingOrder deleted → filtered out
- OpenOrder created → **1 toast shown**

#### Method: `showOrderNotification(eventType, data)` (Lines 971-1006)
**Purpose**: Display individual toast with order type and action

**Toast Format**: `"📦 {ORDER_TYPE} 주문 {ACTION} 1건"`
- Maps event types: `order_created` → 생성, `order_filled` → 체결, `order_cancelled` → 취소, `order_updated` → 업데이트
- Example: "📦 LIMIT 주문 생성 1건", "📦 STOP_LIMIT 주문 취소 1건"

**Toast Color Types**:
- `order_filled` → info (blue)
- `order_cancelled` → warning (orange)
- `order_created` → info (blue)
- Others → info (default)

**Process Flow**:
1. Call `_removeFIFOToast()` before displaying new toast (enforce max queue)
2. Call `window.showToast(message, toastType, 2000)` to render (2s timeout)

**FIFO Management** via `_removeFIFOToast()` (Lines 1018-1053):
- Max 10 toasts (`MAX_TOASTS = 10`)
- When queue reaches limit, remove oldest toast first
- Fade-out animation (300ms via `TOAST_FADE_DURATION_MS`)
- Debug logs: FIFO check state, removal action, remaining count

#### Related: `handleBatchOrderUpdate(data)` (Lines 268-283)
**Purpose**: Handle batch order SSE events separately from individual orders
**Integration**: Batch toasts remain independent; no conflict with individual filtering

### PendingOrder Filtering Logic

**Problem**: Single limit order triggers 3 SSE events in ~1 second:
1. `order_created` (PendingOrder state - internal queue) → **filtered**
2. `order_updated` (PendingOrder state - internal queue) → **no toast**
3. `order_created` (OpenOrder state - exchange submission complete) → **1 toast shown**

**Solution**: Filter at `handleOrderUpdate()` level by detecting PendingOrder via `data.status` and `data.order_id` prefix

**Implementation** (Lines 189-231):
```javascript
// Dual detection: status field OR order_id prefix
const isPendingOrder = data.status === 'PENDING_QUEUE' ||
                      (data.order_id && data.order_id.startsWith('p_'));

// Mark source for downstream filtering
data.source = isPendingOrder ? 'pending_order' : 'open_order';

// Toast shown only for OpenOrder (exchange orders)
// PendingOrder is internal queue - no user notification
if (data.source === 'open_order') {
    this.showOrderNotification(eventType, data);
}
```

**Result**: 3 events → 1 toast (최종 거래소 주문만 표시)

**Why Dual Checks**: Status field is primary (reliable), order_id prefix is fallback (handles format variations)

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

**Dual Detection Fallback** (Lines 190-191): PendingOrder detection uses status field (primary) OR order_id prefix (fallback). This redundancy prevents notification loss if backend changes order ID format or status field encoding.

---

*Last Updated: 2025-10-30*
*Status: Active*
*Phase: Phase 1 - PendingOrder Filtering Complete*
