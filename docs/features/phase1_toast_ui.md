# Phase 1: Toast UI Improvement

## Summary

Toast notification management enhancement for the Real-time Open Orders page:
- **Maximum 10 active toasts** - FIFO removal when limit exceeded
- **300ms fade-out animation** - Smooth disappearance with translate effect
- **Batch notification function** - `createBatchToast()` aggregates multiple order events
- **DRY refactoring** - Extracted `_removeFIFOToast()` helper to eliminate code duplication
- **Null-safety improvements** - Defensive checks for DOM container and parent node

## Implementation Details

### Configuration Constants
```javascript
// @FEAT:toast-ui @COMP:config @TYPE:config
const MAX_TOASTS = 10;                    // Maximum concurrent toasts
const TOAST_FADE_DURATION_MS = 300;       // Must match CSS transition duration
```

**Location**: `web_server/app/static/js/positions/realtime-openorders.js` (Lines 24-25)

### CSS Animation
```css
/* Phase 1: Toast UI Improvement - Fade-out animation for FIFO removal */
.toast.fade-out {
    opacity: 0;
    transform: translateX(100%);
    transition: opacity 300ms ease-out, transform 300ms ease-out;
}
```

**Location**: `web_server/app/static/css/components.css` (Lines 1218-1223)

**Critical**: CSS transition duration MUST match `TOAST_FADE_DURATION_MS` constant. Mismatch causes animation/removal timing issues.

## Key Methods

### _removeFIFOToast()
```javascript
// @FEAT:toast-ui @COMP:service @TYPE:helper
_removeFIFOToast() {
    // Remove oldest toast when MAX_TOASTS exceeded
    // Handles: missing container, null toast, already-removed toast (null-safe)
    // Animation: 300ms fade-out before DOM removal
}
```

**Location**: `web_server/app/static/js/positions/realtime-openorders.js` (Lines 946-964)

**Key improvements**:
1. **Extracted to avoid duplication** (Phase 1.2.1)
2. **Null-safe removal**: Checks both `oldestToast` and `oldestToast.parentNode` before removal
3. **Timeout safety**: Uses constant `TOAST_FADE_DURATION_MS` instead of hardcoded value

### createBatchToast()
```javascript
// @FEAT:toast-ui @COMP:service @TYPE:integration
createBatchToast(summaries) {
    // Aggregate multiple order event messages
    // Format: "📦 ORDER_TYPE 주문 생성 X건, 취소 Y건 | ..."
    // Called during batch order processing (Phase 3 integration)
}
```

**Location**: `web_server/app/static/js/positions/realtime-openorders.js` (Lines 1089-1116)

**Parameters**:
- `summaries`: Array of objects with `{order_type, created, cancelled}`

**Example**:
```javascript
manager.createBatchToast([
    {order_type: 'LIMIT', created: 5, cancelled: 3},
    {order_type: 'STOP_LIMIT', created: 2, cancelled: 0}
]);
// Output: "📦 LIMIT 주문 생성 5건, 취소 3건 | STOP_LIMIT 주문 생성 2건"
```

## Search Patterns

```bash
# Find all Toast UI code
grep -r "@FEAT:toast-ui" --include="*.js" --include="*.css"

# Find configuration constants
grep -n "MAX_TOASTS\|TOAST_FADE_DURATION_MS" web_server/app/static/js/positions/realtime-openorders.js

# Find FIFO removal logic
grep -n "_removeFIFOToast" web_server/app/static/js/positions/realtime-openorders.js

# Find batch toast function
grep -n "createBatchToast" web_server/app/static/js/positions/realtime-openorders.js
```

## Known Issues

### CSS-JS Duration Mismatch
**Issue**: If `TOAST_FADE_DURATION_MS` (300ms) doesn't match CSS `transition: 300ms`, toasts disappear before animation completes or animation hangs after removal.

**Location**: Lines 25 (JS) and 1222 (CSS)

**Prevention**: Update both files together. Verify in browser DevTools: `Inspect Element → Animations → Check fade-out duration`.

## Testing

### Manual Test Checklist
1. **Max Toast Test**: Create 15 toasts → Verify only 10 visible → Oldest fades out
2. **Batch Function**: Call `createBatchToast()` with multiple order types → Verify format "📦 TYPE1 ... | TYPE2 ..."
3. **Animation**: Observe fade-out smoothness (should slide right + fade to transparent)
4. **Edge Cases**:
   - Empty array to `createBatchToast()` → No toast created
   - `{created: 0, cancelled: 0}` → No message for that type

### Test Command (Browser Console)
```javascript
// Test 1: Create 15 toasts
for (let i = 0; i < 15; i++) {
    manager.showToast(`Toast #${i}`, 'info');
}
// Expected: 10 visible, oldest 5 fade out one by one

// Test 2: Batch toast
manager.createBatchToast([
    {order_type: 'LIMIT', created: 3, cancelled: 1},
    {order_type: 'MARKET', created: 0, cancelled: 2}
]);
// Expected: "📦 LIMIT 주문 생성 3건, 취소 1건 | MARKET 주문 취소 2건"
```

## Integration Points

### Phase 3 (Planned)
`createBatchToast()` will be called during batch order processing to display aggregated results:
```javascript
// Example (Phase 3)
const results = {LIMIT: {created: 5, cancelled: 2}, MARKET: {created: 1, cancelled: 0}};
manager.createBatchToast(Object.entries(results).map(([type, counts]) => ({
    order_type: type,
    created: counts.created,
    cancelled: counts.cancelled
})));
```

## Performance

- **Memory**: Constant (max 10 toasts)
- **Animation**: 300ms (GPU-accelerated, transform only)
- **FIFO Removal**: O(1) (always removes `firstChild`)
- **Batch Processing**: O(n) where n = number of unique order types

## Dependencies

- **None** - Self-contained within `RealtimeOpenOrdersManager`
- Related: `realtime-core.js` (shared logger/utilities)

---

**Last Updated**: 2025-10-18
**Phase**: 1 (Complete)
**Status**: ✅ Production Ready
**Document Size**: 220 lines (under 500-line limit)
