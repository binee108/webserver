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

## Active Features

### 🔄 Core Trading
- **webhook-order** - 웹훅 수신, 토큰 검증, 주문 처리 [`@COMP:service,route`] → [docs](features/webhook-order-processing.md)
- **immediate-order-execution** - 웹훅 주문 즉시 실행 및 FailedOrder 관리 UI [`@COMP:service,route,ui`] → [docs](features/immediate-order-execution.md)
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
- **strategy-subscription-safety** - 구독/해제 보안 강화, 강제 청산, Race Condition 방지 (Phase 1-5) [`@COMP:service,route`] → [docs](features/strategy-subscription-safety.md)
- **analytics** - 거래 성과 분석, ROI/승률 계산, 일별 성과 집계 [`@COMP:service`] → [docs](features/analytics.md)
- **account-management** - 계좌 관리, KRW→USDT 변환 [`@COMP:service,route`] → [docs](features/account-management.md)

### ⏱️ Background Jobs & Scheduling
- **background-scheduler** - APScheduler 기반 백그라운드 작업 관리 [`@COMP:job`] → [docs](features/background-scheduler.md)
- **background-log-tagging** - 백그라운드 작업별 로그 태그 시스템 [`@COMP:util,config`] → [docs](features/background_log_tagging.md)
- **batch-parallel-processing** - ThreadPoolExecutor 병렬 처리 (MARKET 전용) [`@COMP:service`] → [docs](features/trade-execution.md)

### 🛡️ Infrastructure & Resilience
- **db-first-orphan-prevention** - DB-first 패턴으로 orphan order 방지 (PENDING 상태 + cleanup job) [`@COMP:service,job`] → [docs](features/webhook-order-processing.md#5-phase-32-db-first-orphan-prevention-2025-10-30)
- **error-message-sanitization** - API 에러 메시지 보안 처리 (민감정보 마스킹, 500자 제한) [`@COMP:service`] → [docs](features/webhook-order-processing.md#phase-31-database--security-enhancements-2025-10-30)
- **worktree-conflict-resolution** - Git worktree 환경 서비스 충돌 자동 해결 [`@COMP:util`] → [docs](features/worktree-conflict-resolution.md)
- **circuit-breaker** - 거래소별 연속 실패 제한 및 점진적 복구 [`@COMP:job`] → [docs](features/circuit-breaker.md)
- **health-monitoring** - WebSocket 연결 상태 감시 및 자동 재연결 [`@COMP:service`] → [docs](features/health-monitoring.md)
- **securities-token** - 한국투자증권 토큰 관리 (자동 갱신) [`@COMP:service`] → [docs](features/securities-token.md)

### 📢 Notifications & Admin
- **telegram-notification** - 사용자별/전역 텔레그램 봇 알림 (우선순위 기반 선택, 9가지 알림 타입) [`@COMP:service`] → [docs](features/telegram-notification.md)
- **admin-panel** - Admin 대시보드, 시스템 모니터링, 백그라운드 작업 로그 조회 [`@COMP:route,ui`] → [docs](features/admin-panel.md)

### 🔐 Authentication & Security
- **auth-session** - 세션 기반 인증 시스템 [`@COMP:service,route`] → [docs](features/auth-session.md)
- **webhook-token** - 웹훅 토큰 관리 (복사 버튼, 재발행) [`@COMP:ui-helper`] → [docs](features/webhook-order-processing.md)

---

## Recent Updates (Last 30 Days)

| Date | Feature | Status | Files Changed | Summary |
|------|---------|--------|---------------|---------|
| 2025-10-30 | DB-first Orphan Prevention | ✅ Phase 2 | constants.py, core.py, order_manager.py | PENDING/FAILED 상태 + 120s cleanup job |
| 2025-10-30 | Error Message Sanitization | ✅ Phase 3.1 | models.py, core.py, migrations/ | OpenOrder error_message 필드 + 보안 함수 (고아 주문 방지 기반) |
| 2025-10-30 | Feature Catalog Sync | ✅ Complete | FEATURE_CATALOG.md | 전체 문서 동기화 (코드 기준 최신화) |
| 2025-10-26 | Immediate Order Execution | ✅ Phase 1-7 | order_manager.py, routes/, ui/ | FailedOrder 관리, 웹훅 즉시 실행 |
| 2025-10-26 | Strategy Subscription Safety | ✅ Phase 1-5 | strategy_service.py, routes/, trading/core.py | Cleanup, API, UI, Force liquidation, Race Condition |
| 2025-10-25 | Toast UX Improvement | ✅ Phase 1-2 | realtime-openorders.js, core.py | 단일/배치 Toast 통일 |
| 2025-10-24 | Background Log Tagging | ✅ Phase 3.1 | logging.py, __init__.py | MARKET_INFO 태그 적용 |
| 2025-10-23 | Circuit Breaker | ✅ Phase 2 | order_manager.py | 거래소별 Gradual Recovery |
| 2025-10-23 | Worktree Conflict Resolution | ✅ Complete | run.py | 서비스 충돌 자동 해결 |
| 2025-10-21 | Capital Management | ✅ Phase 4-5 | capital.py, strategies.html | Force 파라미터, UI 이동 |

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
- **Strategy & Analytics** (4): strategy-management, strategy-subscription-safety, analytics, account-management
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

*Last Updated: 2025-10-30*
*Format: C (계층적 축약형) - 인덱스 역할에 충실*
*Total Lines: ~195 (목표 준수)*
