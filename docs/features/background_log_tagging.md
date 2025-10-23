# 백그라운드 작업 로그 태깅 시스템

**Tags:** `@FEAT:background-log-tagging`

## 개요

백그라운드 작업별 로그를 명확히 구분하기 위한 태그 기반 로깅 시스템입니다.
Admin/system 페이지에서 작업별 로그를 정확하게 필터링할 수 있으며,
로그 파싱 로직을 단순화하고 유지보수성을 향상시킵니다.

**문제 해결**: 기존 파일 경로 기반 파싱으로는 13개 작업 중 대부분이
`app/__init__.py`에 정의되어 명확한 구분이 어려웠습니다. 이제 모든 작업이
고유한 태그를 통해 쉽게 식별됩니다.

---

## 아키텍처

### 1. 태그 정의 (BackgroundJobTag)

**위치:** `web_server/app/constants.py` (lines 939-965)

**형식:** `[TAG_NAME]` (대괄호로 감싼 대문자)

**네이밍 규칙:**
- 최대 15자 (괄호 제외)
- 명확하고 축약된 이름 사용
- 작업의 핵심 기능을 즉시 알 수 있도록 구성

**클래스 구조:**
```python
class BackgroundJobTag:
    """백그라운드 작업 태그 (로그 구분용)"""
    PRECISION_CACHE = "[PRECISION_CACHE]"    # Precision 캐시 업데이트 (30초 주기)
    SYMBOL_VALID = "[SYMBOL_VALID]"          # Symbol Validator 갱신 (30초 주기)
    MARKET_INFO = "[MARKET_INFO]"            # MarketInfo 백그라운드 갱신 (30초 주기)
    PRICE_CACHE = "[PRICE_CACHE]"            # 가격 캐시 업데이트 (5초 주기)
    ORDER_UPDATE = "[ORDER_UPDATE]"          # 미체결 주문 상태 업데이트 (29초 주기)
    PNL_CALC = "[PNL_CALC]"                  # 미실현 손익 계산 (29초 주기)
    DAILY_SUMMARY = "[DAILY_SUMMARY]"        # 일일 요약 전송 (매일 09:00)
    PERF_CALC = "[PERF_CALC]"                # 일일 성과 계산 (매일 09:05)
    AUTO_REBAL = "[AUTO_REBAL]"              # 자동 리밸런싱 (매시 17분)
    TOKEN_REFRESH = "[TOKEN_REFRESH]"        # 증권 OAuth 토큰 갱신 (매시 정각)
    QUEUE_REBAL = "[QUEUE_REBAL]"            # 대기열 재정렬 (1초 주기)
    LOCK_RELEASE = "[LOCK_RELEASE]"          # 오래된 처리 잠금 해제 (5분 주기)
    WS_HEALTH = "[WS_HEALTH]"                # WebSocket 연결 상태 모니터링 (30초 주기)
```

### 2. 로그 포맷팅 함수 (format_background_log)

**위치:** `web_server/app/utils/logging.py`

**역할:** 태그와 메시지를 결합하여 일관된 포맷 생성

**구현:**
```python
def format_background_log(tag: BackgroundJobTag, message: str) -> str:
    """백그라운드 작업 로그 포맷팅

    Args:
        tag: 백그라운드 작업 태그 (BackgroundJobTag 상수)
        message: 로그 메시지

    Returns:
        str: 태그가 포함된 포맷팅된 로그 메시지 ("[TAG] message")
    """
    return f"{tag} {message}"
```

**사용 예:**
```python
logger.info(format_background_log(BackgroundJobTag.AUTO_REBAL, "작업 시작"))
# 출력: [AUTO_REBAL] 작업 시작
```

### 3. Job ID 매핑 (JOB_TAG_MAP)

**위치:** `web_server/app/constants.py` (lines 967-984)

**역할:** Admin 페이지에서 job_id → 태그 변환

**구조:**
```python
JOB_TAG_MAP = {
    'precision_cache': BackgroundJobTag.PRECISION_CACHE,
    'symbol_validator': BackgroundJobTag.SYMBOL_VALID,
    'market_info': BackgroundJobTag.MARKET_INFO,
    'price_cache': BackgroundJobTag.PRICE_CACHE,
    'update_open_orders': BackgroundJobTag.ORDER_UPDATE,
    'update_positions': BackgroundJobTag.PNL_CALC,
    'send_daily_summary': BackgroundJobTag.DAILY_SUMMARY,
    'calculate_daily_performance': BackgroundJobTag.PERF_CALC,
    'auto_rebalance': BackgroundJobTag.AUTO_REBAL,
    'securities_token_refresh': BackgroundJobTag.TOKEN_REFRESH,
    'queue_rebalancer': BackgroundJobTag.QUEUE_REBAL,
    'release_stale_processing': BackgroundJobTag.LOCK_RELEASE,
    'websocket_health_monitor': BackgroundJobTag.WS_HEALTH,
}
```

---

## 백그라운드 작업 태그 목록

| 상수명 | 태그 | Job ID | 설명 | 주기 |
|--------|------|--------|------|------|
| PRECISION_CACHE | [PRECISION_CACHE] | precision_cache | Precision 캐시 업데이트 | 30초 |
| SYMBOL_VALID | [SYMBOL_VALID] | symbol_validator | Symbol Validator 갱신 | 30초 |
| MARKET_INFO | [MARKET_INFO] | market_info | MarketInfo 백그라운드 갱신 | 30초 |
| PRICE_CACHE | [PRICE_CACHE] | price_cache | 가격 캐시 업데이트 | 5초 |
| ORDER_UPDATE | [ORDER_UPDATE] | update_open_orders | 미체결 주문 상태 업데이트 | 29초 |
| PNL_CALC | [PNL_CALC] | update_positions | 미실현 손익 계산 | 29초 |
| DAILY_SUMMARY | [DAILY_SUMMARY] | send_daily_summary | 일일 요약 전송 | 매일 09:00 |
| PERF_CALC | [PERF_CALC] | calculate_daily_performance | 일일 성과 계산 | 매일 09:05 |
| AUTO_REBAL | [AUTO_REBAL] | auto_rebalance | 자동 리밸런싱 | 매시 17분 |
| TOKEN_REFRESH | [TOKEN_REFRESH] | securities_token_refresh | 증권 OAuth 토큰 갱신 | 매시 정각 |
| QUEUE_REBAL | [QUEUE_REBAL] | queue_rebalancer | 대기열 재정렬 | 1초 |
| LOCK_RELEASE | [LOCK_RELEASE] | release_stale_processing | 오래된 처리 잠금 해제 | 5분 |
| WS_HEALTH | [WS_HEALTH] | websocket_health_monitor | WebSocket 연결 상태 모니터링 | 30초 |

---

## 사용 방법

### 백그라운드 작업 로깅

백그라운드 작업은 모든 로깅에서 `format_background_log()` 함수를 사용해야 합니다:

```python
from app.utils.logging import format_background_log
from app.constants import BackgroundJobTag

def my_background_job():
    logger = logging.getLogger(__name__)

    # 작업 시작
    logger.info(format_background_log(BackgroundJobTag.AUTO_REBAL, "🔄 작업 시작"))

    try:
        # ... 작업 수행 ...
        count = 5
        logger.debug(format_background_log(BackgroundJobTag.AUTO_REBAL, f"처리: {count}개"))

        # 작업 완료
        logger.info(format_background_log(BackgroundJobTag.AUTO_REBAL, f"✅ 완료 - 처리: {count}개"))
    except Exception as e:
        logger.error(format_background_log(BackgroundJobTag.AUTO_REBAL, f"❌ 실패: {str(e)}"))
```

**로그 출력 예:**
```
2025-10-23 14:30:45,123 INFO: [AUTO_REBAL] 🔄 작업 시작
2025-10-23 14:30:46,234 DEBUG: [AUTO_REBAL] 처리: 5개
2025-10-23 14:30:47,345 INFO: [AUTO_REBAL] ✅ 완료 - 처리: 5개
```

### Admin 페이지에서 로그 필터링

```python
from app.constants import JOB_TAG_MAP
import re

job_id = request.args.get('job_id')  # 예: 'auto_rebalance'

if job_id and job_id in JOB_TAG_MAP:
    job_tag = JOB_TAG_MAP[job_id]
    # 로그에서 job_tag.value (예: "[AUTO_REBAL]")로 필터링
    pattern = re.escape(job_tag.value)
    # 로그 파일을 정규식으로 파싱
```

---

## 새 백그라운드 작업 추가 시

### 1단계: 태그 정의

`web_server/app/constants.py`의 `BackgroundJobTag` 클래스에 추가:

```python
class BackgroundJobTag:
    # ... 기존 태그들 ...
    NEW_JOB = "[NEW_JOB]"  # 새 작업 설명 (주기)
```

**태그 네이밍 규칙:**
- 최대 15자 (괄호 제외)
- 작업의 핵심 기능을 명확하게 표현
- 기존 태그와 유사한 패턴 유지
- 대문자 + 언더스코어 사용

### 2단계: Job ID 매핑 추가

`web_server/app/constants.py`의 `JOB_TAG_MAP`에 추가:

```python
JOB_TAG_MAP = {
    # ... 기존 매핑 ...
    'new_job_id': BackgroundJobTag.NEW_JOB,
}
```

**주의사항:**
- job_id는 APScheduler에 등록된 작업의 ID와 정확히 일치해야 함
- 중복 없음 확인

### 3단계: 작업 코드에서 사용

```python
from app.utils.logging import format_background_log
from app.constants import BackgroundJobTag

def new_background_job():
    logger.info(format_background_log(BackgroundJobTag.NEW_JOB, "작업 시작"))
    # ... 작업 수행 ...
    logger.info(format_background_log(BackgroundJobTag.NEW_JOB, "작업 완료"))
```

### 4단계: 문서 업데이트

이 문서의 "백그라운드 작업 태그 목록" 테이블에 새 작업 추가

---

## 관련 파일 및 역할

| 파일 | 역할 | 담당 |
|------|------|------|
| `web_server/app/constants.py` | 태그 정의 및 매핑 저장소 | config |
| `web_server/app/utils/logging.py` | 포맷팅 함수 | util/helper |
| `web_server/app/__init__.py` | 백그라운드 작업 등록 | 향후 개선 대상 |
| `web_server/app/routes/admin.py` | 로그 필터링 로직 (향후 개선) | 향후 개선 대상 |
| `docs/features/background_log_tagging.md` | 기능 설명 (이 파일) | documentation |

---

## 백그라운드 로깅 가이드라인

### 로그 레벨 선택

**CLAUDE.md "백그라운드 서비스 로깅 가이드라인" 참조:**

| 레벨 | 용도 |
|------|------|
| ERROR | 작업 실패, 시스템 오류 |
| WARNING | 주의 필요, 잠재적 문제 |
| INFO | 의미 있는 상태 변화 (작업 완료, 실제 처리 발생) |
| DEBUG | 상세 진단, 반복 작업의 중간 단계 |

### 고빈도 작업 패턴 (1-5초)

**Pattern: 조용한 종료 + 5분 주기 요약**

```python
if not all_pairs:
    return  # 조용히 종료 (로그 없음)

# ... 작업 수행 ...

if current_time - _last_status_log > 300:  # 5분
    logger.info(format_background_log(BackgroundJobTag.QUEUE_REBAL,
                                      f"📊 상태 요약 - 활성: {count}개"))
```

---

## Phase 1 구현 현황

| 단계 | 상태 | 담당 | 내용 |
|------|------|------|------|
| Step 1 | ✅ 완료 | project-planner | 계획 수립 |
| Step 2 | ✅ 완료 | plan-reviewer | 계획 검토 |
| Step 2.5 | ✅ 완료 | User | 승인 |
| Step 3 | ✅ 완료 | backend-developer | 태그 정의 및 함수 구현 |
| Step 4 | ✅ 완료 | code-reviewer | 코드 검토 |
| Step 5 | 🔄 진행 중 | documentation-manager | 문서화 |
| Step 6 | ⏳ 예정 | documentation-reviewer | 문서 검토 |
| Step 7 | ⏳ 예정 | feature-tester | 테스트 실행 |
| Step 8 | ⏳ 예정 | test-reviewer | 테스트 검토 |
| Step 9 | ⏳ 예정 | git-worktree-manager | 커밋 |

---

## 빠른 참조

### 임포트
```python
from app.constants import BackgroundJobTag, JOB_TAG_MAP
from app.utils.logging import format_background_log
```

### 사용 예
```python
logger.info(format_background_log(BackgroundJobTag.AUTO_REBAL, "작업 시작"))
```

### 태그 확인
```bash
# 모든 태그 확인
grep -r "@FEAT:background-log-tagging" --include="*.py"

# 특정 작업의 태그 확인
grep "QUEUE_REBAL" web_server/app/constants.py
```

---

*Last Updated: 2025-10-23*
*Document Version: 1.0*
*Status: Phase 1 Step 5 (Documentation)*
