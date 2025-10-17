# Open Orders Sorting Feature

## Overview
포지션 페이지의 "열린 주문" 테이블에 다단계 정렬 기능을 제공합니다.

## Features

### Phase 1: Default Sorting (✅ Implemented - 2025-10-17)
- 5단계 우선순위 자동 정렬
- 심볼 → 상태 → 주문 타입 → 주문 방향 → 가격 순서

### Phase 2: Column Click Sorting (🚧 Planned)
- 각 컬럼 클릭 시 정렬 방향 토글
- 정렬 상태 UI 표시 (화살표 아이콘)

### Phase 3: Real-time Update Integration (🚧 Planned)
- SSE 업데이트 시 정렬 순서 유지

## Usage

### For Developers

#### Sorting Logic
```javascript
// RealtimeOpenOrdersManager 클래스 사용
const manager = new RealtimeOpenOrdersManager();

// 기본 정렬 (자동 적용)
manager.renderOpenOrders(orders);

// 사용자 정의 정렬 (Phase 2)
manager.handleSort('price');  // 가격 컬럼 클릭
```

#### Sort Priority Configuration
```javascript
// constructor 내부에서 설정 가능:
this.defaultSortOrder = [
    { column: 'symbol', direction: 'desc' },
    { column: 'status', direction: 'desc' },
    { column: 'order_type', direction: 'desc' },
    { column: 'side', direction: 'desc' },
    { column: 'price', direction: 'desc' }
];
```

#### Adding New Sort Columns
1. `compareByColumn()` switch 문에 case 추가:
```javascript
case 'new_column':
    aVal = a.new_column || 0;
    bVal = b.new_column || 0;
    break;
```

2. `defaultSortOrder` 배열에 우선순위 추가:
```javascript
{ column: 'new_column', direction: 'asc' }
```

### For Users
- 페이지 로드 시 자동으로 정렬된 주문 목록 표시
- (Phase 2) 각 컬럼 헤더 클릭 시 정렬 기준 변경 가능

## Technical Details

### Sort Algorithm
- **Engine**: JavaScript native `Array.sort()`
- **Stability**: Stable sort (ES2019+)
- **Time Complexity**: O(n log n)
- **Space Complexity**: O(n) - shallow copy of orders array

### Performance Benchmarks
- **50 orders**: < 10ms
- **100 orders**: < 10ms (measured)
- **200 orders**: < 20ms (estimated)

### Sort Priority Details

| Level | Column | Direction | Priority Rule |
|-------|--------|-----------|---------------|
| 1 | Symbol | desc | Alphabetical order (ETH > BTC) |
| 2 | Status | desc | NEW (1) > PENDING_QUEUE (0) |
| 3 | Order Type | desc | STOP_MARKET (3) > STOP_LIMIT (2) > LIMIT (1) |
| 4 | Side | desc | SELL (1) > BUY (0) |
| 5 | Price | desc | Highest price first |

### Edge Cases Handled
- **Null/undefined values**: Converted to default values (empty string for symbol, 0 for numbers)
- **Identical values**: Next priority level applied
- **Empty array**: Returns empty array
- **Single order**: Returns array with single order
- **Missing order_type**: Defaults to priority 0

## Testing

### Manual Test Scenarios
```bash
# 1. Create multiple orders with different symbols
curl -k -s -X POST https://222.98.151.163/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test1",
    "symbol": "BTC/USDT",
    "order_type": "LIMIT",
    "side": "buy",
    "price": "95000",
    "qty_per": 5,
    "token": "unmCgoDsy1UfUFo9pisGJzstVcIUFU2gb67F87cEYss"
  }'

# 2. Verify sort order on positions page
# Expected: Orders sorted by symbol → status → type → side → price
```

### Test Cases
1. **Basic 5-level sort**: Verify default sort priority
2. **Null handling**: Orders with missing fields display correctly
3. **Stable sort**: Orders with identical values maintain relative order
4. **SSE update**: New orders appear in correct sorted position (Phase 3)

## Maintenance

### Modifying Sort Priority
Edit `defaultSortOrder` array in constructor:
```javascript
this.defaultSortOrder = [
    { column: 'price', direction: 'asc' },  // Changed: price first, ascending
    { column: 'symbol', direction: 'desc' },
    // ...
];
```

### Performance Monitoring
Add logging to `sortOrders()` method:
```javascript
const start = performance.now();
const result = ordersCopy.sort(...);
this.logger.debug(`Sorted ${orders.length} orders in ${(performance.now() - start).toFixed(2)}ms`);
return result;
```

## Architecture

### File Structure
```
web_server/
├── app/static/js/positions/
│   └── realtime-openorders.js  ← Core sorting logic
├── docs/features/
│   └── open_orders_sorting.md  ← This document
└── .plan/
    └── open_orders_sorting_plan.md  ← Implementation plan
```

### Class Diagram
```
RealtimeOpenOrdersManager
├── sortConfig {column, direction}
├── defaultSortOrder []
├── sortOrders(orders, sortConfig)
├── compareByColumn(a, b, column, direction)
├── getStatusPriority(order)
├── getOrderTypePriority(orderType)
└── updateSortIndicators() [Phase 2]
```

## Related Files
- `/web_server/app/static/js/positions/realtime-openorders.js` - Core logic
- `.plan/open_orders_sorting_plan.md` - Implementation plan
- `docs/FEATURE_CATALOG.md` - Feature catalog

## Grep Commands
```bash
# Find all sorting-related code
grep -r "@FEAT:open-orders-sorting" --include="*.js"

# Find core sorting logic only
grep -r "@FEAT:open-orders-sorting" --include="*.js" | grep "@TYPE:core"

# Find all methods in RealtimeOpenOrdersManager
grep -n "^[[:space:]]*[a-zA-Z_][a-zA-Z0-9_]*(" /web_server/app/static/js/positions/realtime-openorders.js
```

## Changelog
- **2025-10-17**: Phase 1 구현 완료 (기본 정렬 로직)
  - `sortOrders()`, `compareByColumn()`, priority helper 메서드 추가
  - 5단계 정렬 우선순위 구현
  - JSDoc 문서화 완료

## Future Enhancements (Phase 2-3)
- [ ] Column-click sorting UI
- [ ] Sort direction toggle
- [ ] Sort indicators (arrow icons)
- [ ] Real-time SSE update integration
- [ ] localStorage persistence of user preferences
- [ ] Performance optimization for 1000+ orders

## Support
For issues or questions, refer to:
- **Plan Document**: `.plan/open_orders_sorting_plan.md`
- **Code Review**: Phase 1.3 review results
- **CLAUDE.md**: Project coding guidelines
