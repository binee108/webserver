# 증권 거래소 지원 마이그레이션 가이드

## 📋 개요
기존 크립토 전용 시스템에 증권 거래소 지원 기능을 추가하는 마이그레이션입니다.

### 변경 목적
- 한국투자증권, 키움증권 등 증권사 API 지원
- 계좌 타입 구분 (CRYPTO vs SECURITIES_STOCK)
- OAuth 2.0 토큰 관리 인프라 구축
- 증권사별 설정 유연성 확보

---

## 🚀 실행 방법

### 1. 백업 (필수)
마이그레이션 실행 전 반드시 데이터베이스 백업을 수행하세요.

```bash
# PostgreSQL 백업
pg_dump -U [사용자명] -h [호스트] [데이터베이스명] > backup_$(date +%Y%m%d_%H%M%S).sql

# 예시
pg_dump -U postgres -h localhost trading_db > backup_20251007_120000.sql
```

### 2. 마이그레이션 실행

#### 방법 1: psql 대화형 모드
```bash
# psql 접속
psql -U [사용자명] -h [호스트] -d [데이터베이스명]

# 마이그레이션 실행
\i /Users/binee/Desktop/quant/webserver/web_server/migrations/add_securities_support.sql
```

#### 방법 2: 명령줄 실행
```bash
psql -U [사용자명] -h [호스트] -d [데이터베이스명] \
  -f /Users/binee/Desktop/quant/webserver/web_server/migrations/add_securities_support.sql
```

### 3. 실행 결과 확인
마이그레이션이 성공하면 다음과 같은 메시지가 표시됩니다:

```
✅ accounts.account_type 컬럼 추가 완료
✅ accounts.securities_config 컬럼 추가 완료
✅ accounts.access_token 컬럼 추가 완료
✅ accounts.token_expires_at 컬럼 추가 완료
✅ securities_tokens 테이블 생성 완료
📊 accounts 테이블 추가 컬럼: 4개
📊 securities_tokens 테이블: 존재함

✅ 증권 거래소 지원 마이그레이션 완료
```

### 4. 수동 검증 (선택사항)
```sql
-- Account 테이블 확인
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'accounts'
  AND column_name IN ('account_type', 'securities_config', 'access_token', 'token_expires_at')
ORDER BY column_name;

-- SecuritiesToken 테이블 확인
\d securities_tokens

-- 기존 데이터 확인 (account_type이 CRYPTO로 설정되었는지)
SELECT id, name, exchange, account_type FROM accounts LIMIT 5;
```

---

## 🔄 롤백 방법

마이그레이션을 되돌려야 할 경우:

### 1. 백업 복원 (권장)
```bash
# 백업 파일로 복원
psql -U [사용자명] -h [호스트] -d [데이터베이스명] < backup_20251007_120000.sql
```

### 2. 롤백 스크립트 실행 (대안)
```bash
# 롤백 스크립트 실행
psql -U [사용자명] -h [호스트] -d [데이터베이스명] \
  -f /Users/binee/Desktop/quant/webserver/web_server/migrations/rollback_securities_support.sql
```

**⚠️ 주의**: 롤백 스크립트는 증권 관련 데이터를 모두 삭제합니다.

---

## 📊 변경 내역

### Account 테이블 추가 컬럼

| 컬럼명 | 타입 | NULL 허용 | 기본값 | 설명 |
|--------|------|-----------|--------|------|
| `account_type` | VARCHAR(20) | ❌ | 'CRYPTO' | 계좌 타입 (CRYPTO, SECURITIES_STOCK 등) |
| `securities_config` | TEXT | ✅ | NULL | 암호화된 증권사 설정 (JSON) |
| `access_token` | TEXT | ✅ | NULL | 암호화된 OAuth 토큰 |
| `token_expires_at` | TIMESTAMP | ✅ | NULL | 토큰 만료 시각 |

#### securities_config 구조 예시
```json
{
  "account_number": "12345678",
  "product_code": "01",
  "market_type": "DOMESTIC_STOCK",
  "cert_password": "...",
  "additional_params": {}
}
```

### SecuritiesToken 테이블 (신규 생성)

| 컬럼명 | 타입 | NULL 허용 | 기본값 | 설명 |
|--------|------|-----------|--------|------|
| `id` | SERIAL | ❌ | AUTO | Primary Key |
| `account_id` | INTEGER | ❌ | - | Account FK (CASCADE 삭제) |
| `access_token` | TEXT | ❌ | - | 암호화된 OAuth 접근 토큰 |
| `token_type` | VARCHAR(20) | ❌ | 'Bearer' | 토큰 타입 |
| `expires_in` | INTEGER | ❌ | - | 유효기간 (초) |
| `expires_at` | TIMESTAMP | ❌ | - | 만료 시각 |
| `created_at` | TIMESTAMP | ❌ | CURRENT_TIMESTAMP | 생성 시각 |
| `last_refreshed_at` | TIMESTAMP | ❌ | CURRENT_TIMESTAMP | 마지막 갱신 시각 |

#### 제약조건
- **Foreign Key**: `account_id` → `accounts.id` (ON DELETE CASCADE)
- **Unique**: `account_id` (계좌당 1개 토큰만 허용)

#### 인덱스 (성능 최적화)
- `idx_securities_token_account_id` (account_id) - FK 조인 성능 향상
- `idx_securities_token_expires_at` (expires_at) - 만료 토큰 조회 성능 향상
- `idx_securities_token_last_refreshed` (last_refreshed_at) - 갱신 대상 조회 성능 향상

---

## 📈 인덱스 최적화 전략

이 마이그레이션은 다음 인덱스를 추가하여 쿼리 성능을 최적화합니다:

| 인덱스명 | 테이블 | 컬럼 | 목적 | 예상 개선 효과 |
|----------|--------|------|------|----------------|
| `idx_account_type` | accounts | account_type | 계좌 타입별 조회 성능 향상 | CRYPTO/SECURITIES_STOCK 필터링 시 Full Table Scan 방지 |
| `idx_securities_token_account_id` | securities_tokens | account_id | FK 조인 성능 향상 | Account ↔ SecuritiesToken JOIN 시 인덱스 스캔 사용 |
| `idx_securities_token_expires_at` | securities_tokens | expires_at | 만료 토큰 조회 성능 향상 | 토큰 갱신 Job에서 만료 임박 토큰 조회 시 인덱스 사용 |
| `idx_securities_token_last_refreshed` | securities_tokens | last_refreshed_at | 갱신 대상 조회 성능 향상 | 일정 시간 이상 갱신되지 않은 토큰 조회 시 인덱스 사용 |

### 인덱스 사용 예시 쿼리

```sql
-- 1. 계좌 타입별 조회 (idx_account_type)
SELECT * FROM accounts WHERE account_type = 'SECURITIES_STOCK';

-- 2. 만료 임박 토큰 조회 (idx_securities_token_expires_at)
SELECT * FROM securities_tokens
WHERE expires_at <= NOW() + INTERVAL '6 hours';

-- 3. 갱신 필요 토큰 조회 (idx_securities_token_last_refreshed)
SELECT * FROM securities_tokens
WHERE last_refreshed_at < NOW() - INTERVAL '6 hours';

-- 4. FK 조인 (idx_securities_token_account_id)
SELECT a.name, st.expires_at
FROM accounts a
JOIN securities_tokens st ON a.id = st.account_id
WHERE a.account_type = 'SECURITIES_STOCK';
```

### 성능 검증 쿼리

마이그레이션 실행 후 다음 쿼리로 인덱스 사용 여부를 확인하세요:

```sql
-- 인덱스 생성 확인
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename IN ('accounts', 'securities_tokens')
ORDER BY tablename, indexname;

-- 쿼리 플랜 확인 (인덱스 사용 여부)
EXPLAIN ANALYZE
SELECT * FROM securities_tokens
WHERE last_refreshed_at < NOW() - INTERVAL '6 hours';

-- 예상 결과: Index Scan using idx_securities_token_last_refreshed
-- (NOT Seq Scan on securities_tokens)
```

---

## ⚠️ 주의사항

### 실행 전
- ✅ **백업 필수**: 운영 DB는 반드시 백업 후 실행
- ✅ **점검 시간**: 운영 환경에서는 점검 시간에 실행
- ✅ **권한 확인**: ALTER TABLE 권한 필요
- ✅ **디스크 공간**: 테이블 크기에 따라 충분한 공간 확보

### 실행 중
- 마이그레이션은 트랜잭션으로 실행됩니다 (BEGIN/COMMIT)
- 실패 시 자동 롤백됩니다
- Idempotent 설계로 재실행 가능합니다 (IF NOT EXISTS 체크)

### 실행 후
- 기존 계좌는 자동으로 `account_type='CRYPTO'`로 설정됩니다
- 증권 계좌 추가 시 `account_type='SECURITIES_STOCK'` 명시 필요
- SecuritiesToken 캐시는 애플리케이션 레벨에서 자동 관리됩니다

### 롤백 시
- ⚠️ **데이터 손실**: 모든 증권 관련 데이터 삭제됨
- ⚠️ **증권 계좌**: `account_type='SECURITIES_STOCK'` 계좌는 타입 정보 손실
- ⚠️ **토큰 캐시**: securities_tokens 테이블 전체 삭제

---

## 🔧 트러블슈팅

### 문제 1: "relation already exists" 오류
**원인**: 이미 마이그레이션이 실행된 상태
**해결**: 정상 동작입니다. 스크립트가 기존 구조를 감지하고 스킵합니다.

### 문제 2: "permission denied" 오류
**원인**: ALTER TABLE 권한 부족
**해결**: SUPERUSER 또는 테이블 소유자 계정으로 실행하세요.

### 문제 3: "relation does not exist" (accounts)
**원인**: 테이블명 불일치 (accounts vs account)
**해결**:
```sql
-- 테이블명 확인
\dt
-- 실제 테이블명에 맞게 스크립트 수정 필요
```

### 문제 4: 롤백 후 데이터 복구
**원인**: 롤백 스크립트는 데이터를 삭제합니다
**해결**: 백업 파일에서 복원하세요.

---

## 📚 관련 문서

- [Phase 4.1: Securities Exchange Support 구조 설계](/Users/binee/Desktop/quant/webserver/web_server/app/securities/)
- [한국투자증권 API 인증](/Users/binee/Desktop/quant/webserver/docs/korea_investment_api_auth.md)
- [프로젝트 CLAUDE.md](/Users/binee/Desktop/quant/webserver/CLAUDE.md)

---

## 📝 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|-----------|
| 2025-10-07 | 1.0 | 초기 마이그레이션 스크립트 작성 |

---

## 🆘 문의

마이그레이션 관련 문제 발생 시:
1. 백업 파일 확인
2. 실행 로그 저장
3. `/Users/binee/Desktop/quant/webserver/web_server/logs/app.log` 확인
4. 이슈 리포트 작성
