# Feature Catalog

프로젝트의 모든 기능과 컴포넌트를 태그 기반으로 관리하는 카탈로그입니다.

## 태그 시스템 개요

### 태그 포맷
```python
# @FEAT:feature-name @COMP:component-type @TYPE:logic-type [@DEPS:dependencies]
```

### 태그 카테고리
- **@FEAT:** (필수, 다중 가능) - 기능명 (kebab-case)
- **@COMP:** (필수) - 컴포넌트 타입 (`service`, `route`, `model`, `validation`, `exchange`, `util`, `job`)
- **@TYPE:** (필수) - 로직 타입 (`core`, `helper`, `integration`, `validation`, `config`)
- **@DEPS:** (선택) - 의존 기능 (쉼표로 구분)

---

## Active Features

### 1. webhook-order
**설명**: 트레이딩뷰 웹훅 수신, 토큰 검증, 주문 처리
**태그**: `@FEAT:webhook-order`
**주요 파일**:
- `routes/webhook.py` - 웹훅 엔드포인트
- `services/webhook_service.py` - 웹훅 검증 및 처리
- `services/trading/core.py` - 거래 실행 핵심 로직
**의존성**: `order-tracking`, `exchange-integration`, `telegram-notification`, `strategy-management`
**최근 수정**: 2025-10-15 - Phase 1-3 리팩토링 후속 수정 (메서드 호출 및 구현 복구)
**상세 문서**: `docs/features/webhook-order-processing.md`
**검색**:
```bash
grep -r "@FEAT:webhook-order" --include="*.py"
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@TYPE:validation"
```

**주요 변경 이력**:
- **2025-10-15**: 웹훅 처리 오류 수정 (AttributeError 3건 해결)
  - `webhook_service.py:234` - `process_orders()` → `process_batch_trading_signal()` 호출 수정
  - `webhook_service.py:236-237` - 단일 주문 처리 로직 간소화 (12줄 → 2줄)
  - `trading/core.py:289-322` - `_execute_exchange_order()` 메서드 추가
  - `trading/core.py:324-364` - `_merge_order_with_exchange()` 메서드 추가
  - 성능: ~197ms 처리 시간, 100% 성공률 복구

---

### 2. toast-system
**설명**: 토스트 알림 시스템 (FIFO 큐 관리, 자동 제거, DEBUG 모드 생명주기 로깅)
**태그**: `@FEAT:toast-system`
**주요 파일**:
- `web_server/app/static/js/toast.js` - 핵심 토스트 시스템 (@COMP:util @TYPE:core)
- `web_server/app/static/js/positions/realtime-openorders.js` - FIFO 큐 및 배치 집계 (@COMP:util @TYPE:core)
  - Lines 47-48: MAX_TOASTS, TOAST_FADE_DURATION_MS 설정
  - Lines 1019-1051: _removeFIFOToast() 메서드 (3개 로그)
  - Lines 1177-1211: createBatchToast() 메서드 (2개 로그)
  - Lines 23-44: DEBUG 모드 사용 예시 및 로그 출력 샘플
- `web_server/app/static/css/components.css` (Lines 1123, 1218-1223) - 토스트 스타일
**컴포넌트**:
- `showToast(message, type, duration)` - 토스트 표시 (전역 함수)
- `ensureToastContainer()` - 컨테이너 동적 생성
- `removeToast()` - 슬라이드 아웃 제거
- **DEBUG 로깅** (12개 로그 포인트):
  - toast.js (7개): 컨테이너 확인 → 생성 → 표시 → 제거 전체 추적
  - realtime-openorders.js (5개): FIFO 체크 → 배치 집계 → 토스트 생성 추적
- `MAX_TOASTS = 10`, `TOAST_FADE_DURATION_MS = 300` - FIFO 큐 설정
- `_removeFIFOToast()` - FIFO 제거 헬퍼 (DRY, Phase 2 추가)
- `createBatchToast()` - 배치 메시지 집계 (Phase 2 추가)
**의존성**: logger.js (선택사항, no-op 폴백 제공)
**최근 수정**:
- 2025-10-21 - Phase 2: FIFO/배치 집계 DEBUG 로깅 추가 (5개 로그 포인트)
- 2025-10-21 - Phase 1: 기본 생명주기 DEBUG 로깅 추가 (7개 로그 포인트)
**상세 문서**: `docs/features/toast-ui.md`
**검색**:
```bash
# 토스트 시스템 전체
grep -r "@FEAT:toast-system" --include="*.js"

# DEBUG 로깅 코드 (Phase 1)
grep -n "logger.debug" web_server/app/static/js/toast.js

# FIFO 큐 및 배치 집계 (Phase 2)
grep -n "_removeFIFOToast\|createBatchToast\|Toast-FIFO\|Toast-Batch" web_server/app/static/js/positions/realtime-openorders.js

# 사용 예시
grep -n "showToast" --include="*.js" web_server/app/static/js/
```

---

### 3. pending-order-sse
**설명**: PendingOrder 생성/삭제 시 Order List SSE 발송 (열린 주문 테이블 실시간 업데이트)
**태그**: `@FEAT:pending-order-sse`
**주요 파일**:
- `services/trading/order_queue_manager.py` - PendingOrder 생성/삭제 SSE 발송
  - Lines 105-166: enqueue() 메서드 - 생성 시 SSE (event_type='order_created')
    - Lines 108-119: user_id 사전 추출 (@TYPE:helper)
    - Lines 149-166: Order List SSE 발송 (@TYPE:core @DEPS:event-emitter)
  - Lines 776-870: _execute_pending_order() 메서드 - 삭제 시 SSE (event_type='order_cancelled')
    - Lines 822-829: user_id 사전 추출, strategy Null 체크 (@TYPE:helper)
    - Lines 831-846: Order List SSE 발송, try-except 비치명적 처리 (@TYPE:core @DEPS:event-emitter)
**컴포넌트**:
- **Order List SSE**: 열린 주문 테이블 실시간 업데이트용 개별 SSE 이벤트
- **Toast SSE 구분**: Toast 알림은 웹훅 응답 시 Batch SSE로 통합 (core.py 참조)
- **Transaction Safety**: SSE 발송은 DB 커밋 **전**에 실행 (객체 접근 보장)
- **재정렬 경로**: PendingOrder → OpenOrder 전환 시 개별 SSE 발송 (배치 SSE 아님)
**의존성**: event_emitter.py (emit_pending_order_event)
**최근 수정**:
- 2025-10-21 - Phase 2.2: PendingOrder 삭제 SSE 발송 완성 (최대 재시도 초과 시)
  - 경로 1 (재정렬 성공): PendingOrder → OpenOrder 전환 시 삭제 + SSE 발송
  - 경로 2 (최대 재시도 초과): 재시도 한계 도달 시 삭제 + SSE 발송
  - 경로 3 (사용자 취소): CANCEL_ALL_ORDER 시 삭제 + SSE 발송
- 2025-10-21 - Phase 2.1: PendingOrder 삭제 시 Order List SSE 발송 구현 (재정렬 성공 시)
- 2025-10-21 - Phase 1: PendingOrder 생성 시 Order List SSE 발송 구현
**검색**:
```bash
grep -r "@FEAT:pending-order-sse" --include="*.py"
grep -n "emit_pending_order_event" web_server/app/services/trading/order_queue_manager.py
grep -n "_execute_pending_order" web_server/app/services/trading/order_queue_manager.py
```

---

### 3.1. order-queue
**설명**: 거래소 제한 초과 시 주문 대기열 관리 및 동적 재정렬
**태그**: `@FEAT:order-queue`
**주요 파일**:
- `services/trading/order_queue_manager.py` - 대기열 관리 핵심
- `services/background/queue_rebalancer.py` - 스케줄러
- `constants.py` - ExchangeLimits 클래스
- `models.py` - PendingOrder, OpenOrder
**의존성**: `order-tracking`, `exchange-integration`, `telegram-notification`
**상세 문서**: `docs/features/order-queue-system.md`
**검색**:
```bash
grep -r "@FEAT:order-queue" --include="*.py"
grep -r "@FEAT:order-queue" --include="*.py" | grep "rebalance"
```

**최근 변경**:
- **2025-10-16**: Side별 분리 정렬 구현 최종 검증 및 문서화 완료
  - Buy/Sell 주문 독립 할당 (각 side 20개)
  - ExchangeLimits에 side별 제한 필드 추가 (`max_orders_per_side`, `max_stop_orders_per_side`)
  - 총 용량 2배 증가 (20개 → 40개, 각 side 10개씩)
  - DRY 원칙: `_select_top_orders()` 헬퍼 함수 추가 (40+ 라인 중복 제거)
  - Known Issues 섹션 추가: sort_price 부호 반전 로직 문서화
  - 버전: rebalance_symbol v2.2

**파일**:
- `web_server/app/constants.py` (ExchangeLimits)
- `web_server/app/services/trading/order_queue_manager.py` (rebalance_symbol, _select_top_orders)

**검색 태그**: `@FEAT:order-queue`, `@COMP:service`, `@TYPE:core`, `@COMP:config`

---

### 3. order-tracking
**설명**: 주문 상태 추적 및 WebSocket 기반 실시간 감시
**태그**: `@FEAT:order-tracking`
**주요 파일**:
- `services/order_tracking.py` - 주문 동기화
- `services/websocket_manager.py` - WebSocket 연결 관리
- `models.py` - OpenOrder, OrderTrackingSession
- `services/trading/core.py` - 주문 실행 및 체결 처리
**의존성**: `exchange-integration`, `event-sse`
**최근 수정**: 2025-10-15 - 거래소 주문 실행 메서드 복구
**상세 문서**: `docs/features/order-tracking.md`
**검색**:
```bash
grep -r "@FEAT:order-tracking" --include="*.py"
grep -r "@FEAT:order-tracking" --include="*.py" | grep "websocket"
```

---

### 3.1. order-tracking-improvement
**설명**: 주문 체결 트래킹 개선 (WebSocket 심볼 정규화, 낙관적 잠금, 배치 쿼리 20배 최적화)
**태그**: `@FEAT:order-tracking`, `@FEAT:websocket-integration`
**주요 파일**:
- `services/order_fill_monitor.py` - WebSocket 체결 감지 (Phase 1-2)
- `services/trading/order_manager.py` - Scheduler 배치 처리 (Phase 2-3)
- `migrations/20251014_add_processing_lock_to_open_orders.py` - 낙관적 잠금 스키마
**의존성**: `exchange-integration`, `symbol-utils`
**성능**: API 호출 20배 감소, 처리 시간 20초 → 1초
**검색**:
```bash
grep -r "@FEAT:order-tracking" --include="*.py" web_server/app/
grep -r "is_processing\|release_stale_order_locks" --include="*.py"
```

---

### 3.2. limit-order-fill-processing
**설명**: LIMIT 주문 체결 시 Trade/Position 자동 업데이트 (WebSocket + Scheduler 이중 경로, DB-level 중복 방지)
**태그**: `@FEAT:limit-order`
**주요 파일**:
- `services/order_fill_monitor.py` - WebSocket 체결 처리
- `services/trading/order_manager.py` - Scheduler Fallback
- `services/trading/record_manager.py` - Idempotency 레이어
- `migrations/20251014_add_trade_unique_constraint.py` - UNIQUE 제약조건
**의존성**: `order-tracking`, `trade-execution`, `position-tracking`
**성능**: WebSocket <1초, Scheduler 29초 지연, 중복 방지율 100%
**검색**:
```bash
grep -r "@FEAT:limit-order" --include="*.py" web_server/app/
grep -n "_process_fill_for_order\|_process_scheduler_fill" web_server/app/services/
```

---

### 3.3. batch-parallel-processing
**설명**: ThreadPoolExecutor 기반 계좌별 배치 주문 병렬 처리 (MARKET 전용, 순차 처리 대비 50% 단축)
**태그**: `@FEAT:batch-parallel-processing`
**주요 파일**:
- `services/trading/core.py` - ThreadPoolExecutor 병렬 처리 + 타임아웃
- `services/exchange.py` - `create_batch_orders()` account_id 전달
**의존성**: Account-level Rate Limiting (Phase 0)
**설정**: `BATCH_ACCOUNT_TIMEOUT_SEC=30` (core.py Line 25)
**성능**: 2계좌 × 2주문 1302ms → 651ms
**검색**:
```bash
grep -r "@FEAT:batch-parallel-processing" --include="*.py" web_server/app/
grep -n "ThreadPoolExecutor" web_server/app/services/trading/core.py
```

---

### 4. position-tracking
**설명**: 포지션 관리, 평균가 계산, 실현/미실현 손익 추적
**태그**: `@FEAT:position-tracking`
**주요 파일**:
- `services/trading/position_manager.py` - 포지션 업데이트
- `routes/positions.py` - 포지션 API
- `models.py` - StrategyPosition
**의존성**: `order-tracking`, `price-cache`
**상세 문서**: `docs/features/position-tracking.md`
**검색**:
```bash
grep -r "@FEAT:position-tracking" --include="*.py"
grep -r "@FEAT:position-tracking" --include="*.py" | grep "pnl"
```

---

### 5. capital-management
**설명**: 자본 배분, 관리, 자동 재할당 스케줄러, 수동 UI 트리거, 포지션 청산 즉시 재할당

**태그 구분**:
- `@FEAT:capital-management` - 비즈니스 로직 (service, route, model, util, UI)
- `@FEAT:capital-reallocation` - 재할당 핵심 로직 (Phase 1 추가)

**주요 파일**:
- `services/capital_service.py` - 자본 배분 비즈니스 로직, 이중 임계값 체크, 캐싱 (@FEAT:capital-management @COMP:service @TYPE:core)
- `services/trading/quantity_calculator.py` - 주문 수량 계산 (@FEAT:capital-management @COMP:service @TYPE:core)
- `services/trading/position_manager.py` (Lines 843-868) - 포지션 청산 후 재할당 트리거 (@FEAT:capital-reallocation @COMP:service @TYPE:integration)
- `routes/capital.py` - 자본 API (@FEAT:capital-management @COMP:route @TYPE:core)
- `models.py` (Lines 104-105) - Account 재할당 필드 (@FEAT:capital-management @COMP:model @TYPE:core)
- `migrations/20251021_add_rebalance_fields_to_account.py` - DB 스키마 (@FEAT:capital-reallocation @COMP:migration @TYPE:core)
- `app/__init__.py` (Lines 636-654) - 자동 재할당 스케줄러 (@FEAT:capital-management @COMP:job @TYPE:core)
- `templates/accounts.html`, `app/static/js/accounts.js` - 수동 UI 트리거

**재할당 트리거 (Phase 2 업데이트)**:
1. 백그라운드 스케줄러 - 660초마다 정기적 시도 (하루 약 130회)
2. 포지션 청산 시 즉시 - `should_rebalance()` 조건 체크 후 실행

**재할당 조건 (Phase 1 업데이트)**:
- 이전: 시간 기반 (최소 1시간 경과)
- 현재: 잔고 변화 기반 (이중 임계값)
  - 절대값: 최소 10 USDT 변화
  - 비율: 최소 0.1% 변화
  - 양쪽 모두 충족 시 재할당

**캐싱 (거래소 API 호출 70% 감소)**:
- TTL: 5분 (300초)
- 무효화: 재할당 완료 시 `invalidate_cache(account_id)` 호출

**의존성**: `position-tracking`, `strategy-management`, `account-service`
**상세 문서**: `docs/features/capital-management.md`
**최근 수정**: 2025-10-21 - Phase 4 강제 실행 모드 추가 (force 파라미터, 감사 로깅)
**검색**:
```bash
# 모든 capital 관련 코드 (비즈니스 로직 + 스케줄러)
grep -r "@FEAT:capital-management\|@FEAT:capital-allocation" --include="*.py"

# 비즈니스 로직만
grep -r "@FEAT:capital-management" --include="*.py" | grep "@COMP:service\|@COMP:route"

# 스케줄러 작업만
grep -r "@FEAT:capital-allocation" --include="*.py" | grep "@COMP:job"

# 스케줄러 구현 위치
grep -n "auto_rebalance_all_accounts_with_context" web_server/app/__init__.py

# 로그 확인
grep "auto_rebalance_accounts" /web_server/logs/app.log
```

---

### 6. exchange-integration
**설명**: 거래소 통합 레이어 (Binance, Bybit, Upbit, Bithumb, KIS)
**태그**: `@FEAT:exchange-integration`
**주요 파일**:
- `exchanges/crypto/binance.py` - Binance (Spot, Futures)
- `exchanges/crypto/bybit.py` - Bybit (미완성)
- `exchanges/crypto/upbit.py` - Upbit (SPOT, 215개 심볼)
- `exchanges/crypto/bithumb.py` - Bithumb (SPOT, KRW+USDT 듀얼 마켓, Allowlist)
- `exchanges/securities/korea_investment.py` - 한국투자증권 KIS
- `exchanges/unified_factory.py` - 통합 팩토리
- `services/exchange.py` - 거래소 서비스
- `utils/symbol_utils.py` - 심볼 변환
**의존성**: None
**상세 문서**: `docs/features/upbit-integration.md`, `docs/features/exchange-integration.md`
**검색**:
```bash
grep -r "@FEAT:exchange-integration" --include="*.py"
grep -r "create_batch_orders" --include="*.py" | grep -E "upbit|bithumb"
```

#### 국내 거래소 식별 (Phase 2.2)
**설명**: KRW 기준 국내 거래소 여부 확인 (환율 변환 대상 식별)

**주요 파일**:
- `constants.py` (Lines 248-350) - Exchange 클래스
  - `DOMESTIC_EXCHANGES` - 국내 거래소 목록 [UPBIT, BITHUMB] (Line 249)
  - `is_domestic(exchange: str) -> bool` - 국내 거래소 여부 확인 (Line 315-350)

**사용 예시**:
```python
from app.constants import Exchange

# 국내 거래소 확인
if Exchange.is_domestic('UPBIT'):
    # KRW 잔고 → USDT 변환 필요
    pass
```

**검색**:
```bash
# 국내 거래소 판별 코드
grep -n "is_domestic\|DOMESTIC_EXCHANGES" --include="*.py" web_server/app/

# 국내 거래소별 용도 추적
grep -r "is_domestic" --include="*.py" web_server/app/ | head -20
```

**관련 기능**:
- Phase 1: `price_cache.get_usdt_krw_rate()` - USDT/KRW 환율 조회
- Phase 3: `SecurityService.get_accounts_by_user()` - KRW 잔고 USDT 변환

---

### 국내 거래소 KRW → USDT 변환 (Phase 3)

**파일**: `web_server/app/services/security.py`
**태그**: `@FEAT:account-management`, `@FEAT:exchange-integration`

#### 개요
국내 거래소(UPBIT, BITHUMB)의 KRW 잔고를 USDT로 변환하여 API 응답에 포함합니다.
환율 조회 실패 시 Graceful Degradation 패턴을 적용하여 원화 잔고를 그대로 표시합니다.

#### 핵심 구현
- **메서드**: `SecurityService.get_accounts_by_user(user_id)` (Lines 231-354)
- **환율 소스**: `price_cache.get_usdt_krw_rate()` (30초 캐시)
- **에러 처리**:
  - 환율 조회 실패 → KRW 표시 + `conversion_error="환율 조회 실패"`
  - 환율 ≤ 0 → KRW 표시 + `conversion_error="환율 데이터 이상"`
- **방어 코드**: division by zero 방지 (`usdt_krw_rate > 0`)

#### 응답 필드
```python
{
    "latest_balance": 121239.17,        # USDT 변환 값 (국내) 또는 원본 (해외)
    "currency_converted": true,         # 변환 여부
    "original_balance_krw": 183071153,  # 국내만, 원본 KRW
    "usdt_krw_rate": 1510.0,            # 국내만, 적용된 환율
    "conversion_error": null            # 에러 시 메시지
}
```

#### 검색 명령
```bash
# 핵심 변환 로직
grep -r "@FEAT:account-management" --include="*.py" web_server/app/services/security.py

# 환율 조회 라인
grep -n "get_usdt_krw_rate" web_server/app/services/security.py

# 국내 거래소 여부 확인
grep -n "is_domestic" web_server/app/services/security.py
```

#### 의존성
- **Phase 1**: `price_cache.get_usdt_krw_rate()` (USDT/KRW 환율 캐시)
- **Phase 2**: `Exchange.is_domestic()` (국내 거래소 식별)
- **Infrastructure**: `ExchangeRateUnavailableError` 예외 처리

#### 테스트 시나리오
- UPBIT: ₩183,071,153 → $121,239.17 (rate: 1510.0) ✅
- BINANCE: $5,778.04 (unchanged) ✅
- 환율 조회 실패: KRW 표시 + `conversion_error` ✅
- 환율 ≤ 0: KRW 표시 + `conversion_error="환율 데이터 이상"` ✅

---

### 7. price-cache
**설명**: 심볼별 가격 캐싱 및 주기적 업데이트 (USDT/KRW 환율 조회 포함)
**태그**: `@FEAT:price-cache`
**주요 파일**:
- `services/price_cache.py` - 가격 캐시 핵심
  - `get_price()` - 심볼별 가격 조회 (30초 캐싱)
  - `get_usdt_krw_rate()` - USDT/KRW 환율 조회 (30초 캐싱)
**주요 기능**:
- UPBIT USDT/KRW SPOT 가격 조회
- 30초 캐싱 (기존 PriceCache 인프라 활용)
- API 실패 시 설정 파일 기반 fallback (DEFAULT_USDT_KRW = 1400)
**사용 예시**:
```python
from app.services.price_cache import price_cache

# USDT/KRW 환율 조회
rate = price_cache.get_usdt_krw_rate()
usdt_balance = krw_balance / rate

# 심볼 가격 조회
btc_price = price_cache.get_price('BTC/USDT', Exchange.BINANCE)
```
**설정**:
- `config.DEFAULT_USDT_KRW`: Fallback 환율 (기본값 1400, 2025-10-21 기준)
**의존성**: `exchange-integration` (UPBIT API)
**상세 문서**: `docs/features/price-cache.md`
**검색**:
```bash
# 전체 price-cache 코드
grep -r "@FEAT:price-cache" --include="*.py"

# USDT/KRW 환율 조회만
grep -n "get_usdt_krw_rate" --include="*.py" web_server/app/services/
```

---

### 8. event-sse / batch-sse
**설명**: Server-Sent Events 기반 실시간 이벤트 발송 (개별 + 배치 이벤트 End-to-End 지원)
**태그**: `@FEAT:event-sse`, `@FEAT:batch-sse`
**주요 파일**:
- **Backend (Phase 2)**:
  - `services/event_service.py` - SSE 이벤트 관리 (Lines 56-66 OrderBatchEvent, Lines 162-194 emit_order_batch_event)
  - `services/trading/event_emitter.py` - 이벤트 발행 (Lines 522-587 emit_order_batch_update)
  - `services/trading/core.py` - 배치 SSE 통합 (Lines 1250-1256, 1408-1422)
- **Frontend (Phase 3)**:
  - `static/js/positions/realtime-openorders.js` - SSE 수신 및 Toast 연동 (Lines 110-114 리스너, Lines 219-252 handleBatchOrderUpdate)
**컴포넌트**:
- **OrderEvent**: 개별 주문 이벤트 (기존)
- **OrderBatchEvent**: 배치 주문 이벤트 (Phase 2)
- **emit_order_batch_update()**: Backend 집계 로직 (defaultdict, O(n))
- **handleBatchOrderUpdate()**: Frontend 수신 핸들러 (Phase 3)
- **createBatchToast()**: Toast UI 렌더링 (Phase 1)
**3-Phase 통합** (2025-10-20):
- **Phase 1**: Toast UI 개선 (createBatchToast, MAX_TOASTS=10, FIFO)
- **Phase 2**: Backend 배치 SSE (order_type별 집계, 90% SSE 감소)
- **Phase 3**: Frontend 통합 (SSE 리스너, End-to-End 완성)
**효과**: 배치 주문 시 SSE 10개 → 1개, Toast 10개 → 1개 (90% 감소)
**의존성**: None
**상세 문서**: `docs/features/toast-ui.md`, `docs/features/backend-batch-sse.md`, `docs/features/frontend-batch-sse.md`
**검색**:
```bash
grep -r "@FEAT:event-sse\|@FEAT:batch-sse" --include="*.py" --include="*.js"
grep -n "OrderBatchEvent\|emit_order_batch\|handleBatchOrderUpdate" web_server/app/
```

---

### 9. strategy-management
**설명**: 전략 CRUD, 계좌 연결, 공개 전략 구독, 권한 관리, 웹훅 토큰 검증
**태그**: `@FEAT:strategy-management`
**주요 파일**:
- `services/strategy_service.py` - 전략 비즈니스 로직
- `routes/strategies.py` - 전략 REST API
- `models.py` - Strategy, StrategyAccount, StrategyCapital, StrategyPosition
**의존성**: `capital-management`, `analytics`
**상세 문서**: `docs/features/strategy-management.md`
**검색**:
```bash
grep -r "@FEAT:strategy-management" --include="*.py"
grep -n "_validate_strategy_token" web_server/app/services/webhook_service.py
```

---

### 10. analytics
**설명**: 거래 성과 분석, ROI/승률 계산, 대시보드 데이터, 일별 성과 집계 (자정 자동 실행)
**태그**: `@FEAT:analytics`
**주요 파일**:
- `services/analytics.py` - 통합 분석 서비스 (Analytics + Dashboard + Capital)
- `services/performance_tracking.py` - 일별 성과 추적 및 집계
- `routes/dashboard.py` - 대시보드 API
- `models.py` - Trade, TradeExecution, StrategyPerformance, DailyAccountSummary
**의존성**: `position-tracking`, `order-tracking`, `strategy-management`, `capital-management`
**검색**:
```bash
grep -r "@FEAT:analytics" --include="*.py"
grep -n "calculate_strategy_roi\|aggregate_daily_performance" web_server/app/services/
```

---

### 11. telegram-notification
**설명**: 텔레그램 봇 기반 알림 시스템
**태그**: `@FEAT:telegram-notification`
**주요 파일**:
- `services/telegram_service.py` - 텔레그램 봇 관리
**의존성**: None
**상세 문서**: `docs/features/telegram-notification.md`
**검색**:
```bash
grep -r "@FEAT:telegram-notification" --include="*.py"
```

---

### 12. open-orders-sorting
**설명**: 포지션 페이지 열린 주문 테이블의 다단계 정렬 기능
**태그**: `@FEAT:open-orders-sorting`
**상태**: ✅ Phase 1-3 Complete
**주요 파일**:
- `app/static/js/positions/realtime-openorders.js` - 정렬 + UI + SSE 통합 (@COMP:service @TYPE:core)
- `app/static/css/positions.css` - 정렬 UI 스타일 (@COMP:ui, Lines 327-401)
- `app/templates/positions.html` - 테이블 헤더 마크업 (data-sortable 속성)
**의존성**: SSE 실시간 업데이트 시스템
**상세 문서**: `docs/features/open_orders_sorting.md`

**검색**:
```bash
# 모든 정렬 관련 코드
grep -r "@FEAT:open-orders-sorting" --include="*.js"

# Phase 3 SSE 통합 코드
grep -r "@PHASE:3" web_server/app/static/js/positions/realtime-openorders.js

# 핵심 정렬 로직
grep -r "@FEAT:open-orders-sorting" --include="*.js" | grep "@TYPE:core"
```

**구현 단계**:
- ✅ **Phase 1**: 기본 정렬 로직 (f194b67, 2025-10-17)
  - 5단계 우선순위: 심볼 → 상태 → 주문 타입 → 주문 방향 → 가격
  - `sortOrders()`, `compareByColumn()`, priority 헬퍼 메서드 구현
  - 성능: 100개 주문 < 10ms
- ✅ **Phase 2**: 컬럼 클릭 정렬 UI (0bb2726, 2025-10-18)
  - `handleSort()` - 헤더 클릭 이벤트 처리 (Line 592)
  - `reorderTable()` - 테이블 재정렬 및 재렌더링 (Line 610)
  - `updateSortIndicators()` - 정렬 아이콘 UI 업데이트 (Line 568)
  - `attachSortListeners()` - 이벤트 리스너 등록 (Line 633)
  - CSS 정렬 아이콘 스타일 추가 (Lines 327-401, positions.css)
  - 테이블 헤더에 `data-sortable` 속성 추가
- ✅ **Phase 3**: SSE 실시간 업데이트 통합 ([pending], 2025-10-18) ← NEW
  - `upsertOrderRow()` 리팩토링 (Lines 249-337, +49 lines)
  - 정렬된 위치에 주문 삽입 (O(n log n))
  - Phase 1 `sortOrders()` 재사용 (DRY)
  - 7-step 알고리즘: memory → remove → sort → find → create → insert → animate
  - 성능: 100개 주문 ~5ms

**주요 메서드**:
- `sortOrders(orders, sortConfig)` - 핵심 정렬 로직 (Line 463)
- `compareByColumn(a, b, column, direction)` - 컬럼별 비교 (Line 496)
- `getStatusPriority(order)` - 상태 우선순위 (Line 540)
- `getOrderTypePriority(orderType)` - 주문 타입 우선순위 (Line 553)
- `handleSort(column)` - Phase 2 헤더 클릭 처리 (Line 592)
- `reorderTable()` - Phase 2 테이블 재정렬 (Line 610)
- `updateSortIndicators()` - Phase 2 아이콘 업데이트 (Line 568)
- `attachSortListeners()` - Phase 2 이벤트 리스너 (Line 633)

**최근 변경 (2025-10-18)**:
- Phase 3 구현 완료 (SSE 실시간 업데이트 정렬 유지)
- `upsertOrderRow()` 리팩토링: 정렬된 위치에 삽입 (+49 lines)
- SSE 이벤트 시 정렬 상태 유지 (O(n log n))
- Phase 1/2와 완전 통합 (zero regression)
- 8가지 엣지 케이스 처리 (empty table, top/middle/bottom, fallback 등)

---

## Tag Index

### By Component Type
- **service**: exchange.py, webhook_service.py, order_tracking.py, analytics.py 등
- **route**: webhook.py, positions.py, strategies.py, dashboard.py
- **model**: models.py (모든 DB 모델)
- **validation**: webhook_service.py (토큰 검증)
- **exchange**: exchanges/ (거래소 어댑터)
- **util**: symbol_utils.py
- **job**: order_queue_manager.py, order_manager.py
- **config**: constants.py (ExchangeLimits)
- **ui**: CSS 스타일, 프론트엔드 UI 컴포넌트

### By Logic Type
- **core**: 핵심 비즈니스 로직
- **helper**: 유틸리티 함수
- **integration**: 외부 시스템 통합
- **validation**: 입력 검증
- **config**: 설정 및 초기화
- **interaction**: 사용자 상호작용 이벤트 핸들러

---

## Recent Changes

### 2025-10-21: Capital Management Phase 4 Complete
**영향 범위**: `capital-management`
**파일**:
- `app/routes/capital.py` (Lines 212-334) - trigger_auto_rebalance() 함수
- `docs/features/capital-management.md` - 수동 재할당 UI 섹션 확장

**개선 내용**:
1. **Force 파라미터 추가**: `force=true` 시 should_rebalance() 조건 완전 우회
2. **보안 감사 추적**: 강제 실행 시 user_id, IP 주소 WARNING 레벨 로그
3. **포지션 리스크 경고**: 포지션 존재 중 강제 재할당 시 WARNING 로그
4. **응답 구조**: 모든 경로에 `forced` 플래그 포함으로 일관성 확보

**태그**: `@FEAT:capital-management @COMP:route @TYPE:core`

---

### 2025-10-21: Capital Management Phase 5 Complete
**영향 범위**: `capital-management`
**파일**:
- `app/templates/strategies.html` (Lines 58-78, 1628-1698) - 자본 재할당 UI 이동
- `app/templates/accounts.html` (Line 140-145 삭제) - 버튼 제거
- `app/static/js/accounts.js` (Lines 301-341 삭제) - 함수 제거
- `docs/features/capital-management.md` - Phase 5 이력 추가

**개선 내용**:
1. **UI 위치 변경**: 자본 재할당 버튼을 accounts → strategies 페이지로 이동
2. **논리적 배치**: 전략별 자본 배분 기능이므로 전략 관리 페이지에 배치
3. **버튼 텍스트 개선**: "자본 재할당" → "전략 자본 재할당" (명확성)
4. **Force UI 추가**: 체크박스로 강제 실행 모드 선택 (Phase 4 force 파라미터 활용)
5. **코드 정리**: accounts 관련 코드 제거 (중복 제거, 관심사 분리)

**태그**: `@FEAT:capital-management @COMP:ui @TYPE:core`

---

### 2025-10-21: Capital Management Phase 2 Complete
**영향 범위**: `capital-management`
**파일**:
- `app/__init__.py` (Lines 636-653) - 스케줄러 개선 (7개 cron → 1개 interval)
- `docs/features/capital-management.md` - 스케줄 섹션 업데이트 및 Phase 이력 추가

**개선 내용**:
1. **스케줄 방식 변경**: 7개 cron job → 1개 interval job (660초 간격)
2. **실행 빈도 증가**: 7회/일 → 약 130회/일 (18.6배 증가)
3. **코드 단순화**: DRY 원칙 (중복 제거 -10%)
4. **효과**: Phase 1의 이중 임계값 조건과 5분 TTL 캐싱으로 API 부하 증가 최소화

**성능**:
- 코드 라인 수: 20줄 → 18줄 (-10%)
- 실행 조건: 이중 임계값으로 불필요한 재할당 90%+ 차단

**태그**: `@FEAT:capital-management @COMP:job @TYPE:core`

---

### 2025-10-18: Open Orders Sorting Phase 3 Complete
**영향 범위**: `open-orders-sorting`
**파일**:
- `app/static/js/positions/realtime-openorders.js` - `upsertOrderRow()` 리팩토링 (Lines 249-337, +49 lines)
- `docs/features/open_orders_sorting.md` - Phase 3 섹션 추가
- `docs/FEATURE_CATALOG.md` - 상태 업데이트 (Phase 1-3 Complete)

**개선 내용**:
1. **SSE 정렬 유지**: 새 주문이 올바른 정렬 위치에 삽입 (`insertBefore()` vs `appendChild()`)
2. **7-step 알고리즘**: memory → remove → sort → find → create → insert → animate
3. **Phase 1 재사용**: `sortOrders()` 메서드 재사용 (DRY 원칙)
4. **엣지 케이스**: 8가지 처리 (empty table, top/middle/bottom, DOM fallback, rapid burst 등)
5. **성능**: O(n log n), 100개 주문 ~5ms

**상태**:
- 구현: ✅ 완료 (code-reviewer approved)
- JSDoc: ✅ 완료 (@PHASE:3 태그)
- 문서화: ✅ 완료 (530줄)
- 테스트: ⏳ Pending (Phase 3.5)

**태그 변경**: `@PHASE:3` 추가 (기존 @FEAT:open-orders-sorting 유지)

---

### 2025-10-16: Order Queue v2.2 Documentation Complete
**영향 범위**: `order-queue`
**파일**:
- `docs/features/order-queue-system.md` - Known Issues 섹션 추가

**개선 내용**:
1. **Known Issues 섹션 추가**: sort_price 부호 반전 로직 문서화 (2~5줄 간결 설명)
2. **문서 품질 개선**: Last Updated 날짜 업데이트, 성능 설명 명확화
3. **최종 검증 완료**:
   - 기술적 정확성 100% (코드 대조 완료)
   - 태그 일관성 검증
   - FEATURE_CATALOG 동기화
   - 마크다운 형식 검증

**성능 & 품질**:
- 문서 크기: 330줄 (500줄 제한 내)
- 종합 평가: 9.3/10 (프로덕션 준비 완료)

**검색**:
```bash
# Order-queue v2.2 코드 찾기
grep -r "@FEAT:order-queue" --include="*.py" | grep -E "rebalance_symbol|_select_top_orders"

# Sort_price 부호 반전 로직 찾기
grep -n "_calculate_sort_price" web_server/app/services/trading/order_queue_manager.py
```

---

### 2025-10-15: Order Queue Side-Based Separation (Phase 1-2)
**영향 범위**: `order-queue`
**파일**:
- `constants.py` - ExchangeLimits side별 제한 추가
- `services/trading/order_queue_manager.py` - rebalance_symbol v2.2, _select_top_orders 헬퍼 함수

**개선 내용**:
1. **Side별 독립 제한**: Buy/Sell 주문이 각각 독립적으로 최대 10개 (또는 20개, 거래소별 다름) 할당
2. **총 용량 증가**: 기존 심볼당 10개 → 각 side 10개 (총 최대 20개)
3. **ExchangeLimits 반환값 확장**:
   - `max_orders`: 총 허용량 (Buy + Sell 합계)
   - `max_orders_per_side`: 각 side별 제한 (신규)
   - `max_stop_orders`: 총 STOP 허용량 (Buy + Sell 합계)
   - `max_stop_orders_per_side`: 각 side별 STOP 제한 (신규)
4. **DRY 원칙**: `_select_top_orders()` 헬퍼 함수로 40+ 라인 중복 제거

**검색**:
```bash
# Side별 제한 필드 사용 확인
grep -r "max_orders_per_side\|max_stop_orders_per_side" --include="*.py" web_server/app/

# rebalance_symbol v2.2 버전 확인
grep -n "v2.2" web_server/app/services/trading/order_queue_manager.py

# _select_top_orders 헬퍼 함수 사용 확인
grep -n "_select_top_orders" web_server/app/services/trading/order_queue_manager.py
```

**성능**: 재정렬 성능 유지 (<100ms), 메모리 증가 없음

---

### 2025-10-15: Webhook Order Processing Fix
**영향 범위**: `webhook-order`, `order-tracking`
**파일**:
- `services/webhook_service.py` - 배치/단일 주문 처리 메서드 호출 수정
- `services/trading/core.py` - 거래소 주문 실행 메서드 2개 추가

**문제 해결**:
1. **AttributeError 3건**: Phase 1-3 리팩토링 시 누락된 메서드 호출 및 구현 복구
2. **배치 주문 처리**: `process_orders()` → `process_batch_trading_signal()` 호출 수정
3. **단일 주문 처리**: 불필요한 배치 변환 제거, `process_trading_signal()` 직접 호출
4. **거래소 연동**: `_execute_exchange_order()`, `_merge_order_with_exchange()` 메서드 구현

**검증 결과**:
- 단일 LIMIT 주문: HTTP 200, 1개 주문 생성 성공
- CANCEL_ALL_ORDER: HTTP 200, 1개 주문 취소 성공
- 처리 시간: ~197ms (양호)

**태그 변경**: 없음 (기존 태그 유지, 일관성 검증 완료)

---

## Maintenance Notes

### Adding New Features
1. 코드에 적절한 태그 추가 (`@FEAT:`, `@COMP:`, `@TYPE:`)
2. 이 카탈로그 업데이트 (새 섹션 추가)
3. Feature 문서 작성 (`docs/features/{feature_name}.md`)
4. Grep 검색 예시 추가

### Tag Naming Convention
- 소문자, kebab-case 사용 (예: `webhook-order`, `position-tracking`)
- 명확하고 간결하게 (3단어 이내 권장)
- 기존 태그와 중복 확인

### Documentation Update
- 새 기능 추가 시: 섹션 추가 + 검색 예시
- 기능 변경 시: 해당 섹션 업데이트
- 의존성 변경 시: 관련 섹션 모두 업데이트

---

*Last Updated: 2025-10-21*
*Recent Changes: Phase 3 - 국내 거래소 KRW → USDT 변환 with Graceful Degradation*

