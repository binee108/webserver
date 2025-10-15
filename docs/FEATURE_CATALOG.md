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

### 2. order-queue
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
- **2025-10-15**: Side별 분리 정렬 구현 (Phase 1-2)
  - Buy/Sell 주문 독립 할당 (각 side 20개)
  - ExchangeLimits에 side별 제한 필드 추가 (`max_orders_per_side`, `max_stop_orders_per_side`)
  - 총 용량 2배 증가 (20개 → 40개, 각 side 10개씩)
  - DRY 원칙: `_select_top_orders()` 헬퍼 함수 추가 (40+ 라인 중복 제거)
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
**설명**: 자본 배분 및 관리 (analytics 서비스에 통합)
**태그**: `@FEAT:capital-management`
**주요 파일**:
- `services/analytics.py` - 자본 관리 (통합됨)
- `routes/capital.py` - 자본 API
**의존성**: `position-tracking`, `strategy-management`
**상세 문서**: `docs/features/capital-management.md`
**검색**:
```bash
grep -r "@FEAT:capital-management" --include="*.py"
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

---

### 7. price-cache
**설명**: 심볼별 가격 캐싱 및 주기적 업데이트
**태그**: `@FEAT:price-cache`
**주요 파일**:
- `services/price_cache.py` - 가격 캐시
**의존성**: `exchange-integration`
**상세 문서**: `docs/features/price-cache.md`
**검색**:
```bash
grep -r "@FEAT:price-cache" --include="*.py"
```

---

### 8. event-sse
**설명**: Server-Sent Events 기반 실시간 이벤트 발송
**태그**: `@FEAT:event-sse`
**주요 파일**:
- `services/event_service.py` - SSE 이벤트 관리
- `services/trading/event_emitter.py` - 이벤트 발행
**의존성**: None
**상세 문서**: `docs/features/event-sse.md`
**검색**:
```bash
grep -r "@FEAT:event-sse" --include="*.py"
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

### By Logic Type
- **core**: 핵심 비즈니스 로직
- **helper**: 유틸리티 함수
- **integration**: 외부 시스템 통합
- **validation**: 입력 검증
- **config**: 설정 및 초기화

---

## Recent Changes

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

*Last Updated: 2025-10-15*
*Recent Changes: Order queue side-based separation (Phase 1-2 완료)*
