# Race Condition Integration Tests

**Purpose**: Validate Phase 1 (Trade UNIQUE constraint) and Phase 2 (Position row-level locking) effectiveness against concurrent WebSocket and Scheduler processing.

**Issue**: #38 - Trade Race Condition Fix

---

## Test Scenarios

### Scenario 1: Concurrent Trade Creation
**Validates**: Phase 1 (Trade UNIQUE constraint)

**Test**: WebSocket and Scheduler process same order simultaneously
**Expected**: Only 1 Trade record created, UNIQUE constraint prevents duplicate
**File**: `test_race_conditions.py::test_concurrent_trade_creation_no_duplicates`

---

### Scenario 2: Concurrent Position Updates
**Validates**: Phase 2 (Position row-level locking)

**Test**: Two concurrent trades update same Position
**Expected**: Final quantity reflects both trades (no lost update) OR one skipped gracefully
**File**: `test_race_conditions.py::test_concurrent_position_updates_correct_quantity`

---

### Scenario 3: Realistic LIMIT Order Fill
**Validates**: Phase 1 + Phase 2 (End-to-End)

**Test**: LIMIT order filled, processed by both WebSocket and Scheduler
**Expected**: 1 Trade, correct Position quantity, no errors
**File**: `test_race_conditions.py::test_websocket_scheduler_realistic_scenario`

---

### Scenario 4: Stress Test (100 runs)
**Validates**: No flakiness, consistent behavior

**Test**: Run concurrent trade creation 100 times
**Expected**: 100/100 passes, always 1 Trade per order
**File**: `test_race_conditions.py::test_stress_100_consecutive_runs`

---

### Scenario 5: High Contention (10 threads)
**Validates**: Lock skip behavior (skip_locked=True)

**Test**: 10 threads update same Position simultaneously
**Expected**: No double-counting, some threads skip gracefully
**File**: `test_race_conditions.py::test_high_contention_position_updates`

---

### Scenario 6: Same Exchange Different Symbols
**Validates**: Symbol-specific locking (no interference)

**Test**: Simultaneous ETH and BTC liquidation on same exchange
**Expected**: Both positions closed successfully, no lock conflicts
**File**: `test_race_conditions.py::test_same_exchange_different_symbols`

---

## Running Tests

### Run All Tests
```bash
cd .test
pytest integration/test_race_conditions.py -v
```

### Run Specific Scenario
```bash
pytest integration/test_race_conditions.py::test_concurrent_trade_creation_no_duplicates -v
```

### Run Stress Test (100 iterations)
```bash
pytest integration/test_race_conditions.py::test_stress_100_consecutive_runs -v
```

### Run with Output
```bash
pytest integration/test_race_conditions.py -v -s
```

---

## Expected Results

**All tests should PASS consistently (no flakiness).**

### Success Indicators
- ✅ Only 1 Trade record per order_id (UNIQUE constraint working)
- ✅ Position quantities accurate (no lost updates)
- ✅ Some threads may skip (lock contention handled gracefully)
- ✅ No crashes from IntegrityError or lock failures
- ✅ 100/100 stress test passes

### Failure Indicators
- ❌ Duplicate Trade records found (UNIQUE constraint failed)
- ❌ Position quantity mismatch (lost update occurred)
- ❌ Test crashes with IntegrityError (error handling missing)
- ❌ Stress test failures (flaky behavior, timing issues)

---

## Test Database

**Type**: SQLite in-memory (`:memory:`)
**Isolation**: Each test gets fresh database
**Speed**: Fast execution (~1-2 seconds per scenario)

**Note**: SQLite in-memory provides isolation and speed. Real PostgreSQL behavior is validated separately in Phase 4.3 (validate_pg_locks.py).

---

## Tags

- `@FEAT:order-tracking` - Order lifecycle management
- `@FEAT:position-tracking` - Position updates
- `@COMP:test` - Test infrastructure
- `@TYPE:integration` - Integration testing
- `@ISSUE:38` - Race condition fix

---

*Last Updated: 2025-11-07*
*Phase 4.1: Integration Test Suite Creation*
