# Cancel Queue Worker Documentation

FastAPI 기반 백그라운드 워커 - PENDING 주문 취소 자동 처리

**Version**: Phase 2
**Last Updated**: 2025-11-01

---

## Table of Contents

- [개요](#개요)
- [빠른 시작](#빠른-시작)
- [워커 동작 방식](#워커-동작-방식)
- [재시도 정책](#재시도-정책)
- [설정 가이드](#설정-가이드)
- [에러 처리](#에러-처리)
- [성능 최적화](#성능-최적화)
- [모니터링](#모니터링)
- [문제 해결](#문제-해결)

---

## 개요

Cancel Queue Worker는 PENDING 상태 주문의 취소 요청을 자동으로 처리하는 백그라운드 서비스입니다.

**핵심 특징**:
- 🔄 **주기적 Polling** - 5초마다 Cancel Queue 확인
- 🔒 **중복 처리 방지** - SELECT FOR UPDATE (skip_locked)로 동시성 제어
- ⚡ **거래소별 병렬 처리** - asyncio.gather로 성능 최적화
- 🔁 **Exponential Backoff** - 1분 → 2분 → 4분 → 8분 → 16분 재시도
- 🎯 **에러 분류** - Retriable vs Non-Retriable 자동 판단
- 📝 **백그라운드 로깅** - CLAUDE.md 가이드라인 준수

---

## 빠른 시작

### 1. 워커 자동 시작

Cancel Queue Worker는 FastAPI 앱 시작 시 자동으로 실행됩니다.

```bash
# 서버 실행
uvicorn app.main:app --reload --port 8000

# 로그 확인
tail -f logs/app.log | grep "Cancel Queue Worker"
```

**예상 출력**:
```
✅ Cancel Queue Worker started
```

### 2. 환경 변수 설정

`.env` 파일에 다음 변수를 설정합니다:

```bash
# Cancel Queue Worker 설정
CANCEL_QUEUE_POLL_INTERVAL=5      # Polling 간격 (초)
CANCEL_QUEUE_BATCH_SIZE=100       # 한 번에 처리할 최대 아이템 수
CANCEL_QUEUE_MAX_RETRIES=5        # 최대 재시도 횟수
```

### 3. 워커 상태 확인

```bash
# 워커 로그 확인
grep "Cancel Queue Worker" logs/app.log

# 처리 결과 확인 (DEBUG 레벨 활성화 필요)
grep "Cancel queue processed" logs/app.log
```

---

## 워커 동작 방식

### 전체 흐름

```
Start Worker
    ↓
[Every 5 seconds]
    ↓
Fetch PENDING Items (SELECT FOR UPDATE, skip_locked)
    ↓
Group by Exchange (binance, bybit, upbit)
    ↓
Parallel Processing (asyncio.gather)
    ↓
   ┌─────────────┬─────────────┬─────────────┐
   │  Binance    │   Bybit     │   Upbit     │
   │  Batch      │   Batch     │   Batch     │
   └─────────────┴─────────────┴─────────────┘
    ↓             ↓             ↓
Cancel Single Order (각 아이템)
    ↓
Success / Retry / Failed 처리
    ↓
DB Commit
```

### 주요 단계 설명

#### 1. PENDING 아이템 조회

```python
# SELECT FOR UPDATE (skip_locked)
# - 중복 처리 방지: 다른 워커가 처리 중인 아이템은 건너뜀
# - 배치 사이즈: 한 번에 최대 100개 처리
stmt = (
    select(CancelQueue)
    .with_for_update(skip_locked=True)
    .where(
        CancelQueue.status.in_(['PENDING', 'PROCESSING']),
        or_(
            CancelQueue.next_retry_at.is_(None),
            CancelQueue.next_retry_at <= now
        )
    )
    .limit(100)
)
```

**조회 조건**:
- `status`: PENDING 또는 PROCESSING
- `next_retry_at`: NULL이거나 현재 시각 이전 (재시도 시간 도래)

#### 2. 거래소별 그룹화

```python
# 거래소별로 아이템 그룹화
by_exchange = {
    'binance': [item1, item2, ...],
    'bybit': [item3, item4, ...],
    'upbit': [item5, ...]
}
```

#### 3. 병렬 처리

```python
# 거래소별로 동시에 처리 (asyncio.gather)
tasks = [
    _process_exchange_batch(binance_items, db),
    _process_exchange_batch(bybit_items, db),
    _process_exchange_batch(upbit_items, db)
]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**장점**:
- 거래소 간 독립적 처리 (한 거래소 지연이 다른 거래소에 영향 없음)
- 전체 처리 시간 최소화

#### 4. 결과 처리

| 결과 | 상태 | 다음 동작 |
|------|------|----------|
| **Success** | SUCCESS | 큐에서 제거 (완료) |
| **Retriable Error** | PENDING | `next_retry_at` 설정 후 재시도 |
| **Non-Retriable Error** | FAILED | 영구 실패 처리 |
| **Max Retries** | FAILED | 재시도 횟수 초과 |

---

## 재시도 정책

### Exponential Backoff

재시도 간격은 지수적으로 증가하여 거래소 서버 부하를 완화합니다.

| 재시도 횟수 | 대기 시간 | 누적 시간 |
|------------|---------|---------|
| 0회 (첫 시도) | - | 0분 |
| 1회 | 1분 | 1분 |
| 2회 | 2분 | 3분 |
| 3회 | 4분 | 7분 |
| 4회 | 8분 | 15분 |
| 5회 | 16분 | 31분 |
| **최대** | **1시간** | - |

**계산 공식**:
```python
delay_seconds = min(60 * (2 ** retry_count), 3600)  # 최대 1시간
```

### 재시도 가능한 에러 (Retriable Errors)

다음 에러는 자동으로 재시도됩니다:

| 에러 | 설명 | 원인 |
|------|------|------|
| `timeout` | 네트워크 타임아웃 | 거래소 API 응답 지연 |
| `network_error` | 네트워크 연결 오류 | 일시적 네트워크 문제 |
| `rate_limit` | 요청 속도 제한 | API 호출 빈도 초과 |
| `500` | Internal Server Error | 거래소 서버 내부 오류 |
| `503` | Service Unavailable | 거래소 서비스 일시 중단 |
| `504` | Gateway Timeout | 게이트웨이 타임아웃 |

### 재시도 불가능한 에러 (Non-Retriable Errors)

다음 에러는 즉시 FAILED 처리됩니다:

| 에러 | 설명 | 원인 |
|------|------|------|
| `400` | Bad Request | 잘못된 요청 파라미터 |
| `401` | Unauthorized | API 키 인증 실패 |
| `403` | Forbidden | 권한 없음 |
| `404` | Not Found | 주문 미존재 (이미 취소됨) |

**참고**: `404` 에러는 주문이 이미 취소되었거나 체결된 경우이므로, 워커는 이를 "멱등성" 관점에서 성공으로 처리합니다.

### 에러 분류 로직

```python
def _is_retriable_error(self, error_message: str) -> bool:
    error_lower = error_message.lower()

    # Non-retriable 먼저 체크
    NON_RETRIABLE_ERRORS = ['400', '401', '403', '404']
    if any(err in error_lower for err in NON_RETRIABLE_ERRORS):
        return False

    # Retriable 체크
    RETRIABLE_ERRORS = ['timeout', 'network_error', 'rate_limit', '500', '503', '504']
    if any(err in error_lower for err in RETRIABLE_ERRORS):
        return True

    # 기본값: 재시도 (보수적 접근)
    return True
```

**보수적 접근**: 알 수 없는 에러는 재시도 가능으로 간주하여 누락을 방지합니다.

---

## 설정 가이드

### 환경 변수

| 변수 | 설명 | 기본값 | 권장값 |
|------|------|--------|--------|
| `CANCEL_QUEUE_POLL_INTERVAL` | Polling 간격 (초) | 5 | 5-10 |
| `CANCEL_QUEUE_BATCH_SIZE` | 한 번에 처리할 최대 아이템 수 | 100 | 50-200 |
| `CANCEL_QUEUE_MAX_RETRIES` | 최대 재시도 횟수 | 5 | 3-10 |

### 설정 최적화 전략

#### 시나리오 1: 고빈도 취소 요청

**상황**: 초당 50개 이상의 취소 요청 발생

**권장 설정**:
```bash
CANCEL_QUEUE_POLL_INTERVAL=2      # 더 자주 체크
CANCEL_QUEUE_BATCH_SIZE=200       # 큰 배치 사이즈
CANCEL_QUEUE_MAX_RETRIES=3        # 빠른 실패
```

**효과**:
- 처리 지연 최소화
- 큐 적체 방지
- 빠른 에러 피드백

#### 시나리오 2: 네트워크 불안정 환경

**상황**: 거래소 API가 자주 타임아웃

**권장 설정**:
```bash
CANCEL_QUEUE_POLL_INTERVAL=10     # 부하 감소
CANCEL_QUEUE_BATCH_SIZE=50        # 작은 배치
CANCEL_QUEUE_MAX_RETRIES=10       # 충분한 재시도
```

**효과**:
- 거래소 API 부하 감소
- 더 많은 재시도 기회
- 안정적 처리

#### 시나리오 3: 정상 운영

**상황**: 일반적인 운영 환경

**권장 설정** (기본값 사용):
```bash
CANCEL_QUEUE_POLL_INTERVAL=5
CANCEL_QUEUE_BATCH_SIZE=100
CANCEL_QUEUE_MAX_RETRIES=5
```

---

## 에러 처리

### 에러 로그 형식

#### 성공 (INFO)

```
✅ Order cancelled: order_id=12345, exchange=binance
```

#### 재시도 예정 (WARNING)

```
⚠️ Cancel retry scheduled: order_id=12345, retry=2/5, next_retry=2025-11-01T10:35:00Z, error=timeout
```

#### 영구 실패 (ERROR)

```
❌ Cancel permanently failed: order_id=12345, retries=5, error=Max retries exceeded
```

### 에러 대응 가이드

| 에러 메시지 | 원인 | 해결 방법 |
|-----------|------|----------|
| `Account not found` | DB에 계정 정보 없음 | 계정 데이터 확인 |
| `timeout` | 거래소 API 응답 지연 | 타임아웃 설정 증가 (`EXCHANGE_TIMEOUT`) |
| `401 Unauthorized` | API 키 인증 실패 | API 키 유효성 확인 |
| `rate_limit` | API 호출 제한 초과 | Polling 간격 증가 |
| `Max retries exceeded` | 재시도 횟수 초과 | 수동 확인 필요 |

---

## 성능 최적화

### 동시성 제어

**SELECT FOR UPDATE (skip_locked)**:
- 여러 워커 인스턴스가 동시에 실행되어도 안전
- 이미 처리 중인 아이템은 자동으로 건너뜀
- 락 대기 시간 제로

```python
# 워커 A: item1, item2 처리 중 (LOCKED)
# 워커 B: item3, item4 처리 (item1, item2 건너뜀)
stmt = select(CancelQueue).with_for_update(skip_locked=True)
```

### 거래소별 병렬 처리

**Before (순차 처리)**:
```
Binance: 100ms
Bybit: 100ms
Upbit: 100ms
-------------------
Total: 300ms
```

**After (병렬 처리)**:
```
Binance ┐
Bybit   ├→ max(100ms)
Upbit   ┘
-------------------
Total: 100ms
```

**성능 향상**: 3배 (거래소 수에 비례)

### 배치 크기 최적화

| 배치 크기 | 처리 시간 | DB 부하 | 권장 사용 |
|---------|---------|---------|---------|
| 50 | 낮음 | 낮음 | 네트워크 불안정 환경 |
| 100 | 중간 | 중간 | 일반 운영 (기본값) |
| 200 | 높음 | 높음 | 고빈도 취소 요청 |

**트레이드오프**:
- 큰 배치: 처리량 증가, 메모리 사용 증가
- 작은 배치: 처리량 감소, 메모리 사용 감소

---

## 모니터링

### 로그 레벨 설정

```bash
# 개발 환경 (상세 로그)
LOG_LEVEL=DEBUG

# 프로덕션 환경 (중요 로그만)
LOG_LEVEL=INFO
BACKGROUND_LOG_LEVEL=WARNING  # 백그라운드 워커 전용
```

### 주요 로그 패턴

| 로그 | 레벨 | 의미 |
|------|------|------|
| `✅ Cancel Queue Worker started` | INFO | 워커 시작 |
| `🛑 Cancel Queue Worker stopped` | INFO | 워커 종료 |
| `🔍 Cancel queue fetched: X items` | DEBUG | 큐 조회 (X개 아이템) |
| `🔄 Cancel queue processed: total=X, success=Y` | DEBUG | 처리 결과 요약 |
| `✅ Order cancelled: order_id=X` | INFO | 취소 성공 |
| `⚠️ Cancel retry scheduled` | WARNING | 재시도 예정 |
| `❌ Cancel permanently failed` | ERROR | 영구 실패 |

### 처리 요약 로그 (DEBUG)

```
🔄 Cancel queue processed: total=10, success=8, retry=1, failed=1
```

**의미**:
- `total`: 처리 시도한 총 아이템 수
- `success`: 취소 성공
- `retry`: 재시도 예정
- `failed`: 영구 실패

### Early Return 패턴

빈 큐는 조용히 종료하여 로그 노이즈를 방지합니다.

```python
if not items:
    return  # 로그 없이 종료
```

**로그 출력 조건**:
- 실제 처리가 발생했을 때만 로그 기록
- 빈 큐 polling은 로그 미출력 (Early Return)

---

## 문제 해결

### 워커가 시작되지 않음

**증상**:
```
# 로그에 "Cancel Queue Worker started" 메시지 없음
```

**해결 방법**:
1. FastAPI 앱 시작 확인
```bash
# 서버 상태 확인
curl http://localhost:8000/health
```

2. `app/main.py`의 `lifespan` 함수 확인
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 워커 시작
    await cancel_queue_worker.start()
    yield
    # 워커 종료
    await cancel_queue_worker.stop()
```

3. 환경 변수 확인
```bash
echo $CANCEL_QUEUE_POLL_INTERVAL
```

### 취소가 처리되지 않음

**증상**:
```sql
-- PENDING 상태가 계속 유지됨
SELECT * FROM cancel_queue WHERE status = 'PENDING';
```

**해결 방법**:
1. 워커 로그 확인
```bash
grep "Cancel queue" logs/app.log
```

2. 계정 정보 확인
```sql
SELECT * FROM accounts WHERE id = {account_id};
```

3. `next_retry_at` 확인
```sql
-- 재시도 시간이 미래인지 확인
SELECT id, next_retry_at, NOW() FROM cancel_queue WHERE status = 'PENDING';
```

4. 수동 재시도
```sql
-- next_retry_at을 현재 시각으로 설정
UPDATE cancel_queue SET next_retry_at = NOW() WHERE id = {cancel_id};
```

### 재시도가 무한 반복됨

**증상**:
```
⚠️ Cancel retry scheduled: order_id=12345, retry=5/5, next_retry=...
⚠️ Cancel retry scheduled: order_id=12345, retry=5/5, next_retry=...
```

**원인**: 에러 분류 로직 오류 (Retriable로 잘못 판단)

**해결 방법**:
1. 에러 메시지 확인
```bash
grep "order_id=12345" logs/app.log
```

2. 수동 FAILED 처리
```sql
UPDATE cancel_queue
SET status = 'FAILED', error_message = 'Manual intervention'
WHERE id = {cancel_id};
```

3. 코드 수정 (필요 시)
```python
# Non-retriable 에러 추가
NON_RETRIABLE_ERRORS = ['400', '401', '403', '404', 'your-error']
```

### 성능 저하

**증상**:
- 취소 처리가 느림
- CPU 사용률 높음
- DB 연결 부족

**해결 방법**:

1. **배치 크기 줄이기**
```bash
CANCEL_QUEUE_BATCH_SIZE=50  # 기본 100 → 50
```

2. **Polling 간격 늘리기**
```bash
CANCEL_QUEUE_POLL_INTERVAL=10  # 기본 5 → 10
```

3. **DB 커넥션 풀 확인**
```bash
DB_POOL_SIZE=20  # 기본값
```

4. **처리 시간 프로파일링**
```python
# 로그 레벨을 DEBUG로 설정
LOG_LEVEL=DEBUG
```

---

## 참고 자료

- [Phase 3 - Exchange Adapters](./EXCHANGES.md) - 거래소 어댑터 상세 가이드
- [Phase 4 - Webhook](./WEBHOOK.md) - 웹훅 처리 엔드포인트
- [Configuration Guide](./CONFIGURATION.md) - 환경 변수 전체 목록
- [Models Documentation](./MODELS.md) - CancelQueue 모델 API
- [CLAUDE.md](./../CLAUDE.md) - 백그라운드 로깅 가이드라인

---

**Last Updated**: 2025-11-01
**Phase**: Phase 2
**Status**: Production Ready
