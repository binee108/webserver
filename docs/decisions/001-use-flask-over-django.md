# 1. Use Flask Over Django

**Date**: 2024-01-15  
**Status**: Accepted  
**Deciders**: CTO, Lead Backend Engineer  
**Tags**: architecture, framework, web

---

## Context and Problem

We need to build a trading automation system that receives webhooks from TradingView and executes orders on multiple exchanges. The system requires:

- RESTful API endpoints for webhooks and dashboard
- Real-time updates via Server-Sent Events (SSE)
- Background task scheduling
- Integration with multiple exchange APIs
- Minimal overhead for maximum performance

**Problem**: Which Python web framework should we use?

---

## Decision Drivers

- **Performance**: Low latency for webhook processing (<100ms)
- **Flexibility**: Need custom architecture, not opinionated framework
- **Simplicity**: Small team, need to move fast
- **Learning Curve**: Team already familiar with Flask
- **Library Ecosystem**: Good integration with APScheduler, SQLAlchemy, ccxt

---

## Considered Options

### Option 1: Django

**Pros**:
- Batteries included (admin panel, ORM, auth)
- Large ecosystem
- Built-in security features

**Cons**:
- Heavier framework (slower startup, higher memory)
- Opinionated structure (harder to customize)
- Django ORM less flexible than SQLAlchemy
- Overkill for our use case (we don't need Django Admin)

### Option 2: FastAPI

**Pros**:
- Modern async support
- Automatic OpenAPI docs
- High performance
- Type hints validation

**Cons**:
- Team not familiar with async/await patterns
- More complex for background tasks
- Less mature ecosystem (released 2018)
- Overkill for our sync-heavy workload

### Option 3: Flask

**Pros**:
- Lightweight and fast
- Flexible - build exactly what we need
- Team already experienced
- Excellent integration with SQLAlchemy
- Simple to add APScheduler for background jobs
- Large ecosystem of extensions

**Cons**:
- No built-in admin panel (not needed for our case)
- Less "batteries included" (need to choose components)

---

## Decision

**We chose Flask (Option 3)**.

**Reasoning**:
1. **Performance**: Lightweight, minimal overhead for webhook processing
2. **Flexibility**: We need custom architecture (3-layer service model), not Django's MVT
3. **Team Familiarity**: Faster development with known framework
4. **Simplicity**: Don't need Django's admin panel or extra features
5. **Integration**: Works seamlessly with our tech stack (SQLAlchemy, APScheduler, ccxt)

---

## Consequences

### Positive

- **Fast Development**: Team productive immediately
- **Low Overhead**: Minimal framework overhead, fast webhook response
- **Flexibility**: Easy to implement custom patterns (Service Layer, Repository)
- **Lightweight**: Lower memory usage, easier to deploy
- **Control**: Full control over routing, middleware, error handling

### Negative

- **More Setup**: Need to manually configure components (migrations, extensions)
- **No Admin Panel**: Would need to build custom admin UI
- **Less "Magic"**: More boilerplate code vs Django
- **Security**: Need to manually implement some security features

**Mitigation**:
- Use Flask-Migrate for database migrations
- Build minimal admin UI only for essential features
- Follow Flask security best practices
- Use well-tested extensions (Flask-Login, Flask-CORS)

---

## Implementation Notes

### Key Components

1. **Flask App Factory**: `web_server/app/__init__.py`
   - Creates Flask app with configuration
   - Registers blueprints (routes)
   - Initializes extensions (SQLAlchemy, APScheduler)

2. **SQLAlchemy ORM**: `web_server/app/models.py`
   - Preferred over Django ORM for flexibility
   - Better support for complex queries

3. **APScheduler**: `web_server/app/__init__.py`
   - Background task scheduler
   - Runs order queue rebalancer, fill monitor, etc.

4. **Flask-Migrate**: Database migrations
   - Alembic-based migrations
   - Similar to Django migrations

### Configuration

```python
# web_server/app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
db = SQLAlchemy(app)
scheduler = BackgroundScheduler()
```

### Performance Targets

- Webhook processing: <100ms (achieved: ~50ms avg)
- API response time: <200ms (achieved: ~80ms avg)
- Memory usage: <500MB (achieved: ~250MB)

---

## Related

- **ADR-002**: PostgreSQL as Primary Database
- **TICKET-001**: Initial framework selection
- **ARCHITECTURE.md**: 3-Layer Service Architecture

---

## Code References

- `web_server/app/__init__.py`: Flask app initialization
- `web_server/app/routes/`: API endpoints (blueprints)
- `web_server/app/services/`: Business logic services
- `config/Dockerfile`: Flask deployment configuration

---

## Review History

- **2024-01-15**: Initial decision
- **2024-06-01**: Review after 6 months - decision validated
  - Performance targets met
  - Team velocity high
  - No regrets about Flask choice

---

*Decision made based on project requirements at the time. Future projects may have different needs.*

