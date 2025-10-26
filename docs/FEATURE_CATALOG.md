# Feature Catalog

> 📌 **Quick Navigation**: [Active Features](#active-features) | [Recent Updates](#recent-updates) | [Tag Index](#tag-index) | [Search Patterns](#search-patterns)

프로젝트의 모든 기능과 컴포넌트를 태그 기반으로 관리하는 인덱스입니다.

## 태그 시스템 개요

### 태그 포맷
```python
# @FEAT:feature-name @COMP:component-type @TYPE:logic-type [@DEPS:dependencies]
```

### 태그 카테고리
- **@FEAT:** (필수) - 기능명 (kebab-case)
- **@COMP:** (필수) - 컴포넌트 타입 (`service`, `route`, `model`, `validation`, `exchange`, `util`, `job`)
- **@TYPE:** (필수) - 로직 타입 (`core`, `helper`, `integration`, `validation`, `config`)
- **@DEPS:** (선택) - 의존 기능 (쉼표로 구분)

---

## Recent Updates

### 2025-10-26: Toast UX Improvement - Frontend Toast Removal & Backend Batch SSE (Phase 1-2 완료)
**영향 범위**: `toast-ux-improvement`
**파일**:
- `web_server/app/static/js/positions/realtime-openorders.js` (Lines 219-220, 229-230, 972-998, **1123-1130**)
- `web_server/app/services/trading/core.py` (Lines 726-743, 841-842)

**기능 설명**: 단일 주문과 배치 주문의 Toast 알림 통일 및 중복 토스트 제거
- **Phase 1** (2025-10-25 완료): PendingOrder 토스트 필터링 + 배치 포맷 적용
  - 토스트 3개 → 0개 (필터링)
  - 포맷 통일: "📦 LIMIT 주문 생성 1건"
- **Phase 2** (2025-10-26 완료):
  - **Backend**: 다중 계좌 주문에 배치 SSE 발송
    - LIMIT/STOP 주문: 성공한 계좌가 2개 이상일 때 order_batch_update SSE 발송
    - 단일 계좌 주문: 개별 SSE 사용 (기존 로직 유지)
    - MARKET 주문: 미발송 (메타데이터 부재)
  - **Frontend**: API 응답 성공 토스트 제거
    - "모든 주문 취소" 버튼: API 응답 토스트 제거 (Line 1127-1129)
    - SSE 이벤트 토스트만 사용 (중복 제거)

**태그**: `@FEAT:toast-ux-improvement @COMP:service,route @TYPE:integration @DEPS:webhook-order,event-sse`

**검색**:
```bash
# 전체 기능
grep -r "@FEAT:toast-ux-improvement" --include="*.py" --include="*.js"

# Phase 2 Frontend 변경
grep -n "토스트 제거: SSE" web_server/app/static/js/positions/realtime-openorders.js
```

**문서**: `docs/features/toast-ux-improvement.md`

---

### 2025-10-26: Webhook Token Copy Button (UX Enhancement)
**영향 범위**: `webhook-token`
**파일**:
- `web_server/app/templates/auth/profile.html` (Lines 80-86, 414-464)
- `web_server/app/static/css/components.css` (Lines 761-765)

**기능 설명**: auth/profile 페이지 웹훅 토큰 관리 섹션에 클립보드 복사 버튼 추가
- **UI 개선**: 복사 버튼 추가 ([복사] [표시/숨김] [재발행] 순서)
- **클립보드 통합**: Clipboard API로 토큰 복사
- **사용자 피드백**:
  - 성공 시: 토스트 알림 + 2초간 체크 아이콘 표시
  - 실패 시: 에러 토스트 알림 (권한 거부, 토큰 없음 등)
- **접근성**: `aria-label` 지원으로 스크린 리더 접근성 제공
- **스타일**: `.btn-info` 클래스 정의 추가 (기존 누락 해결)

**태그**: `@FEAT:webhook-token @COMP:ui-helper,style @TYPE:helper,config`

**검색**:
```bash
grep -r "@FEAT:webhook-token" --include="*.html" --include="*.css"
```

**의존성**: Clipboard API (브라우저 네이티브, 97%+ 지원)

---

### 2025-10-25: Dynamic Port Allocation - Main Project Support (Issue #5)
**영향 범위**: `dynamic-port-allocation`
**파일**: `cli/commands/list.py` (Lines 127-173)

**문제 해결**: ls 명령어가 메인 프로젝트의 실제 호스트 포트 표시 안 함
- **변경 전**: 메인 프로젝트만 하드코딩된 기본값 사용
- **변경 후**: 모든 프로젝트(메인/워크트리) .env.local에서 동적 포트 읽기
- **동작**:
  - .env.local 존재 → "(5087, 5518, 4516)" 형식 반환
  - .env.local 없음 → stderr 경고 + "N/A" 반환
- **효과**: 메인 프로젝트 포트 충돌 시 정확한 정보 표시

**태그**: `@FEAT:dynamic-port-allocation @COMP:util @TYPE:helper`

**검색**:
```bash
# Issue #5 수정 코드
grep -n "@CHANGE: Issue #5" web_server/cli/commands/list.py
grep -n "_get_port_info" web_server/cli/commands/list.py
```

**원리**:
- Docstring (Lines 128-154): Issue #5 명시 + 동작 설명
- `_get_port_info()` (Lines 127-173): 메인/워크트리 동일 로직 (Docker API 전용)

---

### 2025-10-23: Worktree Service Conflict Detection & Auto-Resolution (Updated)
**영향 범위**: `worktree-conflict-resolution`
**파일**:
- `run.py` (Lines 412-416, 468-610, 833-904, 987-1077, 1164-1247) - TradingSystemManager 확장

**구현 내용**: 여러 git worktree 환경에서 서비스 충돌 자동 해결
- **check_port_availability()**: 필수 포트(443, 5001, 5432) 사용 가능 여부 확인
- **get_running_containers_info()**: Docker 컨테이너의 실행 경로 추적
- **check_running_services()**: 다른 worktree 경로의 실행 중인 서비스 감지
- **stop_other_services()**: 충돌 서비스 자동 종료 (docker-compose down)
- **detect_and_stop_conflicts()**: 충돌 감지 및 종료 로직 통합 (재사용 가능)
- **start_system() 개선**: 시작 전 충돌 방지 로직 추가
- **restart_system() 개선**: 재시작 전 충돌 방지 로직 추가
- **clean_system() 개선**: 정리 전 충돌 방지 로직 추가

**적용 명령어**: `start`, `restart`, `clean`

**사용 시나리오**:
```bash
# worktree1에서 서비스 실행 중
cd /path/to/worktree1
python run.py start  # ✅ 정상 실행

# worktree2에서 시작
cd /path/to/worktree2
python run.py start  # ⚠️ worktree1 서비스 감지 → 종료 → 시작

# worktree2에서 재시작
python run.py restart  # ⚠️ 다른 경로 서비스 감지 → 종료 → 재시작

# worktree3에서 정리
cd /path/to/worktree3
python run.py clean  # ⚠️ 모든 경로 서비스 감지 → 종료 → 정리
```

**기능**:
- ✅ Docker 컨테이너 라벨로 실행 경로 추적
- ✅ 포트 충돌 사전 확인 (Windows/macOS/Linux 지원)
- ✅ 다른 경로 서비스 자동 정리
- ✅ 포트 해제 대기 (3초)
- ✅ 사용자 친화적 상태 메시지

**태그**: `@FEAT:worktree-conflict-resolution @COMP:util @TYPE:core`

**문서**: `README.md` (Lines 70-91)

**검색**:
```bash
# 충돌 감지 관련 메서드
grep -n "check_running_services\|stop_other_services\|detect_and_stop_conflicts" run.py

# 통합된 명령어
grep -n "def start_system\|def restart_system\|def clean_system" run.py
```

---

### 2025-10-24: Background Log Tagging System - Phase 3.1 Complete
**영향 범위**: `background-log-tagging`
**파일**:
- `app/__init__.py` (Lines 712-793) - MARKET_INFO 함수 태그 및 Docstring 업데이트
- `docs/features/background_log_tagging.md` - Phase 3.1 섹션 추가
- `docs/FEATURE_CATALOG.md` - 기능 카탈로그 업데이트

**구현 내용**: current_app 사용 함수에 [MARKET_INFO] 태그 적용 (직접 호출 방식)
- **warm_up_market_info_with_context()** (Line 713-753, +19/-8)
  - 서버 시작 시 MarketInfo 캐시 준비
  - 로그: INFO, WARNING, ERROR (3개)
  - 기능 태그: `@FEAT:background-log-tagging @COMP:app-init @TYPE:warmup`

- **refresh_market_info_with_context()** (Line 767-793)
  - 백그라운드 갱신 (317초 주기)
  - 로그: DEBUG, ERROR (2개)
  - 기능 태그: `@FEAT:background-log-tagging @COMP:app-init @TYPE:background-refresh`

**기술**:
- Phase 1 인프라 재사용 (`format_background_log`, `BackgroundJobTag.MARKET_INFO`)
- 직접 호출 방식 선택: `current_app` 사용 함수는 데코레이터 호환 불가 (시그니처 제약)
- Docstring 업데이트: Logging 섹션 추가 (레벨, 태그, 목적)

**효과**:
- ✅ 코드 최소화: +11 lines (net, ~0.8% 증가)
- ✅ 완전한 태그 커버리지: 5/5 로그 (100%)
- ✅ 명확한 로그 의도: Docstring으로 레벨 명시

**코드 변경**:
- `app/__init__.py`: +19/-8 lines (net +11)
  - 기능 태그: +2줄
  - Docstring: +17줄

**태그**: `@FEAT:background-log-tagging @COMP:app-init @TYPE:core,warmup`

**문서**: `docs/features/background_log_tagging.md` (Phase 3.1 섹션)

**검색**:
```bash
# MARKET_INFO 태그 사용 코드
grep -n "BackgroundJobTag.MARKET_INFO" web_server/app/__init__.py

# 함수 위치
grep -n "def warm_up_market_info_with_context\|def refresh_market_info_with_context" web_server/app/__init__.py

# 기능 태그 확인
grep -n "@FEAT:background-log-tagging" web_server/app/__init__.py
```

**Quality Score**: 98/100 (code-reviewer 승인)

---

### 2025-10-24: Background Log Tagging System - Phase 2 Documentation Complete
**영향 범위**: `background-log-tagging`
**파일**:
- `app/utils/logging.py` (Lines 62-154, 156-209) - TaggedLogger, @tag_background_logger 데코레이터
- `app/__init__.py` (Lines 196-197) - TaggedLogger 래핑으로 글로벌 활성화
- `docs/features/background_log_tagging.md` - Phase 2 상세 문서화 완성
- `docs/FEATURE_CATALOG.md` - 기능 카탈로그 업데이트

**구현 내용**: 데코레이터 기반 자동 태그 적용 (Thread-Safe)
- **TaggedLogger 클래스** (Lines 62-154, +93줄)
  - 5개 로그 메서드 (debug, info, warning, error, exception)
  - Python varargs 지원: `logger.debug('msg %s', arg)` 호환
  - Thread-local 태그 조회: contextvars 기반
  - 태그 없을 때 원본 logger 동작 보존

- **@tag_background_logger 데코레이터** (Lines 156-209, +54줄)
  - 함수 진입 시 태그 설정 (`_current_tag.set(tag)`)
  - 함수 종료/예외 시 태그 복원 (finally 블록)
  - APScheduler 동시 실행 환경에서도 격리 보장
  - @wraps로 메타데이터 보존

- **적용 범위**: 10개 함수 (Lines 772-1195)
  - warm_up_precision_cache_with_context [PRECISION_CACHE]
  - refresh_precision_cache_with_context [PRECISION_CACHE]
  - update_price_cache_with_context [PRICE_CACHE]
  - update_open_orders_with_context [ORDER_UPDATE]
  - calculate_unrealized_pnl_with_context [PNL_CALC]
  - send_daily_summary_with_context [DAILY_SUMMARY]
  - auto_rebalance_all_accounts_with_context [AUTO_REBAL]
  - calculate_daily_performance_with_context [PERF_CALC]
  - release_stale_order_locks_with_context [LOCK_RELEASE]
  - check_websocket_health_with_context [WS_HEALTH]

- **제외 함수** (2개, Phase 3 예정):
  - warm_up_market_info_with_context (current_app 사용)
  - refresh_market_info_with_context (current_app 사용)

**효과**:
- ✅ 기존 로그 코드 0줄 수정 (자동 태그)
- ✅ 누락 불가능 (데코레이터 강제)
- ✅ 향후 로그 추가 시 자동 태그
- ✅ Thread-Safe (contextvars)
- ✅ 예외 안전성 (finally 복원)

**코드 변경**:
- `app/utils/logging.py`: +147줄 (TaggedLogger +93, decorator +54)
- `app/__init__.py`: +12줄 (import +2, 데코레이터 +10)
- 합계: +159줄

**태그**: `@FEAT:background-log-tagging @COMP:util @TYPE:helper`

**문서**: `docs/features/background_log_tagging.md` (검수 및 Phase 2 상세 섹션 추가)

**검색**:
```bash
# 모든 백그라운드 로깅 태그 사용 코드
grep -r "@FEAT:background-log-tagging" --include="*.py" web_server/app/

# 데코레이터 적용 함수 (10개)
grep -r "@tag_background_logger" --include="*.py" web_server/app/

# TaggedLogger 래핑 확인
grep -n "TaggedLogger" web_server/app/__init__.py
```

**Quality Score**: 98.5/100 (code-reviewer 승인)

---

### 2025-10-23: Background Log Tagging System (Phase 1) Complete
**영향 범위**: `background-log-tagging`
**파일**:
- `app/constants.py` (Lines 939-985)
- `app/utils/logging.py` (Lines 1-51)

**구현 내용**: 백그라운드 작업별 로그 태그 시스템
- **BackgroundJobTag**: 13개 백그라운드 작업의 고유 태그 정의
- **format_background_log()**: 일관된 로그 포맷팅 함수
- **JOB_TAG_MAP**: Admin 페이지 job_id → 태그 변환 매핑
- **효과**: Admin/system 페이지에서 작업별 로그 필터링 가능

**태그**: `@FEAT:background-log-tagging @COMP:config,util @TYPE:core,helper`

---

### 2025-10-23: Circuit Breaker & Gradual Recovery (Priority 2 Phase 2) Complete
**영향 범위**: `order-tracking`
**파일**: `app/services/trading/order_manager.py` (Lines 1024-1310)

**구현 내용**: 거래소별 연속 실패 제한 및 점진적 복구 메커니즘
- **Circuit Breaker Pattern**: 연속 3회(기본값) 실패 시 거래소 건너뜀
- **Gradual Recovery**: 성공 시 실패 카운터 1씩 감소 (점진적 복구)
- **설정**: `CIRCUIT_BREAKER_THRESHOLD` 환경변수로 임계값 조정
- **효과**: 일시적 거래소 장애 시 다른 정상 거래소 계속 처리

**태그**: `@FEAT:order-tracking @COMP:job @TYPE:resilience`

**문서**: `docs/features/circuit-breaker.md` (새로운 문서 작성)

**로그 패턴**:
```
🚫 Circuit Breaker 발동: BINANCE (연속 실패: 3/3) - 계좌 snlbinee의 5개 주문 건너뜀
⚠️ BINANCE 실패 카운터 증가: 2 → 3 (임계값: 3)
✅ BINANCE 복구 진행: 실패 카운터 3 → 2
```

**검색**:
```bash
grep -n "Circuit Breaker\|exchange_failures\|CIRCUIT_BREAKER_THRESHOLD" \
  web_server/app/services/trading/order_manager.py
```

---

### 2025-10-23: Background Job Logs UI + API Completed (Phase 2)
**영향 범위**: `background-job-logs`
**파일**:
- `app/routes/admin.py` (Lines 1372-1577) - 백엔드 API
- `app/templates/admin/system.html` (Lines 813-1051) - 프론트엔드 UI

**구현 내용**: Admin 대시보드 백그라운드 작업 로그 조회 완성 (UI + API End-to-End)
- **백엔드 API**: Job ID별 로그 조회, 레벨/검색 필터링, Tail 방식 읽기
  - Path Traversal 방어 (절대 경로 검증, 화이트리스트)
  - 최근 200KB 읽기, 최대 500줄 limit

- **프론트엔드 UI**: Expandable Row 패턴 (5개 JavaScript 함수)
  - 필터 컨트롤: 레벨, 검색(500ms 디바운스), Limit, 새로고침
  - 아이콘 지원: 🔴 ERROR, ⚠️ WARNING, ℹ️ INFO, 🔍 DEBUG
  - XSS 방어: escapeHtml() 적용
  - JSDoc 완비 (@param, @returns)

**태그**:
- `@FEAT:background-job-logs @COMP:route @TYPE:core` (백엔드)
- `@FEAT:background-job-logs @COMP:ui @TYPE:core` (프론트엔드)

**문서**: `docs/features/background-scheduler.md` (업데이트, 470-504줄)

**검색**:
```bash
# UI 함수 (5개)
grep -n "toggleJobLogs\|loadJobLogs\|renderLogs\|refreshJobLogs\|escapeHtml" \
  web_server/app/templates/admin/system.html
```

---

### 2025-10-21: CANCEL_ALL_ORDER Type Mismatch Fix
**영향 범위**: `webhook-order`
**파일**: `app/services/trading/core.py` (Line 1222)

**수정 내용**: CANCEL_ALL_ORDER 실행 시 발생하는 `TypeError` 해결
- **변경 전**: `sum(r.get('cancelled_orders', 0) for r in successful_cancels)`
- **변경 후**: `sum(len(r.get('cancelled_orders', [])) for r in successful_cancels)`
- **원인**: OrderManager가 List[Dict] 반환하나, 이전 코드는 int 가정
- **효과**: 배치 SSE 집계 시 TypeError 완전 제거, 안정성 개선

**태그**: `@FEAT:webhook-order @COMP:service @TYPE:core`

**검색**:
```bash
# 수정된 집계 로직 확인
grep -B 1 -A 3 "total_cancelled = sum" web_server/app/services/trading/core.py
```

---

### 2025-10-25: Strategies UI Refactor Phase 3 Complete

**영향 범위**: `strategies-ui-refactor`
**파일**: `web_server/app/templates/strategies.html` (Lines 621-666, 1147-1556, 1765-1793)

**구현 내용**: 모달 관리 통합 함수 2개 + 8개 함수 마이그레이션 + 전역 이벤트 리스너 개선
- **새 통합 함수 2개**:
  - `openModal(modalId, options)` (Lines 621-646): 7곳의 중복 모달 열기 패턴 통합
    - WHY: 7개 함수의 중복 열기/닫기 패턴을 1개로 통합, 백드롭 방지 옵션 중앙화
    - Feature tag: `@FEAT:modal-management @COMP:util @TYPE:core`
  - `closeModal(modalId)` (Lines 656-666): 3곳의 중복 모달 닫기 패턴 통합
    - WHY: 3개 함수의 닫기 로직을 1개로 통합, dataset 정리 표준화
    - Feature tag: `@FEAT:modal-management @COMP:util @TYPE:core`

- **8개 함수 마이그레이션** (`openModal()` / `closeModal()` 사용):
  - 단순 함수 6개 (Lines 1147-1556):
    - `openAddStrategyModal()` (Line 1147)
    - `closeStrategyModal()` (Line 1158)
    - `openAccountModal()` (Line 1235)
    - `closeAccountModal()` (Line 1242)
    - `openCapitalModal()` (Line 1549)
    - `closeCapitalModal()` (Line 1556)
  - 특수 함수 2개:
    - `openSubscribeModal(strategyId, strategyName)` (Line 916)
    - `openPublicDetail(strategyId)` (Line 1114, async)

- **전역 이벤트 리스너 개선** (Lines 1765-1793):
  - WHY: 7개의 개별 모달 리스너 → 1개 위임 리스너로 변경. ESC 키 최상위 모달만 닫기, preventBackdropClose 지원.
  - 이벤트 위임 패턴 적용 (document 레벨 리스너)
  - preventBackdropClose dataset 체크로 백드롭 클릭 방지
  - ESC 키는 최상위 모달만 닫기 (모달 중첩 지원)
  - Feature tag: `@FEAT:modal-management @COMP:util @TYPE:core`

**효과**:
- **유지보수성 향상**: 모달 열기/닫기 로직 통일, 백드롭/ESC 키 중앙화
- **코드 중복 제거**: 7개 열기 함수 → 1개 `openModal()`, 3개 닫기 함수 → 1개 `closeModal()`
- **확장성 개선**: 새 모달 추가 시 HTML만 작성하면 즉시 동작 (함수 추가 불필요)
- **메모리 효율**: 이벤트 위임으로 리스너 수 감소 (7개 → 1개)
- **코드 증가**: +90 lines (통합 함수 + 상세 주석, 품질 투자로 정당화됨)

**태그**: `@FEAT:modal-management @COMP:util @TYPE:core`

**검색 패턴**:
```bash
# 새 통합 함수 정의
grep -n "^async function openModal\|^function closeModal" web_server/app/templates/strategies.html

# openModal 실제 호출 (5곳)
grep -n "openModal(" web_server/app/templates/strategies.html | grep -v "function openModal" | grep -v "^\s*\*"

# closeModal 사용처 (3곳)
grep -n "closeModal(" web_server/app/templates/strategies.html | grep -v "function closeModal"

# 전역 이벤트 리스너 (위임 패턴)
grep -n "@FEAT:modal-management.*이벤트 위임\|document.*addEventListener.*modal-overlay" web_server/app/templates/strategies.html
```

**Quality Score**: 예상 85-90/100 (code-reviewer 최종 점수 대기)

---

### 2025-10-25: Strategies UI Refactor Phase 2 Complete

**영향 범위**: `strategies-ui-refactor`
**파일**: `web_server/app/templates/strategies.html` (Lines 441-605, 리팩토링된 함수들)

**구현 내용**: 핵심 유틸리티 함수 3개 추가 및 16개 함수 리팩토링
- **새 유틸리티 함수 3개**:
  - `apiCall()` (Lines 441-520): 18곳의 중복 fetch 호출 패턴 통합
    - WHY: CSRF 토큰, 에러 처리, 토스트를 자동화하여 일관성 확보. 향후 새 API 호출 3-5줄 구현 가능.
  - `renderState()` (Lines 522-585): 20곳의 인라인 로딩/에러 HTML 통합
    - WHY: 재시도 버튼에 전역 핸들러 방식으로 클로저 직렬화 문제 해결
  - `setButtonLoading()` (Lines 587-605): 버튼 로딩 상태 표준화
    - WHY: disabled/복구 실패 방지. dataset에 originalText 저장으로 안전한 원복

- **16개 함수 리팩토링**:
  - 데이터 로딩: `loadSubscribedStrategies`, `loadPublicStrategies`, `renderSubscribeAccountPicker`
  - 전략 CRUD: `editStrategy`, `deleteStrategy`, `submitStrategy`
  - 구독 관리: `subscribeStrategy`, `unsubscribeStrategy`
  - 계좌 관리: `loadStrategyAccountModal`
  - 모달 뷰: `openPublicDetail`, `loadCapitalModal`

- **4개 레거시 함수 제거**: `handleApiResponse`, `handleApiError`, `showLoadingState`, `showErrorState`

**효과**:
- **유지보수성 향상**: API 호출 패턴 통일, 에러 처리 일관성
- **코드 중복 제거**: 18개 fetch → 1개 `apiCall()`, 20개 HTML → 1개 `renderState()`
- **확장성 개선**: 향후 새 API 호출 시 3-5줄로 구현 (기존 15-20줄 대비)
- **코드 감소**: +9줄 (품질 투자로 정당화, 상세한 JSDoc + WHY 주석)

**태그**: `@FEAT:api-integration @COMP:util @TYPE:core`, `@FEAT:ui-state-management @COMP:util @TYPE:core`

**검색 패턴**:
```bash
# 새 유틸리티 함수
grep -r "@FEAT:api-integration" --include="*.html"
grep -r "@FEAT:ui-state-management" --include="*.html"

# apiCall 사용처 (10곳)
grep -n "await apiCall" web_server/app/templates/strategies.html

# renderState 사용처 (14곳)
grep -n "renderState(" web_server/app/templates/strategies.html

# setButtonLoading 사용처
grep -n "setButtonLoading(" web_server/app/templates/strategies.html
```

**Quality Score**: 92/100 (code-reviewer 승인, Minor Changes 수정 완료)

---

### 2025-10-21: Capital Management Phase 5.1 Complete
**영향 범위**: `capital-management`
**파일**:
- `app/templates/strategies.html` (Lines 58-65, 1615+) - UI 개선 및 force=true 고정

**개선 내용**:
1. **UI 단순화**: 체크박스 제거, purple gradient 버튼으로 교체
2. **동작 변경**: force=true 고정 (항상 활성 포지션 무시)
3. **안전장치 추가**: 2단계 확인 모달 (명확한 경고 메시지)
4. **디자인 개선**: 통계 카드 패턴 재사용 (purple gradient, shadow effects)
5. **코드 최소화**: -9줄 (HTML -13, JavaScript +4)

**테마 일관성**: 통계 카드의 gradient/shadow 패턴 재사용으로 세련된 UI 구현

**태그**: `@FEAT:capital-management @COMP:ui @TYPE:core`

---

## Active Features

### 🔄 Core Trading
- **webhook-order** - 웹훅 수신, 토큰 검증, 주문 처리 [`@COMP:service,route`] → [docs](features/webhook-order-processing.md)
- **order-tracking** - 주문 상태 추적 및 WebSocket 실시간 감시 [`@COMP:service`] → [docs](features/order-tracking.md)
- **order-queue** - 대기열 관리 및 동적 재정렬 (v2.2 Side별 분리) [`@COMP:service`] → [docs](features/order-queue-system.md)
- **trade-execution** - 거래 실행 및 체결 처리 [`@COMP:service`] → [docs](features/trade-execution.md)
- **limit-order-fill-processing** - LIMIT 주문 체결 자동 업데이트 (WebSocket + Scheduler) [`@COMP:service`] → [docs](features/order-tracking.md)
- **pending-order-sse** - PendingOrder 생성/삭제 SSE 발송 [`@COMP:service`] → [docs](features/order-tracking.md)

### 💰 Position & Capital
- **position-tracking** - 포지션 관리, 평균가 계산, 손익 추적 [`@COMP:service`] → [docs](features/position-tracking.md)
- **capital-management** - 자본 배분, 재할당, 수량 계산 [`@COMP:service,route`] → [docs](features/capital-management.md)

### 🔌 Exchange Integration
- **exchange-integration** - 거래소 통합 레이어 (Binance, Upbit, Bybit, Bithumb, KIS) [`@COMP:exchange`] → [docs](features/exchange-integration.md)
- **upbit-integration** - 업비트 SPOT 통합 (215개 심볼) [`@COMP:exchange`] → [docs](features/upbit-integration.md)
- **price-cache** - 가격 캐싱 및 USDT/KRW 환율 조회 [`@COMP:service`] → [docs](features/price-cache.md)
- **symbol-validation** - 심볼 검증 및 정규화 [`@COMP:validation`] → [docs](features/symbol-validation.md)
- **futures-validation** - 선물 주문 검증 (레버리지, Stop 가격) [`@COMP:validation`] → [docs](features/futures-validation.md)

### 🎨 UI & Real-time Updates
- **toast-system** - 토스트 알림 시스템 (FIFO 큐, DEBUG 로깅) [`@COMP:util`] → [docs](features/toast-ui.md)
- **toast-ux-improvement** - 단일/배치 주문 Toast 통일 [`@COMP:service,route`] → [docs](features/toast-ux-improvement.md)
- **event-sse** - SSE 실시간 이벤트 발송 (개별 + 배치) [`@COMP:service`] → [docs](features/event-sse.md)
- **batch-sse** - 배치 주문 SSE 통합 (90% SSE 감소) [`@COMP:service`] → [docs](features/backend-batch-sse.md)
- **individual-toast** - 개별 주문 토스트 알림 (PendingOrder 필터링) [`@COMP:integration`] → [docs](features/individual-toast.md)
- **open-orders-sorting** - 열린 주문 테이블 다단계 정렬 (Phase 1-3) [`@COMP:service`] → [docs](features/open_orders_sorting.md)

### 📊 Strategy & Analytics
- **strategy-management** - 전략 CRUD, 계좌 연결, 공개 전략 구독 [`@COMP:service,route`] → [docs](features/strategy-management.md)
- **analytics** - 거래 성과 분석, ROI/승률 계산, 일별 성과 집계 [`@COMP:service`] → [docs](features/analytics.md)
- **account-management** - 계좌 관리, KRW→USDT 변환 [`@COMP:service,route`] → [docs](features/account-management.md)

### ⏱️ Background Jobs & Scheduling
- **background-scheduler** - APScheduler 기반 백그라운드 작업 관리 [`@COMP:job`] → [docs](features/background-scheduler.md)
- **background-log-tagging** - 백그라운드 작업별 로그 태그 시스템 [`@COMP:util,config`] → [docs](features/background_log_tagging.md)
- **batch-parallel-processing** - ThreadPoolExecutor 병렬 처리 (MARKET 전용) [`@COMP:service`] → [docs](features/trade-execution.md)

### 🛡️ Infrastructure & Resilience
- **worktree-conflict-resolution** - Git worktree 환경 서비스 충돌 자동 해결 [`@COMP:util`] → [docs](features/worktree-conflict-resolution.md)
- **circuit-breaker** - 거래소별 연속 실패 제한 및 점진적 복구 [`@COMP:job`] → [docs](features/circuit-breaker.md)
- **health-monitoring** - WebSocket 연결 상태 감시 및 자동 재연결 [`@COMP:service`] → [docs](features/health-monitoring.md)
- **securities-token** - 한국투자증권 토큰 관리 (자동 갱신) [`@COMP:service`] → [docs](features/securities-token.md)

### 📢 Notifications & Admin
- **telegram-notification** - 텔레그램 봇 기반 알림 시스템 [`@COMP:service`] → [docs](features/telegram-notification.md)
- **admin-panel** - Admin 대시보드, 시스템 모니터링, 백그라운드 작업 로그 조회 [`@COMP:route,ui`] → [docs](features/admin-panel.md)

### 🔐 Authentication & Security
- **auth-session** - 세션 기반 인증 시스템 [`@COMP:service,route`] → [docs](features/auth-session.md)
- **webhook-token** - 웹훅 토큰 관리 (복사 버튼, 재발행) [`@COMP:ui-helper`] → [docs](features/webhook-order-processing.md)

---

## Recent Updates (Last 30 Days)

| Date | Feature | Status | Files Changed | Summary |
|------|---------|--------|---------------|---------|
| 2025-10-26 | Strategies UI Refactoring | ✅ Phase 1-4 | strategies.html (+286) | 8개 렌더링 함수, 3-tier 아키텍처 |
| 2025-10-26 | Webhook Token Copy | ✅ Complete | profile.html, components.css | 클립보드 복사 버튼 추가 |
| 2025-10-25 | Toast UX Improvement | ✅ Phase 1-2 | realtime-openorders.js, core.py | 단일/배치 Toast 통일 |
| 2025-10-25 | Dynamic Port Allocation | ✅ Complete | cli/commands/list.py | 메인 프로젝트 포트 동적 읽기 |
| 2025-10-24 | Background Log Tagging | ✅ Phase 3.1 | logging.py, __init__.py | MARKET_INFO 태그 적용 |
| 2025-10-24 | Background Log Tagging | ✅ Phase 2 | logging.py, __init__.py | 데코레이터 자동 태그 (10개 함수) |
| 2025-10-23 | Worktree Conflict Resolution | ✅ Complete | run.py | 서비스 충돌 자동 해결 |
| 2025-10-23 | Background Log Tagging | ✅ Phase 1 | constants.py, logging.py | BackgroundJobTag 시스템 |
| 2025-10-23 | Circuit Breaker | ✅ Phase 2 | order_manager.py | 거래소별 Gradual Recovery |
| 2025-10-23 | Background Job Logs UI | ✅ Phase 2 | admin.py, system.html | Admin 로그 조회 UI |
| 2025-10-21 | CANCEL_ALL Type Fix | ✅ Complete | core.py | TypeError 해결 |
| 2025-10-21 | Capital Management | ✅ Phase 5.1 | strategies.html | Force 모드 UI 단순화 |
| 2025-10-21 | Capital Management | ✅ Phase 4-5 | capital.py, strategies.html | Force 파라미터, UI 이동 |
| 2025-10-21 | Capital Management | ✅ Phase 2 | __init__.py | 스케줄 660초 간격 (130회/일) |
| 2025-10-18 | Open Orders Sorting | ✅ Phase 3 | realtime-openorders.js | SSE 정렬 유지 통합 |
| 2025-10-16 | Order Queue v2.2 | ✅ Complete | order_queue_manager.py | Known Issues 문서화 |
| 2025-10-15 | Order Queue Side Separation | ✅ Phase 1-2 | constants.py, order_queue_manager.py | Buy/Sell 독립 제한 |
| 2025-10-15 | Webhook Order Fix | ✅ Complete | webhook_service.py, core.py | AttributeError 3건 해결 |

---

## Tag Index

<details>
<summary><strong>📦 By Component Type</strong> (클릭하여 펼치기)</summary>

- **service** (35+): webhook_service, order_tracking, analytics, position_manager, capital_service, exchange, price_cache, ...
- **route** (12): webhook, positions, strategies, dashboard, capital, admin, accounts, ...
- **model** (8): Strategy, StrategyAccount, OpenOrder, StrategyPosition, Trade, TradeExecution, ...
- **validation** (4): symbol_utils, futures_validation, order_validation, ...
- **exchange** (5): binance, upbit, bybit, bithumb, korea_investment
- **util** (10): symbol_utils, logging, toast, event_emitter, ...
- **job** (8): order_queue_manager, order_manager, background_scheduler, ...
- **ui** (6): toast-system, open-orders-sorting, admin-panel, ...

</details>

<details>
<summary><strong>🔧 By Logic Type</strong></summary>

- **core** (45+): 핵심 비즈니스 로직 (주문 처리, 포지션 관리, 자본 배분)
- **helper** (20+): 유틸리티 함수 (심볼 변환, 로깅, 포맷팅)
- **integration** (15): 외부 시스템 통합 (거래소 API, WebSocket, SSE)
- **validation** (8): 입력 검증 (심볼, 선물 주문, 토큰)
- **config** (6): 설정 및 초기화 (상수, 제한값, 환경 변수)
- **resilience** (3): 복원력 패턴 (Circuit Breaker, Retry, Fallback)

</details>

<details>
<summary><strong>🔗 By Feature Group</strong></summary>

- **Trading Core** (8): webhook-order, order-tracking, order-queue, trade-execution, limit-order-fill, pending-order-sse, batch-parallel-processing, circuit-breaker
- **Position & Capital** (2): position-tracking, capital-management
- **Exchange** (5): exchange-integration, upbit-integration, price-cache, symbol-validation, futures-validation
- **UI & Real-time** (6): toast-system, toast-ux-improvement, event-sse, batch-sse, individual-toast, open-orders-sorting
- **Strategy & Analytics** (3): strategy-management, analytics, account-management
- **Background Jobs** (3): background-scheduler, background-log-tagging, batch-parallel-processing
- **Infrastructure** (4): worktree-conflict-resolution, circuit-breaker, health-monitoring, securities-token
- **Notifications** (2): telegram-notification, admin-panel
- **Auth** (2): auth-session, webhook-token

</details>

---

## Search Patterns

### 기능별 코드 찾기
```bash
# 특정 기능 전체
grep -r "@FEAT:webhook-order" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@TYPE:core"

# 다중 기능
grep -r "@FEAT:webhook-order\|@FEAT:order-queue" --include="*.py"

# JavaScript 포함
grep -r "@FEAT:toast-system" --include="*.js" --include="*.py"
```

### 컴포넌트별 검색
```bash
# 모든 서비스
grep -r "@COMP:service" --include="*.py"

# 거래소 어댑터
grep -r "@COMP:exchange" --include="*.py"

# UI 컴포넌트
grep -r "@COMP:ui" --include="*.html" --include="*.js"
```

### 로직 타입별 검색
```bash
# 핵심 비즈니스 로직
grep -r "@TYPE:core" --include="*.py"

# 통합 레이어
grep -r "@TYPE:integration" --include="*.py"

# 헬퍼 함수
grep -r "@TYPE:helper" --include="*.py"
```

---

## Maintenance Notes

### 새 기능 추가 시
1. 코드에 태그 추가: `@FEAT:feature-name @COMP:component @TYPE:type`
2. 이 카탈로그의 Active Features에 한 줄 추가
3. Recent Updates 테이블에 항목 추가
4. Feature 문서 작성: `docs/features/{feature}.md` (500줄 미만)

### 카탈로그 정리 규칙
- **크기 유지**: ~400줄 목표, 최대 500줄
- **Recent Updates**: 최근 30일만, 오래된 항목은 제거
- **상세 정보**: 파일 목록, 의존성, 변경 이력은 개별 문서에만 작성
- **Tag Index**: `<details>` 접기로 유지

### Tag Naming Convention
- 소문자, kebab-case 사용 (예: `webhook-order`, `position-tracking`)
- 명확하고 간결하게 (3단어 이내 권장)
- 기존 태그와 중복 확인

---

*Last Updated: 2025-10-26*  
*Format: C (계층적 축약형) - 인덱스 역할에 충실*  
*Total Lines: ~400 (목표 준수)*
