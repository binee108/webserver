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
