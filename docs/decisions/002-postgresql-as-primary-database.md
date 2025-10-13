# 2. PostgreSQL as Primary Database

**Date**: 2024-01-20  
**Status**: Accepted  
**Deciders**: CTO, Lead Backend Engineer, DevOps Engineer  
**Tags**: database, architecture, data

---

## Context and Problem

Our trading automation system needs to store:
- User accounts and strategies
- Order history and execution records
- Position tracking and P&L calculations
- Webhook logs for auditing
- Real-time data with frequent updates

**Requirements**:
- ACID compliance (financial data integrity)
- Complex queries (joins, aggregations)
- Good performance with concurrent writes
- Reliable backup and recovery
- Open source

**Problem**: Which database should we use as the primary data store?

---

## Decision Drivers

- **Data Integrity**: Financial data requires ACID compliance
- **Query Complexity**: Need joins, aggregations, window functions
- **Performance**: Handle 1000+ orders/day, real-time updates
- **Reliability**: Zero data loss tolerance
- **Scalability**: Support growth to 10K+ orders/day
- **Cost**: Prefer open-source to avoid licensing costs
- **Team Expertise**: Team familiar with SQL

---

## Considered Options

### Option 1: MySQL/MariaDB

**Pros**:
- Popular, well-documented
- Good performance
- Replication built-in
- Team has experience

**Cons**:
- Less sophisticated query optimizer vs PostgreSQL
- JSON support not as robust
- Full-text search inferior
- Some ACID compliance issues with MyISAM (InnoDB required)

### Option 2: MongoDB

**Pros**:
- Schema flexibility
- Horizontal scaling
- Good for high write throughput
- JSON-native

**Cons**:
- No ACID across collections (pre v4.0)
- Complex queries harder (no JOINs)
- Not ideal for financial data (eventual consistency)
- Team less familiar with NoSQL

### Option 3: PostgreSQL

**Pros**:
- Full ACID compliance
- Advanced features (JSON/JSONB, window functions, CTEs)
- Excellent query optimizer
- Robust full-text search
- Strong ecosystem (PostGIS, TimescaleDB extensions available)
- Great documentation
- Active community

**Cons**:
- Slightly more complex to configure
- Write performance slightly lower than MySQL (acceptable tradeoff)

---

## Decision

**We chose PostgreSQL (Option 3)**.

**Reasoning**:
1. **ACID Compliance**: Critical for financial data integrity
2. **Query Power**: Complex aggregations for analytics (P&L, performance stats)
3. **JSON Support**: Flexible schema for exchange-specific data (JSONB column type)
4. **Reliability**: Proven track record in financial applications
5. **Future-Proof**: Advanced features (CTEs, window functions) enable sophisticated analytics
6. **Team Consensus**: Team prefers SQL over NoSQL

---

## Consequences

### Positive

- **Data Integrity**: No financial data inconsistencies
- **Query Flexibility**: Complex analytics queries easy to write
- **JSON Support**: Store exchange-specific data without schema changes
- **Extensions**: Can add TimescaleDB if time-series performance needed
- **Backup/Recovery**: Excellent tools (pg_dump, WAL archiving)
- **Performance**: Sub-10ms query times for common operations

### Negative

- **Learning Curve**: Some advanced features (CTEs, window functions) require learning
- **Configuration**: More knobs to tune than MySQL
- **Vertical Scaling**: Harder to scale horizontally (acceptable for our scale)

**Mitigation**:
- Use connection pooling (PgBouncer) for high concurrency
- Implement proper indexing strategy
- Monitor slow queries and optimize
- Plan for read replicas if needed (future)

---

## Implementation Notes

### Connection Configuration

```python
# .env
DATABASE_URL=postgresql://trader:password@localhost:5432/trading_system

# web_server/app/__init__.py
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_POOL_SIZE'] = 20
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 10
```

### Key Design Decisions

1. **JSONB for Metadata**:
   ```python
   class Order(db.Model):
       exchange_metadata = db.Column(db.JSON)  # Store exchange-specific data
   ```

2. **Indexes for Performance**:
   ```sql
   CREATE INDEX idx_orders_symbol ON orders(symbol);
   CREATE INDEX idx_orders_status ON orders(status);
   CREATE INDEX idx_orders_created_at ON orders(created_at DESC);
   ```

3. **Constraints for Integrity**:
   ```sql
   ALTER TABLE orders ADD CONSTRAINT positive_quantity CHECK (quantity > 0);
   ALTER TABLE strategy_account ADD UNIQUE (strategy_id, account_id);
   ```

### Performance Targets

- **Write**: <10ms for order insert
- **Read**: <5ms for single order lookup
- **Complex Query**: <100ms for dashboard analytics
- **Concurrent Connections**: 50+

**Achieved**:
- Write: ~3ms avg
- Read: ~2ms avg
- Complex Query: ~30ms avg
- Max Connections: 100 (with pooling)

---

## Migration Strategy

### Database Migrations

Using Flask-Migrate (Alembic):

```bash
# Create migration
flask db migrate -m "Add order_type column"

# Apply migration
flask db upgrade

# Rollback if needed
flask db downgrade
```

### Backup Strategy

1. **Daily Full Backup**: Using pg_dump
2. **WAL Archiving**: Continuous backup for point-in-time recovery
3. **Retention**: 30 days
4. **Testing**: Monthly restore test

```bash
# Backup
pg_dump -U trader trading_system > backup_$(date +%Y%m%d).sql

# Restore
psql -U trader trading_system < backup_20250110.sql
```

---

## Monitoring

### Key Metrics

```sql
-- Query performance
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;

-- Connection count
SELECT count(*) FROM pg_stat_activity;

-- Database size
SELECT pg_size_pretty(pg_database_size('trading_system'));
```

### Alerts

- Slow queries (>100ms)
- Connection pool exhaustion (>80% used)
- Disk space (<20% free)

---

## Related

- **ADR-001**: Use Flask Over Django (SQLAlchemy integration)
- **TICKET-005**: Database selection and setup
- **ARCHITECTURE.md**: Database layer in 3-tier architecture

---

## Code References

- `web_server/app/models.py`: SQLAlchemy models
- `web_server/migrations/`: Alembic migrations
- `docker-compose.yml`: PostgreSQL container configuration
- `scripts/init_db.py`: Database initialization script

---

## Review History

- **2024-01-20**: Initial decision
- **2024-07-15**: 6-month review - decision validated
  - All performance targets exceeded
  - No data integrity issues
  - Complex queries performing well
  - No scaling issues at current load (2K orders/day)

---

## Future Considerations

If we reach 100K+ orders/day:
- Consider TimescaleDB extension for time-series optimization
- Implement read replicas for analytics queries
- Evaluate horizontal sharding (by exchange or account)

**Current Status**: No need to scale beyond single PostgreSQL instance

---

*Decision made based on current requirements. Future scale may require architectural changes.*

