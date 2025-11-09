# Race Condition Monitoring Guide

**Purpose**: Detect and monitor race condition defense mechanisms in production
**Issue**: #38 - Trade Race Condition Fix
**Last Updated**: 2025-11-09

---

## Quick Check

Check race condition event frequency:
```bash
grep "RACE_CONDITION_DETECTED" logs/app.log | wc -l
```

---

## Event Types

- **duplicate_trade**: WebSocket/Scheduler race → UNIQUE constraint defense → <10/day normal, >50/day investigate traffic spike
- **position_lock_skip**: Concurrent Position updates → row_lock_skip defense → <5/day normal, >20/day optimize batching

---

## Alerting Thresholds

| Level | Events/24h | Action |
|-------|-----------|--------|
| **Normal** | <10 | Monitor only |
| **Warning** | 50-200 | Investigate patterns |
| **Critical** | >200 | Check bottlenecks |

---

## Common Queries

```bash
# All events (last 24h)
grep "RACE_CONDITION_DETECTED" logs/app.log | wc -l

# By event type
grep "RACE_CONDITION_DETECTED" logs/app.log | awk -F '|' '{print $2}' | sort | uniq -c

# By symbol (pattern analysis)
grep "RACE_CONDITION_DETECTED" logs/app.log | awk -F '|' '{print $4}' | sort | uniq -c | sort -rn
```

---

## Troubleshooting (3 Steps)

1. **Count events**: `grep "RACE_CONDITION_DETECTED" logs/app.log | wc -l`
2. **Identify patterns**: Group by symbol, event type, time of day
3. **Root cause**: High duplicate_trade = processing delays; High position_lock_skip = database contention

## Log Format

Format: `RACE_CONDITION_DETECTED | event=<type> | order_id=<ID> | symbol=<SYM> | side=<S> | quantity=<Q> | price=<P> | strategy_account_id=<ID> | defense=<mechanism> | source=<service>`

Fields (in order): event, order_id, symbol, side, quantity, price, strategy_account_id, defense, source

Event types: `duplicate_trade`, `position_lock_skip` | Defense: `unique_constraint`, `row_lock_skip`

---

**Tags**: @FEAT:race-condition-monitoring @COMP:documentation @TYPE:operations @ISSUE:38
