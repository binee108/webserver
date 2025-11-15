# Toast Notification System

## Summary

Complete toast notification management system for app-wide notifications:
- **Global `showToast()` function** - Centralized toast creation and display
- **FIFO queue management** - Maximum 10 concurrent toasts, automatic removal of oldest
- **Race condition protection** - `pendingRemovals` counter prevents limit violation during rapid-fire calls
- **DEBUG lifecycle logging** - 7 log points tracking container, display, and removal (DEBUG mode only)
- **Batch aggregation** - `createBatchToast()` groups multiple order events by type
- **Null-safety** - Defensive checks for DOM containers and parent nodes

## Implementation Details

### Core Files
- **Toast Core**: `web_server/app/static/js/toast.js` (Lines 1-172)
- **Toast Integration**: `web_server/app/static/js/positions/realtime-openorders.js` (Lines 46-48, 1018-1229)
- **CSS Styles**: `web_server/app/static/css/components.css` (Lines 1140-1238)

### Configuration Constants
```javascript
// @FEAT:toast-system @COMP:config @TYPE:config
const MAX_TOASTS = 10;                    // Maximum concurrent toasts per RFC (2 toasts/sec × 5 sec window)
const TOAST_FADE_DURATION_MS = 300;       // Animation duration, must match CSS
```

**Location**: `web_server/app/static/js/positions/realtime-openorders.js` (Lines 47-48)

### Global showToast() Function
```javascript
// @FEAT:toast-system @COMP:util @TYPE:core
function showToast(message, type = 'info', duration = 5000)
```

**Location**: `web_server/app/static/js/toast.js` (Lines 82-168)

**Parameters**:
- `message`: Toast content (truncated to 100 chars in logs)
- `type`: 'success', 'info', 'warning', 'error'
- `duration`: Auto-removal delay in ms (0 = no auto-removal)

**Features**:
- Creates dynamic toast container if missing
- Enforces MAX_TOASTS limit via FIFO queue
- Race condition protection: `pendingRemovals` counter prevents violation during rapid-fire calls
- Close button support
- 300ms fade-out animation (slide-out)
- Auto-removal with configurable timeout
- DEBUG logging at 7 points (container, trigger, display, removal)

**DEBUG Log Points** (Line 14-22):
1-3: Container management (creation/existence checks)
4-5: Toast display (trigger, completion with elapsed time)
6-7: Toast removal (start, completion with remaining count)

### CSS Animations
```css
/* Slide-in animation (entry) */
.toast.slide-in {
    animation: slideInRight 0.3s ease-out;
}

/* Slide-out animation (exit) */
.toast.slide-out {
    animation: slideOutRight 0.3s ease-out;
    opacity: 0;
}

/* @FEAT:toast-system FIFO Queue: Fade-out for oldest removal */
.toast.fade-out {
    opacity: 0;
    transform: translateX(100%);
    transition: opacity 300ms ease-out, transform 300ms ease-out;
}
```

**Location**: `web_server/app/static/css/components.css` (Lines 1156-1238)

**Critical**: CSS `transition: 300ms` MUST match `TOAST_FADE_DURATION_MS = 300`. Mismatch causes animation/removal timing issues (animation finishes before or after removal).

## Queue Management

### _removeFIFOToast() in RealtimeOpenOrdersManager
```javascript
// @FEAT:toast-system @COMP:service @TYPE:helper
_removeFIFOToast() {
    // Remove oldest toast when MAX_TOASTS exceeded
    // Phase 2: Batch processing integration (Lines 1018-1053)
}
```

**Location**: `web_server/app/static/js/positions/realtime-openorders.js` (Lines 1018-1053)

**Features**:
1. Checks container existence (null-safe)
2. Validates `currentToasts >= MAX_TOASTS` before removal
3. Safely adds `fade-out` class (checks `parentNode`)
4. Deferred removal: `setTimeout(..., TOAST_FADE_DURATION_MS)` allows animation to complete
5. DEBUG logging at 3 points:
   - `Toast-FIFO` Checking FIFO removal (currentCount, maxToasts, needsRemoval)
   - `Toast-FIFO` Removing oldest toast (toastType)
   - `Toast-FIFO` FIFO removal complete (remaining count)

**Race Condition Prevention** (toast.js Lines 94-113):
- `pendingRemovals` counter tracks scheduled (but not yet executed) removals in toast.js
- Incremented before FIFO removal starts, decremented after immediate DOM removal completes
- Formula: `if (currentCount + pendingRemovals >= MAX_TOASTS)` prevents violation
- Example: If 9 toasts exist and 2 removals pending, prevents 11th toast creation
- Note: Separate from realtime-openorders.js FIFO removal (uses `fade-out` animation + setTimeout)

## Batch Aggregation

### createBatchToast()
```javascript
// @FEAT:toast-system @COMP:service @TYPE:integration
createBatchToast(summaries) {
    // Aggregates order events by type (LIMIT, STOP_LIMIT, etc.)
    // Creates separate toast per order type
}
```

**Location**: `web_server/app/static/js/positions/realtime-openorders.js` (Lines 1172-1229)

**Parameters**:
- `summaries`: Array of `{order_type, created, cancelled}` format (legacy structure, currently used)

**Features**:
- Aggregates events by `${order_type}_${action}` key (internal optimization)
- Creates separate toast per order type based on `summaries` array
- Toast type: 'warning' if `cancelled > 0`, else 'info'
- Calls `_removeFIFOToast()` before each toast to enforce MAX_TOASTS limit
- Each toast displays for 3 seconds with 📦 emoji prefix
- DEBUG logging at 2 points:
  - `Toast-Batch` Batch aggregation started (summaryCount, uniqueTypes)
  - `Toast-Batch` Individual toast created (orderType, message, toastType)

**Message Format**:
```
📦 LIMIT 주문 생성 5건, 취소 3건
📦 STOP_LIMIT 주문 생성 2건
```

**Example Usage**:
```javascript
manager.createBatchToast([
    {order_type: 'LIMIT', created: 5, cancelled: 3},
    {order_type: 'STOP_LIMIT', created: 2, cancelled: 0}
]);
// Output: 2 toasts ("📦 LIMIT..." and "📦 STOP_LIMIT..."), each 3sec duration
```

## Search Patterns

```bash
# Find all toast system code
grep -r "@FEAT:toast-system" --include="*.js" --include="*.css"

# Find core configuration
grep -n "MAX_TOASTS\|TOAST_FADE_DURATION_MS" web_server/app/static/js/positions/realtime-openorders.js

# Find FIFO removal
grep -n "_removeFIFOToast\|pendingRemovals" web_server/app/static/js/toast.js

# Find batch function
grep -n "createBatchToast" web_server/app/static/js/positions/realtime-openorders.js
```

## Known Issues

### CSS-JS Duration Mismatch Risk
**Issue**: If `TOAST_FADE_DURATION_MS` (300ms) doesn't match CSS `transition: 300ms`, animation and removal get out of sync. Toast may disappear before animation completes or vice versa.

**Locations**:
- JS constant: `web_server/app/static/js/positions/realtime-openorders.js:48`
- CSS transition: `web_server/app/static/css/components.css:1237`
- Referenced in: `toast.js:148` (removeToast timeout), `realtime-openorders.js:1050` (FIFO removal timeout)

**Prevention**: Always update both JS and CSS together. Verify in DevTools: `Inspect Element → Animations tab → Check fade-out duration matches 300ms`.

## Debugging Guide

### DEBUG Mode Activation
```javascript
// URL parameter
https://yoursite.com/positions?debug=true

// Or console
enableDebugMode();
showToast('Test', 'info', 2000);
```

### Expected Log Output (12 total points)
**Phase 1 (toast.js - 7 logs)**:
```
🔍 Toast Container creation/existence check
🔍 Toast Toast triggered { type: 'info', duration: 2000, message: 'Test' }
🔍 Toast Toast displayed { type: 'info', count: 1, elapsed: '1.23ms' }
🔍 Toast Removing toast { type: 'info' }
🔍 Toast Toast removed { type: 'info', remaining: 0 }
```

**Phase 2 (realtime-openorders.js - 5 logs)**:
```
🔍 Toast-Batch Batch aggregation started { summaryCount: 3, uniqueTypes: 2 }
🔍 Toast-FIFO Checking FIFO removal { currentCount: 5, maxToasts: 10, needsRemoval: false }
🔍 Toast-FIFO Removing oldest toast { toastType: 'info' }
🔍 Toast-Batch Individual toast created { orderType: 'LIMIT', message: '...', toastType: 'info' }
🔍 Toast-FIFO FIFO removal complete { remaining: 4 }
```

### Performance Metrics
- **Memory**: O(1) - Maximum 10 DOM elements
- **Animation**: 300ms GPU-accelerated (transform + opacity)
- **FIFO Removal**: O(1) - Always removes `firstChild`
- **Batch Aggregation**: O(n) where n = unique order types

## Error Handling

### Toast Container Not Found
- **Fallback**: `ensureToastContainer()` dynamically creates `#toast-container` in `body`
- **Logger**: Warns in toast.js, skips in realtime-openorders.js
- **Safety**: Always null-checks `oldestToast.parentNode` before removal

### Logger Not Loaded
- **Fallback**: toast.js (Lines 33-38) provides no-op functions
- **Result**: Zero production impact if `logger.js` not loaded
- **Safety**: All DEBUG calls handled gracefully

### Rapid-Fire Toast Creation
- **Protection**: `pendingRemovals` counter in toast.js
- **Example**: 9 toasts + 2 pending removals = prevents 11th creation
- **Formula**: `if (currentCount + pendingRemovals >= MAX_TOASTS)` before adding

## Testing

### Manual Smoke Test
```javascript
// Test 1: FIFO limit (browser console)
for (let i = 0; i < 15; i++) {
    showToast(`Toast #${i}`, 'info', 1000);
}
// Expected: Only 10 visible, oldest 5 fade out progressively

// Test 2: Batch toast
manager = getRealtimeOpenOrdersManager();
manager.createBatchToast([
    {order_type: 'LIMIT', action: 'created', count: 3},
    {order_type: 'LIMIT', action: 'cancelled', count: 1},
    {order_type: 'MARKET', action: 'created', count: 2}
]);
// Expected: 2 toasts ("📦 LIMIT..." and "📦 MARKET..."), each 3sec duration
```

## Dependencies

- **toast.js**: `logger.js` (optional - degrades gracefully)
- **realtime-openorders.js**: `toast.js`, `logger.js`, `realtime-core.js`
- **components.css**: No external dependencies

## Additional Toast Features

### Toast Close Button (Click Handler)
**Location**: `web_server/app/static/js/toast.js` (Lines 131-149)

- Close button removes toast with slide-out animation
- Custom `removeToast()` function handles both close-button and auto-removal
- 300ms slide-out animation before DOM removal
- Null-safe removal via `toast.parentNode` check

### Toast Auto-Removal
- Configurable duration via `showToast(message, type, duration)` parameter
- Duration in milliseconds (0 = no auto-removal)
- Uses `setTimeout` for deferred removal after animation completes
- Default auto-remove delays: 5000ms (basic), 3000ms (batch), 2000ms (handler calls)

### Toast Security
**Location**: `web_server/app/static/js/toast.js` (Lines 117-119)

- HTML content from server-controlled SSE only (not user input)
- innerHTML used safely: Server validates message in `core.py` before SSE emit
- Message directly interpolated into toast HTML via `innerHTML`

---

**Last Updated**: 2025-10-30
**Status**: ✅ Production Ready
**Document Size**: ~385 lines
