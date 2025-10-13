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
**설명**: 트레이딩뷰 웹훅 수신 및 주문 처리
**태그**: `@FEAT:webhook-order`
**주요 컴포넌트**:
- **Route**: `web_server/app/routes/webhook.py` - 웹훅 엔드포인트
- **Service**: `web_server/app/services/webhook_service.py` - 웹훅 검증 및 처리
- **Validation**: 토큰 검증, 파라미터 검증

**의존성**: `order-tracking`, `exchange-integration`, `telegram-notification`, `strategy-management`

**검색 예시**:
```bash
# 모든 웹훅 관련 코드
grep -r "@FEAT:webhook-order" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@TYPE:core"

# 검증 로직만
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@TYPE:validation"

# strategy-management와의 통합 지점
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@FEAT:strategy-management"
```

---

### 2. order-queue
**설명**: 거래소 제한 초과 시 주문 대기열 관리 및 동적 재정렬
**태그**: `@FEAT:order-queue`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/trading/order_queue_manager.py` - 대기열 관리 핵심
- **Job**: `web_server/app/services/background/queue_rebalancer.py` - 스케줄러
- **Model**: `web_server/app/models.py` - PendingOrder, OpenOrder

**의존성**: `order-tracking`, `exchange-integration`, `telegram-notification`

**검색 예시**:
```bash
# 대기열 관련 모든 코드
grep -r "@FEAT:order-queue" --include="*.py"

# 재정렬 로직
grep -r "@FEAT:order-queue" --include="*.py" | grep "rebalance"

# 텔레그램 알림 통합
grep -r "@FEAT:order-queue" --include="*.py" | grep "@FEAT:telegram-notification"
```

---

### 3. order-tracking
**설명**: 주문 상태 추적 및 WebSocket 기반 실시간 감시
**태그**: `@FEAT:order-tracking`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/order_tracking.py` - 주문 동기화
- **Service**: `web_server/app/services/websocket_manager.py` - WebSocket 연결 관리
- **Model**: `web_server/app/models.py` - OpenOrder, OrderTrackingSession

**의존성**: `exchange-integration`, `event-sse`

**검색 예시**:
```bash
# 주문 추적 관련 코드
grep -r "@FEAT:order-tracking" --include="*.py"

# WebSocket 통합
grep -r "@FEAT:order-tracking" --include="*.py" | grep "websocket"
```

---

### 4. position-tracking
**설명**: 포지션 관리, 평균가 계산, 실현/미실현 손익 추적
**태그**: `@FEAT:position-tracking`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/trading/position_manager.py` - 포지션 업데이트
- **Model**: `web_server/app/models.py` - StrategyPosition
- **Route**: `web_server/app/routes/positions.py` - 포지션 API

**의존성**: `order-tracking`, `price-cache`

**검색 예시**:
```bash
# 포지션 관련 코드
grep -r "@FEAT:position-tracking" --include="*.py"

# PnL 계산
grep -r "@FEAT:position-tracking" --include="*.py" | grep "pnl"
```

---

### 5. capital-management
**설명**: 자본 배분 및 관리
**태그**: `@FEAT:capital-management`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/analytics.py` - 자본 관리 (통합됨)
- **Route**: `web_server/app/routes/capital.py` - 자본 API

**의존성**: `position-tracking`, `strategy-management`

**검색 예시**:
```bash
# 자본 관리 코드
grep -r "@FEAT:capital-management" --include="*.py"

# analytics와의 통합 지점
grep -r "@FEAT:analytics" --include="*.py" | grep "@FEAT:capital-management"
```

---

### 6. exchange-integration
**설명**: 거래소 통합 레이어 (Binance, Bybit, KIS)
**태그**: `@FEAT:exchange-integration`
**주요 컴포넌트**:
- **Exchange**: `web_server/app/exchanges/` - 거래소 어댑터
  - `crypto/binance.py` - Binance 구현
  - `crypto/bybit.py` - Bybit 구현 (미완성)
  - `securities/korea_investment.py` - 한국투자증권
  - `unified_factory.py` - 통합 팩토리
- **Service**: `web_server/app/services/exchange.py` - 거래소 서비스

**의존성**: None

**검색 예시**:
```bash
# 거래소 통합 코드
grep -r "@FEAT:exchange-integration" --include="*.py"

# Binance 특화
grep -r "@FEAT:exchange-integration" --include="*.py" | grep "binance"
```

---

### 7. price-cache
**설명**: 심볼별 가격 캐싱 및 주기적 업데이트
**태그**: `@FEAT:price-cache`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/price_cache.py` - 가격 캐시

**의존성**: `exchange-integration`

**검색 예시**:
```bash
grep -r "@FEAT:price-cache" --include="*.py"
```

---

### 8. event-sse
**설명**: Server-Sent Events 기반 실시간 이벤트 발송
**태그**: `@FEAT:event-sse`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/event_service.py` - SSE 이벤트 관리
- **Service**: `web_server/app/services/trading/event_emitter.py` - 이벤트 발행

**의존성**: None

**검색 예시**:
```bash
grep -r "@FEAT:event-sse" --include="*.py"
```

---

### 9. strategy-management
**설명**: 전략 CRUD, 계좌 연결, 공개 전략 구독, 권한 관리
**태그**: `@FEAT:strategy-management`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/strategy_service.py` - 전략 비즈니스 로직
- **Route**: `web_server/app/routes/strategies.py` - 전략 REST API
- **Model**: `web_server/app/models.py` - Strategy, StrategyAccount, StrategyCapital, StrategyPosition

**의존성**: `capital-management` (자본 자동 배분), `analytics` (성과 조회)

**핵심 기능**:
1. **전략 CRUD**: 생성, 조회, 수정, 삭제
2. **계좌 연결 관리**: 전략-계좌 연결, 해제, 설정 변경
3. **공개 전략 구독**: is_public=True인 전략을 다른 사용자가 구독 가능
4. **전략 격리**: 동일 계좌의 여러 전략 주문/포지션 분리
5. **웹훅 토큰 검증**: 소유자 + 구독자 토큰 검증
6. **성과 조회**: ROI, 승률, 일일 성과 API

**상세 문서**: [strategy-management.md](./features/strategy-management.md)

**검색 예시**:
```bash
# 전략 관리 모든 코드
grep -r "@FEAT:strategy-management" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@TYPE:core"

# 검증 로직만
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@TYPE:validation"

# 웹훅 통합 지점
grep -r "@FEAT:webhook-order" --include="*.py" | grep "strategy"

# 전략 토큰 검증
grep -n "_validate_strategy_token" web_server/app/services/webhook_service.py

# analytics 통합 (성과 조회)
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@FEAT:analytics"
```

---

### 10. analytics
**설명**: 거래 성과 분석, ROI 계산, 리스크 메트릭, 대시보드 데이터 제공
**태그**: `@FEAT:analytics`

**주요 컴포넌트**:
- **Service**: `web_server/app/services/analytics.py` - 통합 분석 서비스 (Analytics + Dashboard + Capital 통합)
- **Service**: `web_server/app/services/performance_tracking.py` - 일별 성과 추적 및 집계
- **Route**: `web_server/app/routes/dashboard.py` - 대시보드 API
- **Route**: `web_server/app/routes/strategies.py` - 전략 성과 API (일부)
- **Model**: `web_server/app/models.py` - Trade, TradeExecution, StrategyPerformance, DailyAccountSummary

**의존성**: `position-tracking`, `order-tracking`, `strategy-management`, `capital-management`

**핵심 기능**:

1. **대시보드 데이터 제공**:
   - `get_dashboard_summary()` - 요약 정보 (전략/계좌/포지션/주문 수)
   - `get_user_dashboard_stats()` - 전체 통계 (전략별 상세 포함, N+1 최적화)
   - `get_recent_activities()` - 최근 활동 내역
   - `get_user_recent_trades()` - 최근 거래 내역 (TradeExecution 기반)

2. **전략 성과 분석**:
   - `get_strategy_performance()` - 전략별 성과 분석 (기간별)
   - `calculate_roi()` - 투입자본 대비 ROI 계산
   - `get_performance_summary()` - 성과 요약 (최근 N일)
   - `calculate_daily_performance()` - 일일 성과 계산 및 저장

3. **리스크 메트릭**:
   - Sharpe Ratio (샤프 비율)
   - Sortino Ratio (소르티노 비율)
   - Max Drawdown (최대 낙폭, MDD)
   - Volatility (변동성)
   - Profit Factor (손익비)

4. **리포트 생성**:
   - `generate_monthly_report()` - 월간 리포트
   - `get_pnl_history()` - 손익 이력
   - `get_trading_statistics()` - 거래 통계

5. **자본 관리 (통합)**:
   - `get_capital_overview()` - 자본 현황 개요
   - `auto_allocate_capital_for_account()` - 마켓 타입별 자본 자동 할당

6. **N+1 쿼리 최적화**:
   - `_bulk_load_strategy_accounts()` - StrategyAccount 벌크 로딩
   - `_bulk_load_positions()` - StrategyPosition 벌크 로딩
   - `_bulk_load_trades()` - Trade 벌크 로딩
   - 메모리 집계로 DB 왕복 최소화 (10배 이상 성능 향상)

**성과 지표 계산 공식**:
```
ROI = (총 실현 손익 / 투입 자본) × 100%
승률 = (수익 거래수 / 전체 거래수) × 100%
손익비 = 총 수익 / 총 손실
MDD = (고점 - 저점) / 고점 × 100%
Sharpe Ratio = (평균 수익률 / 변동성) × √252
Sortino Ratio = (평균 수익률 / 하방 편차) × √252
```

**상세 문서**: [analytics.md](./features/analytics.md)

**검색 예시**:
```bash
# analytics 기능의 모든 코드
grep -r "@FEAT:analytics" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:analytics" --include="*.py" | grep "@TYPE:core"

# 헬퍼 함수만
grep -r "@FEAT:analytics" --include="*.py" | grep "@TYPE:helper"

# 전략 관리와 analytics 통합 지점 (성과 조회 API)
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@FEAT:analytics"

# 자본 관리와 analytics 통합 지점
grep -r "@FEAT:analytics" --include="*.py" | grep "@FEAT:capital-management"

# position-tracking과 analytics 통합 (미실현 손익)
grep -r "@FEAT:analytics" --include="*.py" | grep "unrealized_pnl"

# ROI 계산 로직
grep -rn "calculate_roi" web_server/app/services/

# Sharpe Ratio 계산
grep -rn "sharpe_ratio" web_server/app/services/

# MDD 계산
grep -rn "drawdown" web_server/app/services/

# 벌크 로딩 헬퍼
grep -rn "_bulk_load" web_server/app/services/analytics.py

# 최근 거래 조회 (TradeExecution 기반)
grep -rn "get_user_recent_trades" web_server/app/services/analytics.py
```

---

### 11. telegram-notification
**설명**: 거래 체결, 시스템 오류, 일일 요약 등을 텔레그램으로 실시간 알림
**태그**: `@FEAT:telegram-notification`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/telegram.py` - 텔레그램 알림 서비스 (핵심)

**의존성**: None (독립적으로 동작, 다른 기능들이 이 기능에 의존)

**핵심 기능**:
1. **사용자별/전역 봇 관리**: 사용자별 개인 봇 우선, 전역 봇 폴백
2. **주문 수량 자동 조정 알림**: `send_order_adjustment_notification()`
3. **시스템 오류 알림**: `send_error_alert()`, `send_webhook_error()`, `send_exchange_error()`
4. **주문 실패 알림**: `send_order_failure_alert()` (복구 불가능 오류)
5. **시스템 상태 알림**: `send_system_status()` (startup, shutdown)
6. **일일 요약 보고서**: `send_daily_summary()`

**알림 통합 지점**:
- `web_server/app/routes/webhook.py` - 웹훅 처리 오류
- `web_server/app/services/trading/order_queue_manager.py` - 주문 실패
- `web_server/app/services/background/queue_rebalancer.py` - 재정렬 오류
- `web_server/app/services/exchanges/binance_websocket.py` - WebSocket 연결 오류
- `web_server/app/services/exchanges/bybit_websocket.py` - WebSocket 연결 오류
- `web_server/app/__init__.py` - 시스템 시작/종료, 백그라운드 작업 오류, 일일 요약

**상세 문서**: [telegram-notification.md](./features/telegram-notification.md)

**검색 예시**:
```bash
# 텔레그램 알림 핵심 서비스
grep -r "@FEAT:telegram-notification" --include="*.py" | grep "@TYPE:core"

# 텔레그램 알림 통합 지점 (다른 기능에서 호출)
grep -r "@FEAT:telegram-notification" --include="*.py" | grep "@TYPE:integration"

# 모든 텔레그램 관련 코드
grep -r "@FEAT:telegram-notification" --include="*.py"

# 주문 큐 + 텔레그램 통합
grep -r "@FEAT:order-queue" --include="*.py" | grep "telegram"

# 웹훅 + 텔레그램 통합
grep -r "@FEAT:webhook-order" --include="*.py" | grep "telegram"

# 텔레그램 알림 메서드
grep -n "send_.*notification\|send_.*alert\|send_.*error\|send_.*summary" web_server/app/services/telegram.py
```

---

### 12. background-scheduler
**설명**: APScheduler 기반 백그라운드 작업
**태그**: `@FEAT:background-scheduler`
**주요 컴포넌트**:
- **Job**: `web_server/app/services/background/` - 스케줄러 작업들
  - `queue_rebalancer.py` - 대기열 재정렬
- **Service**: `web_server/app/__init__.py` - 스케줄러 초기화

**의존성**: `order-queue`, `order-tracking`, `telegram-notification`

**검색 예시**:
```bash
grep -r "@FEAT:background-scheduler" --include="*.py"
```

---

## 컴포넌트 타입별 분류

### Routes (@COMP:route)
- `web_server/app/routes/webhook.py` - 웹훅 엔드포인트
- `web_server/app/routes/strategies.py` - 전략 API (성과 조회 포함)
- `web_server/app/routes/accounts.py` - 계좌 API
- `web_server/app/routes/positions.py` - 포지션 API
- `web_server/app/routes/capital.py` - 자본 API
- `web_server/app/routes/dashboard.py` - 대시보드 API

### Services (@COMP:service)
- `web_server/app/services/webhook_service.py` - 웹훅 처리
- `web_server/app/services/strategy_service.py` - 전략 관리
- `web_server/app/services/analytics.py` - 통합 분석 서비스 **(Analytics + Dashboard + Capital 통합)**
- `web_server/app/services/performance_tracking.py` - 성과 추적 **(StrategyPerformance 집계)**
- `web_server/app/services/trading/core.py` - 거래 핵심 로직
- `web_server/app/services/trading/order_queue_manager.py` - 주문 대기열
- `web_server/app/services/trading/position_manager.py` - 포지션 관리
- `web_server/app/services/order_tracking.py` - 주문 추적
- `web_server/app/services/price_cache.py` - 가격 캐싱
- `web_server/app/services/event_service.py` - SSE 이벤트
- `web_server/app/services/telegram.py` - 텔레그램 알림

### Exchanges (@COMP:exchange)
- `web_server/app/exchanges/crypto/binance.py` - Binance
- `web_server/app/exchanges/securities/korea_investment.py` - KIS

### Models (@COMP:model)
- `web_server/app/models.py` - 모든 DB 모델
  - Strategy, StrategyAccount, StrategyCapital, StrategyPosition
  - OpenOrder, PendingOrder, Trade, TradeExecution
  - **StrategyPerformance** (일별 성과 집계)
  - **DailyAccountSummary** (일일 계정 요약)
  - Account, User (telegram_id, telegram_bot_token 필드 포함)
  - WebhookLog, OrderTrackingSession
  - SystemSetting (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

### Jobs (@COMP:job)
- `web_server/app/services/background/queue_rebalancer.py` - 대기열 재정렬

---

## 로직 타입별 분류

### Core (@TYPE:core)
주요 비즈니스 로직을 담당하는 컴포넌트

### Helper (@TYPE:helper)
보조 함수 및 유틸리티

### Integration (@TYPE:integration)
외부 시스템 통합

### Validation (@TYPE:validation)
입력 검증 및 데이터 유효성 검사

### Config (@TYPE:config)
설정 및 초기화

---

## 다중 기능 태그 예시

여러 기능과 연관된 코드의 경우 여러 `@FEAT:` 태그를 사용합니다:

```python
# @FEAT:webhook-order @FEAT:order-queue @COMP:service @TYPE:integration
def enqueue_webhook_order(order_data):
    """웹훅 주문을 대기열에 추가"""
    pass

# @FEAT:order-tracking @FEAT:position-tracking @COMP:service @TYPE:core
def sync_position_from_orders(account_id):
    """주문 추적 데이터로 포지션 동기화"""
    pass

# @FEAT:webhook-order @FEAT:strategy-management @COMP:validation @TYPE:validation
def _validate_strategy_token(group_name, token):
    """전략 조회 및 토큰 검증 (웹훅에서 사용)"""
    pass

# @FEAT:strategy-management @FEAT:analytics @COMP:route @TYPE:core
@bp.route('/strategies/<int:strategy_id>/performance/roi', methods=['GET'])
def get_strategy_roi(strategy_id):
    """전략 ROI 조회 (전략 관리 + 분석 기능 통합)"""
    pass

# @FEAT:telegram-notification @COMP:service @TYPE:core @DEPS:order-queue
def send_order_failure_alert(strategy, account, symbol, error_type, error_message):
    """복구 불가능 주문 실패 시 텔레그램 알림 (주문 큐에서 호출)"""
    pass

# @FEAT:analytics @FEAT:capital-management @COMP:service @TYPE:core
def auto_allocate_capital_for_account(account_id: int) -> bool:
    """계좌에 연결된 모든 전략에 마켓 타입별로 자동 자본 할당"""
    pass

# @FEAT:analytics @FEAT:position-tracking @COMP:service @TYPE:core
def get_position_analysis(strategy_id: int) -> Dict[str, Any]:
    """포지션 분석 (analytics + position-tracking 통합)"""
    pass
```

---

## 검색 패턴 가이드

### 기본 검색
```bash
# 특정 기능의 모든 코드
grep -r "@FEAT:webhook-order" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@TYPE:core"

# 특정 컴포넌트 타입
grep -r "@COMP:service" --include="*.py"
```

### 다중 기능 검색
```bash
# 두 기능 모두 포함하는 코드 (AND)
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@FEAT:order-queue"

# 두 기능 중 하나라도 포함 (OR)
grep -r "@FEAT:webhook-order\|@FEAT:order-queue" --include="*.py"

# 전략 관리와 웹훅의 통합 지점
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@FEAT:webhook-order"

# 텔레그램 알림이 사용되는 모든 곳
grep -r "telegram_service.send" --include="*.py"

# analytics와 다른 기능의 통합 지점
grep -r "@FEAT:analytics" --include="*.py" | grep "@FEAT:"
```

### 의존성 검색
```bash
# 특정 기능에 의존하는 코드
grep -r "@DEPS:order-tracking" --include="*.py"

# capital-management에 의존하는 전략 관리 코드
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@DEPS:capital-management"

# telegram-notification에 의존하는 주문 큐 코드
grep -r "@FEAT:order-queue" --include="*.py" | grep "@DEPS:telegram-notification"

# analytics에 의존하는 코드
grep -r "@DEPS:analytics" --include="*.py"
```

### 복합 검색
```bash
# 웹훅 기능의 서비스 컴포넌트
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@COMP:service"

# 주문 대기열의 핵심 로직
grep -r "@FEAT:order-queue" --include="*.py" | grep "@TYPE:core"

# 거래소 통합의 Binance 관련 코드
grep -r "@FEAT:exchange-integration" --include="*.py" | grep -i "binance"

# 전략 관리의 검증 로직
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@TYPE:validation"

# 텔레그램 알림 통합 지점 찾기
grep -r "from app.services.telegram import telegram_service" --include="*.py"

# analytics 기능의 리스크 메트릭 계산
grep -rn "sharpe_ratio\|sortino_ratio\|max_drawdown" web_server/app/services/analytics.py web_server/app/services/performance_tracking.py
```

---

## 태그 일관성 검증

### 누락된 태그 찾기
```bash
# 클래스나 함수가 있지만 태그가 없는 파일
grep -l "^class\|^def" web_server/app/**/*.py | while read f; do
    grep -q "@FEAT:" "$f" || echo "Missing tags: $f"
done
```

### 중복/불일치 태그 찾기
```bash
# 동일한 기능에 다른 태그를 사용하는 경우
grep -r "@FEAT:webhook" --include="*.py"  # webhook vs webhook-order
grep -r "@FEAT:strategy" --include="*.py"  # strategy vs strategy-management
grep -r "@FEAT:telegram" --include="*.py"  # telegram vs telegram-notification
grep -r "@FEAT:analytic[^s]" --include="*.py"  # analytic vs analytics
```

### 전체 기능 태그 목록
```bash
# 프로젝트에 사용된 모든 @FEAT: 태그 추출 (중복 제거)
grep -roh "@FEAT:[a-z-]*" --include="*.py" | sort -u
```

---

## 태그 추가 가이드

### 신규 기능 추가 시
1. 이 카탈로그에 기능 등록
2. 모든 관련 파일에 일관된 태그 추가
3. 검색 예시 업데이트
4. 의존성 명시
5. `docs/features/{feature-name}.md` 상세 문서 작성

### 기존 코드 수정 시
1. 기능 변경 시 태그 업데이트
2. 의존성 변경 시 `@DEPS:` 업데이트
3. 카탈로그 동기화
4. 상세 문서 업데이트

---

## 유지보수 체크리스트

- [x] 모든 주요 클래스/함수에 태그 추가됨
- [x] 태그 포맷 일관성 유지
- [x] Feature Catalog가 최신 상태
- [x] 검색 예시가 작동함
- [x] 의존성이 정확히 명시됨
- [x] 상세 문서 (`docs/features/*.md`)가 존재함
- [x] 다중 기능 태그가 적절히 사용됨

---

### 13. account-management
**설명**: 계좌 생성, 조회, 수정, 삭제, 연결 테스트, 잔고 조회
**태그**: `@FEAT:account-management`
**주요 컴포넌트**:
- **Route**: `web_server/app/routes/accounts.py` - 계좌 REST API
- **Service**: `web_server/app/services/security.py` (일부) - 계좌 관리 로직

**의존성**: `exchange-integration` (연결 테스트 및 잔고 조회)

**검색 예시**:
```bash
grep -r "@FEAT:account-management" --include="*.py"
```

---

### 14. auth-session
**설명**: 사용자 인증, 로그인, 로그아웃, 세션 관리, 권한 검증
**태그**: `@FEAT:auth-session`
**주요 컴포넌트**:
- **Route**: `web_server/app/routes/auth.py` - 인증 API
- **Service**: `web_server/app/services/security.py` (일부) - 세션 및 권한 관리

**의존성**: None

**검색 예시**:
```bash
grep -r "@FEAT:auth-session" --include="*.py"
```

---

### 15. admin-panel
**설명**: 관리자 전용 페이지 (사용자 관리, 시스템 설정, 텔레그램 설정 등)
**태그**: `@FEAT:admin-panel`
**주요 컴포넌트**:
- **Route**: `web_server/app/routes/admin.py` - 관리자 API

**의존성**: `auth-session`, `telegram-notification`, `order-tracking`, `order-queue`

**검색 예시**:
```bash
grep -r "@FEAT:admin-panel" --include="*.py"
```

---

### 16. health-monitoring
**설명**: 시스템 헬스체크, 레디니스/라이브니스 체크
**태그**: `@FEAT:health-monitoring`
**주요 컴포넌트**:
- **Route**: `web_server/app/routes/health.py` - 헬스체크 API
- **Route**: `web_server/app/routes/system.py` (일부) - 시스템 모니터링 API

**의존성**: None

**검색 예시**:
```bash
grep -r "@FEAT:health-monitoring" --include="*.py"
```

---

### 17. symbol-validation
**설명**: 심볼 검증, 주문 파라미터 조정 (거래소별 정밀도, 최소/최대 수량)
**태그**: `@FEAT:symbol-validation`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/symbol_validator.py` - 심볼 검증 서비스

**의존성**: `exchange-integration`

**검색 예시**:
```bash
grep -r "@FEAT:symbol-validation" --include="*.py"
```

---

### 18. trade-execution
**설명**: 거래 실행 기록 및 통계 (TradeExecution 관리)
**태그**: `@FEAT:trade-execution`
**주요 컴포넌트**:
- **Service**: `web_server/app/services/trade_record.py` - 거래 기록 서비스
- **Service**: `web_server/app/services/order_fill_monitor.py` - 주문 체결 모니터링

**의존성**: `order-tracking`

**검색 예시**:
```bash
grep -r "@FEAT:trade-execution" --include="*.py"
```

---

### 19. securities-token
**설명**: 증권사 OAuth 토큰 자동 갱신 (한국투자증권 KIS)
**태그**: `@FEAT:securities-token`
**주요 컴포넌트**:
- **Job**: `web_server/app/jobs/securities_token_refresh.py` - 토큰 갱신 작업
- **CLI**: `web_server/app/cli/securities.py` - CLI 명령어

**의존성**: `exchange-integration` (KIS)

**검색 예시**:
```bash
grep -r "@FEAT:securities-token" --include="*.py"
```

---

### 20. api-gateway
**설명**: 대시보드, 메인 페이지, 포지션 조회 라우팅
**태그**: `@FEAT:api-gateway`
**주요 컴포넌트**:
- **Route**: `web_server/app/routes/dashboard.py` - 대시보드 API
- **Route**: `web_server/app/routes/main.py` - 메인 페이지 라우트
- **Route**: `web_server/app/routes/positions.py` (일부) - 포지션 조회 API

**의존성**: `analytics`, `position-tracking`

**검색 예시**:
```bash
grep -r "@FEAT:api-gateway" --include="*.py"
```

---

## 기존 기능 확장 (Code Review 반영)

### exchange-integration (확장)
**확장 내역**:
- `services/exchange.py` 추가 (ExchangeService, RateLimiter, PrecisionCache)
- `exchanges/crypto/*` 추가 (Binance, Upbit 구현)
- `exchanges/securities/*` 추가 (한국투자증권 KIS 구현)
- `exchanges/metadata.py`, `unified_factory.py` 추가

**통합 근거**: exchange-service, exchange-crypto, exchange-securities, exchange-metadata는 모두 거래소 통합 레이어의 구성 요소

**검색 예시**:
```bash
# 전체 거래소 통합 코드 (1번 검색으로 모든 거래소 관련 코드 조회)
grep -r "@FEAT:exchange-integration" --include="*.py"

# 거래소 서비스 오케스트레이터
grep -r "@FEAT:exchange-integration" --include="*.py" | grep "@TYPE:orchestrator"

# Binance 구현
grep -r "@FEAT:exchange-integration" --include="*.py" | grep -i "binance"

# 증권사 구현
grep -r "@FEAT:exchange-integration" --include="*.py" | grep -i "securities"
```

### order-tracking (확장)
**확장 내역**:
- `services/websocket_manager.py` 추가 (WebSocket 연결 관리)
- `services/exchanges/*_websocket.py` 추가 (Binance, Bybit WebSocket)

**통합 근거**: WebSocket은 실시간 주문 추적의 구현 수단

**검색 예시**:
```bash
# 주문 추적 전체 (WebSocket 통합 포함)
grep -r "@FEAT:order-tracking" --include="*.py"

# WebSocket 통합 부분만
grep -r "@FEAT:order-tracking" --include="*.py" | grep "@TYPE:websocket-integration"
```

### framework (확장)
**확장 내역**:
- `services/trading/core.py` 추가 (TradingCore - 거래 실행 엔진)
- `security/encryption.py` 추가 (암호화 유틸리티)
- `utils/*` 추가 (모든 유틸리티 함수)
- `__init__.py`, `constants.py`, `models.py` 등

**통합 근거**: trading-core, security-encryption, utility는 프레임워크 및 핵심 라이브러리

**검색 예시**:
```bash
# 프레임워크 전체
grep -r "@FEAT:framework" --include="*.py"

# 핵심 거래 엔진만
grep -r "@FEAT:framework" --include="*.py" | grep "trading/core"
```

---

*Last Updated: 2025-10-11*
*Version: 2.0.0*
*Total Features: 20*
*Documented Features: 20 (기존 12 + 신규 8)*
*Code Review Status: ✅ Approved with Changes - 기능 중복 제거 및 통합 완료*
