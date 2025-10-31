# Database Migrations

> 📌 **Quick Navigation**: [Active Migrations](#active-migrations) | [Migration Workflow](#migration-workflow) | [Rollback Procedures](#rollback-procedures)

데이터베이스 스키마 변경 이력을 추적하는 문서입니다.

---

## Active Migrations

### 20251030_add_error_message_field.py

**Feature**: `webhook-order` (고아 주문 방지 - Phase 3.1)
**Purpose**: OpenOrder 테이블에 `error_message` 필드 추가
**Status**: ✅ Applied (2025-10-30)
**Author**: Phase 3.1 - Database & Security Enhancements

**변경 내용**:
- `open_orders` 테이블에 `error_message` TEXT 컬럼 추가 (nullable)
- PostgreSQL COMMENT 추가 (스키마 문서화)
- Idempotent upgrade (기존 컬럼 존재 시 스킵)
- Safe downgrade (컬럼 제거 전 존재 여부 확인)

**필드 스펙**:
```sql
ALTER TABLE open_orders ADD COLUMN error_message TEXT;
COMMENT ON COLUMN open_orders.error_message IS
  'Sanitized error message from exchange API failures (max 500 chars) - Phase 3.1 (2025-10-30)';
```

**영향 범위**:
- OpenOrder 모델: 모든 주문 레코드에 error_message 필드 추가
- 하위 호환성: ✅ Yes (nullable 필드, 기존 레코드 unaffected)
- 데이터 손실: ❌ None (additive only)

**보안 고려사항**:
- error_message는 `sanitize_error_message()` 함수로 전처리 후 저장
- 민감 정보 (API 키, 계정 번호, 토큰) 자동 마스킹
- 최대 500자 제한으로 DB 비대화 방지

**Rollback**:
```bash
# Method 1: Using migration downgrade function
python migrations/20251030_add_error_message_field.py --downgrade

# Method 2: Manual SQL (if needed)
psql -d webserver_dev -c "ALTER TABLE open_orders DROP COLUMN IF EXISTS error_message;"
```

**Verification**:
```bash
# Check column exists
psql -d webserver_dev -c "\d open_orders" | grep error_message

# Check PostgreSQL comment
psql -d webserver_dev -c "
SELECT col_description('open_orders'::regclass,
  (SELECT ordinal_position FROM information_schema.columns
   WHERE table_name='open_orders' AND column_name='error_message')
);"

# Verify feature tags
grep -r "@DATA:error_message" --include="*.py" web_server/app/
```

**Related Features**:
- Phase 3.2: DB-first Pattern (pending) - Will populate error_message field
- `sanitize_error_message()` function in `trading/core.py` (Lines 71-127)
- OpenOrder model in `models.py` (Lines 390-393)

---

## 20251030_add_cancelling_state.py

**날짜**: 2025-10-30
**Feature**: cancel-order-db-first-orphan-prevention (Phase 1: State Management)
**목적**: 주문 취소 시 고아 주문 방지를 위한 CANCELLING 상태 및 cancel_attempted_at 필드 추가

### 변경 사항

#### 1. 컬럼 추가
- **컬럼명**: `cancel_attempted_at`
- **타입**: `timestamp without time zone`
- **Nullable**: `TRUE` (기존 주문 호환성)
- **용도**: 주문 취소 시도 시각 기록 (타임아웃 감지, 디버깅)
- **Comment**: "Timestamp when order cancellation was initiated (for timeout detection and debugging)"

#### 2. 인덱스 추가
- **인덱스명**: `idx_open_orders_cancelling_cleanup`
- **컬럼**: `(status, cancel_attempted_at)`
- **조건**: `WHERE status = 'CANCELLING'`
- **용도**: 백그라운드 정리 작업 쿼리 최적화 (120초 초과 CANCELLING 주문 검색)

### 실행 방법

#### Upgrade
```bash
# 환경 변수 설정
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=trading_system
export DB_USER=trader
export DB_PASSWORD=your_password

# 마이그레이션 실행
python migrations/20251030_add_cancelling_state.py --upgrade
```

**예상 출력**:
```
🔧 Starting migration: Add CANCELLING state and cancel_attempted_at...
  → Adding cancel_attempted_at column...
  → Creating index on (status, cancel_attempted_at)...
  ✅ cancel_attempted_at column verified
  ✅ Index idx_open_orders_cancelling_cleanup verified
✅ Migration completed successfully!
```

#### 검증
```bash
# 컬럼 확인
psql -d trading_system -c "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'open_orders' AND column_name = 'cancel_attempted_at';"

# 예상 출력:
#  column_name        | data_type                   | is_nullable
# --------------------+-----------------------------+-------------
#  cancel_attempted_at| timestamp without time zone | YES

# 인덱스 확인
psql -d trading_system -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'open_orders' AND indexname = 'idx_open_orders_cancelling_cleanup';"

# 예상 출력:
#  indexname                       | indexdef
# ---------------------------------+---------------------------------------
#  idx_open_orders_cancelling_cleanup | CREATE INDEX idx_open_orders_cancelling_cleanup ON public.open_orders USING btree (status, cancel_attempted_at) WHERE ((status)::text = 'CANCELLING'::text)
```

#### Downgrade
```bash
# 롤백 실행
python migrations/20251030_add_cancelling_state.py --downgrade
```

**안전성 확인**:
- CANCELLING 상태 주문 존재 여부 확인
- 존재 시 사용자 확인 후 롤백 진행

**예상 출력**:
```
🔄 Rolling back migration: Remove CANCELLING state support...
⚠️  WARNING: 0 orders currently in CANCELLING state!
  → Dropping index idx_open_orders_cancelling_cleanup...
  → Dropping cancel_attempted_at column...
✅ Rollback completed successfully!
```

### 의존성

- **선행 마이그레이션**: `20251030_add_error_message_field.py`
- **후속 Phase**: Phase 2 (Core Cancel Logic), Phase 4 (Background Cleanup)

### 영향 범위

- **테이블**: `open_orders`
- **서비스**: Phase 2 이후 `order_manager.py`, 백그라운드 정리 작업
- **하위 호환성**: 기존 주문 데이터에 영향 없음 (nullable 필드)

### 롤백 시나리오

1. **즉시 롤백 가능**: CANCELLING 상태 주문이 없는 경우
2. **주의 필요**: Phase 2 구현 후 CANCELLING 주문 존재 시
   - 롤백 전 모든 CANCELLING 주문을 수동으로 OPEN 또는 CANCELLED로 전환 필요

### 성능 영향

- **인덱스 크기**: Partial Index로 CANCELLING 상태만 인덱스 포함 → 최소 오버헤드
- **쿼리 성능**: 백그라운드 정리 작업 쿼리 최적화 (Full Table Scan → Index Scan)
- **디스크 사용량**: 컬럼 추가로 약 8 bytes/row 증가 (timestamp)

---

## Migration Workflow

### 마이그레이션 적용
```bash
# 자동 마이그레이션 (권장)
python run.py migrate

# 수동 실행
python migrations/{migration_file}.py

# SQL 직접 실행 (psql)
\i migrations/{migration_file}.py
```

### 마이그레이션 검증
```bash
# 1. 스키마 확인
psql -d webserver_dev -c "\d {table_name}"

# 2. 데이터 무결성 확인
psql -d webserver_dev -c "SELECT COUNT(*) FROM {table_name};"

# 3. 인덱스 확인
psql -d webserver_dev -c "\di {table_name}*"
```

### Idempotency 테스트
```bash
# 마이그레이션 두 번 실행 (에러 없어야 함)
python migrations/{migration_file}.py
python migrations/{migration_file}.py  # Should skip gracefully
```

---

## Rollback Procedures

### 일반 롤백 절차
1. **백업 생성** (필수):
   ```bash
   pg_dump -d webserver_dev -t open_orders > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Downgrade 실행**:
   ```bash
   python migrations/{migration_file}.py --downgrade
   ```

3. **검증**:
   ```bash
   psql -d webserver_dev -c "\d open_orders"  # 컬럼 제거 확인
   ```

4. **애플리케이션 재시작**:
   ```bash
   python run.py restart
   ```

### 긴급 롤백 (수동 SQL)
```sql
-- Phase 3.1 rollback
ALTER TABLE open_orders DROP COLUMN IF EXISTS error_message;
```

---

## Maintenance Notes

### 새 마이그레이션 추가 시
1. 마이그레이션 파일 생성: `migrations/{date}_{description}.py`
2. Idempotent upgrade() 함수 구현 (중복 실행 안전)
3. Safe downgrade() 함수 구현 (컬럼/인덱스 존재 여부 확인)
4. 이 문서에 마이그레이션 기록 추가
5. Backup 절차 문서화

### 마이그레이션 이름 규칙
- 형식: `{YYYYMMDD}_{snake_case_description}.py`
- 예시: `20251030_add_error_message_field.py`
- 설명은 명확하고 간결하게 (동사_명사 형식)

### 롤백 테스트
- 모든 마이그레이션은 downgrade 함수 필수
- 개발 환경에서 upgrade → downgrade → upgrade 테스트
- 데이터 손실 없는지 검증

---

*Last Updated: 2025-10-30*
*Purpose: Database schema change tracking and rollback procedures*
