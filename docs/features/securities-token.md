# 증권사 OAuth 토큰 자동 갱신

> **목적**: 증권사 API OAuth 토큰을 자동으로 갱신하여 만료로 인한 인증 실패를 방지하고 안정적인 증권 거래 서비스를 제공합니다.

## 1. 개요

### 시스템 역할
- OAuth 2.0 토큰 만료 감지 (24시간 유효기간)
- 주기적 토큰 자동 갱신 (6시간마다)
- Race Condition 방지 (DB 락)
- 갱신 실패 계좌 추적 및 알림

### 기술 스택
- **인증**: OAuth 2.0 (access_token)
- **저장**: PostgreSQL (`securities_tokens` 테이블)
- **스케줄러**: APScheduler (6시간 주기)
- **동시성 제어**: SELECT FOR UPDATE

---

## 2. 실행 플로우

```
[토큰 발급]
    ↓
[유효 24시간]
    ↓
[6시간 경과] → needs_refresh() = True → 자동 갱신 Job
    ↓
[새 토큰 발급 → DB 업데이트]
    ↓
[만료 5분 전] → is_expired() = True → 긴급 재발급
```

### 주요 단계
1. APScheduler가 6시간마다 `SecuritiesTokenRefreshJob.run()` 실행 (동기 래퍼)
2. 내부에서 `asyncio.run(run_async())`로 비동기 로직 실행
3. 모든 증권 계좌(`SECURITIES_%`) 조회 (Line 96-98)
4. 각 계좌마다 `await exchange.ensure_token()` 호출 → 자동 갱신 판단 (Line 125)
   - `ensure_token()`: 토큰 유효성 확인 → 만료되거나 6시간 경과 시 갱신
   - `is_expired()`: 만료 5분 전 판정 (재발급 트리거)
   - `needs_refresh()`: 마지막 갱신 후 6시간 경과 판정 (갱신 트리거)
5. 갱신 필요 시 증권사 API 호출 → DB 업데이트
6. 성공/실패 로깅 및 결과 반환 (Line 150-164)

**비동기 패턴:**
- `run()`: 동기 래퍼 (APScheduler 호환용)
- `run_async()`: 실제 비동기 로직 (native await 사용)
- Thread Pool 안전성을 위해 최상위 레벨에서만 `asyncio.run()` 호출

---

## 3. 데이터 플로우

```
[APScheduler Job]
    ↓
[SecuritiesTokenRefreshJob] → Account.query (SECURITIES_%)
    ↓
[SecuritiesExchangeFactory] → 어댑터 생성 (KoreaInvestmentAdapter)
    ↓
[ensure_token()] → DB 조회 (SELECT FOR UPDATE)
    ↓
[needs_refresh() 확인] → 6시간 경과?
    ↓ Yes
[authenticate()/refresh_token()] → 증권사 API 호출
    ↓
[SecuritiesToken 업데이트] → DB COMMIT
```

### 주요 의존성
- `Account` 모델: 증권 계좌 정보
- `SecuritiesToken` 모델: 토큰 캐시 (1:1 relationship with Account)
  * `account_id` (FK, UNIQUE, CASCADE DELETE)
  * `account` relationship: bidirectional link to Account
- `SecuritiesExchangeFactory`: 증권사별 어댑터 생성
- `KoreaInvestmentAdapter`: 한국투자증권 구현체

**SecuritiesToken ↔ Account 관계:**
- Account 삭제 시 Token 자동 삭제 (SQL FK CASCADE)
- Token 삭제 시 Account 유지 (역방향 cascade 없음)

---

## 4. 주요 컴포넌트

| 파일 | 역할 | 태그 | 핵심 메서드/기능 |
|------|------|------|----------------|
| `jobs/securities_token_refresh.py` | 자동 갱신 Job | `@FEAT:securities-token @COMP:job @TYPE:core` | `run_async()`, `run()`, `get_accounts_needing_refresh()` |
| `cli/securities.py` | CLI 명령어 | `@FEAT:securities-token @COMP:cli @TYPE:core` | `refresh-tokens`, `check-status` |
| `exchanges/securities/base.py` | 토큰 관리 로직 | `@FEAT:securities-token @COMP:exchange @TYPE:core` | `ensure_token()` (동기), `authenticate()`, `refresh_token()` |
| `models.py:SecuritiesToken` | 토큰 캐시 모델 | `@FEAT:securities-token @COMP:model @TYPE:core` | `is_expired()`, `needs_refresh()` |
| `exchanges/securities/factory.py` | 거래소 팩토리 | `@FEAT:securities-token @COMP:exchange @TYPE:helper` | `SecuritiesExchangeFactory.create()` |

### ensure_token() - 토큰 관리의 핵심 메서드

**파일**: `exchanges/securities/base.py:96-188`

```python
def ensure_token(self) -> str:
    """
    유효한 토큰 보장 (자동 갱신)

    Race Condition 방지:
    - SELECT ... FOR UPDATE로 DB 레벨 락 사용
    - 동시 요청 시 첫 번째만 토큰 발급, 나머지는 대기 후 재사용

    Returns:
        str: 유효한 access_token
    """
```

**동작 흐름**:
1. DB에서 토큰 캐시 조회 (SELECT FOR UPDATE 락 적용)
2. 토큰이 없거나 `is_expired()` = True → `authenticate()` 호출 (재발급)
3. 토큰이 있고 `needs_refresh()` = True → `refresh_token()` 호출 (갱신)
4. 그 외 → 캐시된 토큰 반환 (DB 쓰기 없음)
5. 모든 성공/실패 로그 기록

### 토큰 상태 판정 로직

**파일**: `models.py:SecuritiesToken`

```python
def is_expired(self) -> bool:
    """토큰 만료 여부 확인 (5분 버퍼)"""
    return datetime.utcnow() > (self.expires_at - timedelta(minutes=5))

def needs_refresh(self) -> bool:
    """토큰 갱신 필요 여부 (6시간 기준)"""
    return datetime.utcnow() > (self.last_refreshed_at + timedelta(hours=6))
```

**판정 기준**:
- `is_expired()`: 만료 5분 전 도달 시 True (긴급 상황 감지)
- `needs_refresh()`: 마지막 갱신으로부터 6시간 경과 시 True (예방적 갱신)

---

## 5. 설계 결정 히스토리

### 왜 6시간 주기 갱신인가?
- 토큰 유효기간: 24시간
- 안전 마진: 24h ÷ 4 = 6h (4회 갱신 기회)
- 만료 5분 전 재발급으로 이중 안전망 구축

### 왜 DB 락 (`SELECT FOR UPDATE`)인가?
- **문제**: 여러 프로세스/스레드가 동시에 갱신 시도 → 중복 API 호출, 토큰 불일치
- **해결**: PostgreSQL 행 레벨 락으로 첫 번째 프로세스만 갱신, 나머지는 대기 후 재사용
- **대안 검토**: Redis 락 (추가 인프라 부담), 메모리 락 (멀티 프로세스 불가)

### 동작 흐름
```
[Process A]              [Process B]
SELECT FOR UPDATE        SELECT FOR UPDATE
🔒 락 획득               ⏳ 대기 (블로킹)
API 호출 → DB 업데이트
COMMIT (락 해제) ────→  🔓 락 획득
                        캐시 확인 → 갱신 불필요
                        COMMIT
```

---

## 5.5 Helper 메서드

### get_accounts_needing_refresh()

**파일**: `jobs/securities_token_refresh.py:204-267`

```python
@staticmethod
async def get_accounts_needing_refresh_async(app: Flask = None) -> List['Account']:
    """갱신이 필요한 계좌 목록 조회 (비동기 버전)"""
    # 내부: 6시간 이내 만료되는 계좌 조회
    threshold = datetime.utcnow() + timedelta(hours=6)
    accounts = db.session.query(Account)\
        .join(SecuritiesToken)\
        .filter(SecuritiesToken.expires_at <= threshold).all()
```

**목적**:
- Job 실행 전 갱신 대상 사전 파악
- 스케줄러 모니터링 및 알림 시스템에 사용 가능
- CLI 명령어 `check-status`와 연동

---

## 6. CLI 명령어

### 수동 토큰 갱신
```bash
flask securities refresh-tokens
```
- 모든 증권 계좌 즉시 갱신
- Background Job과 동일한 로직 사용

### 토큰 상태 확인
```bash
flask securities check-status
```
- 만료 시간, 남은 시간, 마지막 갱신 확인
- 갱신 필요 계좌 식별 (6시간 경과)

---

## 7. 유지보수 가이드

### 주의사항
1. **API 호출 전 `ensure_token()` 필수**: 모든 증권사 API 호출 전 토큰 유효성 확인
2. **DB 락 유지**: `ensure_token()` 내부 `with_for_update()` 제거 금지
3. **Job 실행 확인**: 스케줄러 상태 정기 점검 (`/api/system/scheduler/status`)

### 확장 포인트
- **새 증권사 추가**: `SecuritiesExchangeFactory`에 어댑터 등록, `authenticate()` 구현
- **갱신 주기 변경**: `app/__init__.py:add_job(hours=6)` 수정
- **알림 추가**: `refresh_securities_tokens_with_context()` 내부에 Telegram/Email 전송 로직 추가

### 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 토큰 갱신 실패 (401) | 잘못된 API 키, 서버 장애 | `flask securities check-status` → API 키 재설정 |
| 6시간 경과해도 갱신 안 됨 | Job 미등록, 스케줄러 중단 | `curl /api/system/scheduler/status` → 서버 재시작 |
| 중복 API 호출 | DB 락 미작동 | `with_for_update()` 확인, DB 연결 풀 점검 |
| API 호출 시 토큰 만료 | 자동 갱신 실패 | `flask securities refresh-tokens` 즉시 실행 |

### 로그 확인
```bash
# 갱신 Job 실행 이력
grep "증권 토큰 자동 갱신" /Users/binee/Desktop/quant/webserver/web_server/logs/app.log

# 실패 이력
grep "토큰 갱신 실패" /Users/binee/Desktop/quant/webserver/web_server/logs/app.log

# 최근 24시간 갱신 성공
grep "토큰 갱신 완료" /Users/binee/Desktop/quant/webserver/web_server/logs/app.log | tail -20
```

### DB 직접 조회
```sql
-- 토큰 만료 시간 및 갱신 경과 시간 확인
SELECT
    account_id,
    expires_at,
    last_refreshed_at,
    EXTRACT(EPOCH FROM (expires_at - NOW())) / 3600 AS hours_until_expiry,
    EXTRACT(EPOCH FROM (NOW() - last_refreshed_at)) / 3600 AS hours_since_refresh
FROM securities_tokens
ORDER BY expires_at;
```

---

## 8. Quick Search

```bash
# 모든 securities-token 관련 코드
grep -r "@FEAT:securities-token" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:securities-token" --include="*.py" | grep "@TYPE:core"

# CLI 명령어
grep -r "@FEAT:securities-token" --include="*.py" | grep "@COMP:cli"

# Job 코드
grep -r "@FEAT:securities-token" --include="*.py" | grep "@COMP:job"
```

---

## 관련 문서

- [거래소 통합](./exchange-integration.md) - 증권사 어댑터 구조
- [백그라운드 스케줄러](./background-scheduler.md) - APScheduler 설정
- [아키텍처 개요](../ARCHITECTURE.md) - 시스템 전체 구조
- **API 문서**: `/Users/binee/Desktop/quant/webserver/docs/korea_investment_api_auth.md`

---

*Last Updated: 2025-10-30*
*Version: 2.1 (Full Codebase Sync)*

**Changes from 2.0.1:**
- Added `ensure_token()` detailed flow (base.py:96-188)
- Documented helper method `get_accounts_needing_refresh()` (job.py:204-267)
- Clarified `ensure_token()` is synchronous (not async)
- Updated component table with factory.py and method tags
- Enhanced OAuth flow documentation with Race Condition prevention details

**Verification Status:**
- ✅ `jobs/securities_token_refresh.py`: run(), run_async(), get_accounts_needing_refresh()
- ✅ `cli/securities.py`: refresh-tokens, check-status commands
- ✅ `exchanges/securities/base.py`: ensure_token() flow & SELECT FOR UPDATE
- ✅ `models.py`: SecuritiesToken with is_expired(), needs_refresh()
- ✅ Account-SecuritiesToken 1:1 relationship (CASCADE DELETE on Account)
