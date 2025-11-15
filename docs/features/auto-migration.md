# Auto Migration System

> 📌 **Quick Navigation**: [System Overview](#system-overview) | [Writing Migrations](#writing-migrations) | [Template](#migration-template) | [Common Mistakes](#common-mistakes)

자동 마이그레이션 시스템은 `python run.py start/restart` 실행 시 미실행 마이그레이션을 자동으로 감지하고 실행합니다.

---

## System Overview

### 작동 원리

```
python run.py start/restart
    ↓
1. PostgreSQL 컨테이너 시작
    ↓
2. schema_migrations 테이블 확인/생성
    ↓
3. 실행된 마이그레이션 목록 조회
    ↓
4. web_server/migrations/ 디렉토리 스캔
    ↓
5. 미실행 마이그레이션 감지 (날짜순 정렬)
    ↓
6. 순차 실행 (upgrade 함수 호출)
    ↓
7. 실행 이력 자동 기록
    ↓
8. Flask 앱 시작
```

### 핵심 구성 요소

**1. MigrationHelper** (`cli/helpers/migration.py`)
- 마이그레이션 파일 스캔 및 실행
- schema_migrations 테이블 관리
- SQLAlchemy engine을 통한 실행

**2. schema_migrations 테이블**
```sql
CREATE TABLE schema_migrations (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(255) UNIQUE NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**3. 마이그레이션 디렉토리**
- 위치: `web_server/migrations/`
- 패턴: `{YYYYMMDD}_{description}.py`

---

## Writing Migrations

### ⚠️ 필수 규칙

#### 1. SQLAlchemy 패턴 사용 (필수)

**✅ 올바른 패턴:**
```python
from sqlalchemy import text

def upgrade(engine):
    """Apply migration"""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("ALTER TABLE ..."))
            trans.commit()
        except Exception as e:
            trans.rollback()
            raise

def downgrade(engine):
    """Rollback migration"""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("ALTER TABLE ..."))
            trans.commit()
        except Exception as e:
            trans.rollback()
            raise
```

**❌ 잘못된 패턴 (psycopg2):**
```python
import psycopg2

def upgrade(conn):  # ❌ psycopg2 connection
    cursor = conn.cursor()
    cursor.execute("...")
    conn.commit()
```

**이유:**
- 자동 마이그레이션 시스템은 SQLAlchemy engine을 전달
- psycopg2 connection은 호환되지 않음

#### 2. 필수 함수 시그니처

```python
def upgrade(engine):   # ✅ engine 파라미터 (필수)
def downgrade(engine): # ✅ engine 파라미터 (필수)
```

**파라미터 이름 확인:**
- ✅ `engine` (권장)
- ❌ `conn` (psycopg2 connection과 혼동)
- ❌ `connection` (SQLAlchemy connection과 혼동)

#### 3. text() 사용

**✅ 올바른 SQL 실행:**
```python
from sqlalchemy import text

conn.execute(text("""
    ALTER TABLE open_orders
    ADD COLUMN error_message TEXT;
"""))
```

**❌ 잘못된 방식:**
```python
conn.execute("""
    ALTER TABLE open_orders
    ADD COLUMN error_message TEXT;
""")  # ❌ text() 없음 (SQLAlchemy 2.0+에서 오류)
```

#### 4. Idempotent 설계

**마이그레이션은 재실행 가능해야 함:**

```python
# ✅ Idempotent 패턴
conn.execute(text("""
    ALTER TABLE open_orders
    ADD COLUMN IF NOT EXISTS error_message TEXT;
"""))

conn.execute(text("""
    CREATE INDEX IF NOT EXISTS idx_name
    ON table_name(column);
"""))

# 컬럼 존재 확인
result = conn.execute(text("""
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_name = 'open_orders'
    AND column_name = 'error_message'
"""))
if result.scalar() > 0:
    print("✅ Column already exists, skipping")
    return
```

#### 5. 트랜잭션 관리

**✅ 명시적 트랜잭션:**
```python
def upgrade(engine):
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # 모든 DDL 작업
            conn.execute(text("..."))
            conn.execute(text("..."))

            trans.commit()  # ✅ 명시적 커밋
        except Exception as e:
            trans.rollback()  # ✅ 명시적 롤백
            raise
```

---

## Migration Template

### 기본 템플릿

```python
#!/usr/bin/env python3
"""
Migration: {마이그레이션 설명}
Date: {YYYY-MM-DD}
Purpose: {목적 설명}

Feature: {feature-name}
Phase: {phase-number} - {phase-description}

Changes:
- {변경 사항 1}
- {변경 사항 2}

Usage:
    # 자동 실행 (python run.py start/restart)
    # 수동 실행
    python migrations/{filename}.py --upgrade
    python migrations/{filename}.py --downgrade
"""
# @FEAT:{feature-name} @COMP:migration @TYPE:core

from sqlalchemy import text


def upgrade(engine):
    """Apply migration"""
    with engine.connect() as conn:
        trans = conn.begin()

        try:
            print("🔧 Starting migration: {마이그레이션 설명}...")

            # 1. 변경 사항 1
            print("  → {작업 설명}...")
            conn.execute(text("""
                -- SQL 명령어
            """))

            # 2. 검증
            result = conn.execute(text("""
                -- 검증 쿼리
            """))
            if result.fetchone():
                print("  ✅ Verified")
            else:
                raise Exception("Verification failed")

            trans.commit()
            print("✅ Migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


def downgrade(engine):
    """Rollback migration"""
    with engine.connect() as conn:
        trans = conn.begin()

        try:
            print("🔄 Rolling back migration...")

            # 안전성 확인 (선택)
            result = conn.execute(text("""
                -- 데이터 존재 여부 확인
            """))
            count = result.scalar()
            if count > 0:
                print(f"⚠️  WARNING: {count} records will be affected")

            # Rollback 작업
            conn.execute(text("""
                -- 되돌리기 SQL
            """))

            trans.commit()
            print("✅ Rollback completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ Rollback failed: {e}")
            raise


# 독립 실행 지원 (수동 실행용)
if __name__ == '__main__':
    import sys
    import os
    from dotenv import load_dotenv
    from sqlalchemy import create_engine

    if len(sys.argv) < 2:
        print("Usage: python {filename}.py [--upgrade|--downgrade]")
        sys.exit(1)

    action = sys.argv[1]

    if action not in ['--upgrade', '--downgrade']:
        print(f"Invalid action: {action}")
        print("Usage: python {filename}.py [--upgrade|--downgrade]")
        sys.exit(1)

    try:
        # 환경 변수 로드
        load_dotenv()

        # SQLAlchemy 엔진 생성
        database_url = (
            f"postgresql://{os.getenv('DB_USER', 'trader')}:"
            f"{os.getenv('DB_PASSWORD', 'password123')}@"
            f"{os.getenv('DB_HOST', 'localhost')}:"
            f"{os.getenv('DB_PORT', '5432')}/"
            f"{os.getenv('DB_NAME', 'trading_system')}"
        )

        engine = create_engine(database_url)

        if action == '--upgrade':
            upgrade(engine)
        else:
            downgrade(engine)

        engine.dispose()

    except Exception as e:
        print(f"❌ Migration script failed: {e}")
        sys.exit(1)
```

---

## Common Mistakes

### 1. psycopg2 패턴 사용 ❌

**문제:**
```python
import psycopg2

def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("...")
```

**해결:**
```python
from sqlalchemy import text

def upgrade(engine):
    with engine.connect() as conn:
        conn.execute(text("..."))
```

### 2. text() 누락 ❌

**문제:**
```python
conn.execute("ALTER TABLE ...")  # ❌
```

**해결:**
```python
conn.execute(text("ALTER TABLE ..."))  # ✅
```

### 3. 잘못된 파라미터 이름 ❌

**문제:**
```python
def upgrade(conn):  # ❌ connection으로 오해
def upgrade(connection):  # ❌ SQLAlchemy connection과 혼동
```

**해결:**
```python
def upgrade(engine):  # ✅ 명확함
```

### 4. 트랜잭션 누락 ❌

**문제:**
```python
def upgrade(engine):
    with engine.connect() as conn:
        conn.execute(text("..."))
        # ❌ commit/rollback 없음
```

**해결:**
```python
def upgrade(engine):
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("..."))
            trans.commit()  # ✅
        except:
            trans.rollback()  # ✅
            raise
```

### 5. Non-Idempotent 설계 ❌

**문제:**
```python
conn.execute(text("""
    ALTER TABLE open_orders
    ADD COLUMN error_message TEXT;
"""))  # ❌ 재실행 시 오류
```

**해결:**
```python
conn.execute(text("""
    ALTER TABLE open_orders
    ADD COLUMN IF NOT EXISTS error_message TEXT;
"""))  # ✅ 재실행 안전
```

---

## Compatibility Checklist

### 마이그레이션 작성 후 체크리스트

- [ ] `from sqlalchemy import text` import 확인
- [ ] `def upgrade(engine):` 시그니처 확인
- [ ] `def downgrade(engine):` 시그니처 확인
- [ ] `with engine.connect() as conn:` 패턴 사용
- [ ] `trans = conn.begin()` 트랜잭션 시작
- [ ] `conn.execute(text("..."))` text() 사용
- [ ] `trans.commit()` 명시적 커밋
- [ ] `trans.rollback()` 예외 처리
- [ ] `IF NOT EXISTS` / `IF EXISTS` Idempotent 설계
- [ ] `__main__` 블록 SQLAlchemy 패턴 사용

### 자동 마이그레이션 호환성 테스트

```bash
# 1. 자동 마이그레이션 실행
python run.py restart

# 2. 로그 확인
grep "마이그레이션" logs/*.log

# 3. schema_migrations 테이블 확인
docker exec webserver-postgres-1 psql -U trader -d trading_system -c "SELECT * FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;"

# 4. 재실행 테스트 (Idempotent 확인)
python run.py restart  # 오류 없이 스킵되어야 함
```

---

## Troubleshooting

### 문제 1: "upgrade() takes 0 positional arguments but 1 was given"

**원인:**
```python
def upgrade():  # ❌ engine 파라미터 누락
```

**해결:**
```python
def upgrade(engine):  # ✅
```

### 문제 2: "Object of type 'TextClause' is not callable"

**원인:**
```python
conn.execute("ALTER TABLE ...")  # ❌ text() 누락
```

**해결:**
```python
from sqlalchemy import text
conn.execute(text("ALTER TABLE ..."))  # ✅
```

### 문제 3: "This Connection is closed"

**원인:**
```python
conn = engine.connect()
conn.execute(...)  # ❌ context manager 없음
```

**해결:**
```python
with engine.connect() as conn:  # ✅
    conn.execute(...)
```

### 문제 4: 마이그레이션이 자동 실행되지 않음

**확인 사항:**
1. 파일명이 `{YYYYMMDD}_{description}.py` 패턴인가?
2. `web_server/migrations/` 디렉토리에 있는가?
3. `upgrade(engine)` 함수가 정의되어 있는가?
4. schema_migrations 테이블에 이미 기록되어 있지 않은가?

```bash
# schema_migrations 확인
docker exec webserver-postgres-1 psql -U trader -d trading_system -c "SELECT migration_name FROM schema_migrations;"
```

---

## Related Documentation

- [Database Migrations History](MIGRATIONS.md) - 전체 마이그레이션 이력
- [MigrationHelper Source](../../cli/helpers/migration.py) - 자동 마이그레이션 시스템 구현

---

*Last Updated: 2025-10-31*
*Purpose: 자동 마이그레이션 시스템 사용 가이드 및 SQLAlchemy 패턴 필수 규칙*
