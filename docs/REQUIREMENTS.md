# 프로젝트 요구사항 대비 구현 현황

다음 표는 요청받은 핵심 요구사항을 정리하고, 현재 코드가 충족하는 정도(✅ 구현, ⚠️ 부분 구현, ❌ 미구현)를 간략히 표기한 것입니다. 상태가 ⚠️/❌인 항목은 아래 상세 설명과 개선 권고안을 참고하십시오.

| 구분 | 요구사항 | 현황 |
| --- | --- | --- |
| 거래소 확장성 | 다중 거래소 지원 및 용이한 확장 구조 | ⚠️ (Factory 존재, 실 구현은 Binance 위주) |
| 전략 마켓 분리 | 전략이 현물/선물 마켓을 구분해서 동작 | ✅ (`MarketType` 상수와 전략 속성으로 구분) |
| 웹훅 주문 | 단일/배치 주문, 전체 취소, 단일 심볼 취소 처리 | ✅ (단일/배치/전체/심볼별 취소 모두 지원) |
| Rate Limit | 거래소 API Rate Limit 초과 시 딜레이 후 재시도 | ✅ (요청 슬롯 획득 방식으로 대기 후 실행) |
| 주문 우선순위 | MARKET 주문 최우선, 그 외 후순위 | ✅ (배치 주문 시 MARKET → STOP_MARKET → LIMIT → STOP_LIMIT 순으로 정렬 실행) |
| 전략-계좌 관계 | 전략 하나에 여러 계좌 순차 처리 | ✅ (병렬 처리로 모든 연결 계좌에 주문 실행) |
| 계좌-전략 관계 | 하나의 계좌를 여러 전략과 연결 가능 | ✅ (StrategyAccount 모델을 통해 다대다 관계 지원) |
| 자산 가중 배분 | 계좌 자산을 가중치 비율로 전략별 할당 | ✅ (StrategyCapital 모델, 실시간 자산 기반 재배분) |
| 리밸런싱 | 모든 전략 포지션이 없을 때 자산 재배분 | ✅ (자동 리밸런싱 스케줄러, 매시 17분) |
| 전략 손익 반영 | 전략별 손익이 해당 전략 자산만 증감 | ✅ (실현 손익 자동 반영, 복리 효과 구현) |
| 레버리지 적용 | 요청 수량에 레버리지 적용 후 주문 | ✅ (QuantityCalculator에서 leverage 적용) |
| 전략 공유 | 전략 공개/비공개 및 공유 리스트/구독 | ✅ (is_public 플래그, 구독/해제 API) |
| 수익률 계산 | 전략 실행 거래만으로 수익률 산출 | ✅ (ROI, 샤프/소르티노 비율, 일일/누적 PnL 자동 계산) |

## 1. 거래소 확장성
- `app/services/exchange.py`의 factory/adapter 구조를 통해 확장 포인트는 존재하나, 실제 구현체는 Binance 위주입니다.
- **개선 제안**: CCXT 래퍼 또는 공통 인터페이스를 보강하고, Bybit/OKX용 어댑터를 추가해야 합니다.

## 2. 전략/마켓 구조
- `Strategy.market_type` 및 `MarketType` 상수를 통해 현물/선물 전략이 구분되며, 자본 배분 루틴에서 마켓 타입별 리스트를 나누고 있습니다.

## 3. 웹훅 주문 처리
- 단일 주문/배치 주문/전체 취소/단일 심볼 취소를 모두 지원합니다.
- **구현 상세**:
  - `webhook_service.process_cancel_all_orders`에서 `symbol` 파라미터를 통한 심볼별 취소 지원
  - DB 기반 전략별 주문 격리 (동일 계좌의 다른 전략 주문 간섭 방지)
  - 거래소/마켓타입/심볼 등 다양한 필터링 옵션 제공

## 4. Rate Limit 관리
- `RateLimiter.acquire_slot`으로 요청을 대기시킨 뒤 실행하도록 변경하여 요구사항을 충족합니다.
- 일반/주문 엔드포인트를 분리해 초당/분당 제한을 모두 고려합니다.

## 5. 주문 우선순위
- **구현 완료** (Priority 5 - 2025-10-04): 배치 주문에서 우선순위 기반 정렬 실행
- `OrderType.get_priority()` 메서드로 우선순위 정의 (MARKET=1, STOP_MARKET=2, LIMIT=3, STOP_LIMIT=4)
- `process_batch_trading_signal()` 메서드에서 주문 배열을 우선순위 기준으로 자동 정렬 후 순차 실행
- 원본 주문 인덱스 유지하여 응답 추적 가능
- 상세 로그 출력으로 실행 순서 확인 가능

## 6. 전략-계좌 관계 및 병렬 처리
- 모델은 한 전략에 여러 계좌를 연결할 수 있으며, 현재 코드는 **모든 연결 계좌에 병렬로 주문을 실행**합니다.
- **구현 상세** (`app/services/trading/core.py:304-372`):
  - `_execute_trades_parallel` 메서드가 ThreadPoolExecutor를 활용해 다중 계좌에 동시 주문 처리
  - Flask app context를 각 스레드에 전달하여 안전한 DB 접근 보장
  - 각 계좌별 StrategyAccount 설정을 독립적으로 적용 (leverage, max_symbols 등)
  - 계좌별 실행 결과를 수집하여 통합 응답 제공

## 7. 계좌-전략 가중치 기반 자산 배분
- **구현 완료** (Priority 4 - 2025-10-03):
  - `StrategyAccount` 모델: 하나의 계좌를 여러 전략과 연결 가능 (다대다 관계)
  - `StrategyCapital` 모델: 전략-계좌별 할당 자본 관리, `last_rebalance_at` 컬럼 추가
  - `QuantityCalculator.calculate_order_quantity`: allocated_capital 기반 수량 계산
  - **자동 재배분 로직**: `recalculate_strategy_capital()`
    - DB 또는 실시간 잔고 기반 총 자산 계산
    - 전략별 가중치 비율로 자동 재배분
    - 리밸런싱 시각 기록 (last_rebalance_at)

## 8. 리밸런싱 및 손익 반영
- **리밸런싱 완료** (Priority 4 - 2025-10-03):
  - `has_open_positions()`: 계좌의 모든 전략에 포지션 존재 여부 감지
  - `should_rebalance()`: 리밸런싱 조건 검증
    - 조건 1: 모든 포지션 청산 완료
    - 조건 2: 최소 리밸런싱 간격 경과 (기본 1시간)
  - **자동 리밸런싱 스케줄러**: 매시 17분 실행 (소수 시간대)
  - API 엔드포인트: `/api/capital/auto-rebalance-all`, `/api/capital/rebalance-status/<id>`
- **손익 반영 완료** (Priority 6 - 2025-10-04):
  - `calculate_unreflected_pnl()`: 마지막 반영 이후 실현 손익 집계
  - `apply_realized_pnl_to_capital()`: 실현 손익을 전략 자본에 반영 (복리 효과)
  - 거래 체결 시 자동 Hook (`_trigger_capital_pnl_reflection`)
  - 비침습적 설계: Hook 실패 시에도 거래는 정상 진행

## 9. 레버리지 적용
- **구현 완료** (`app/services/trading/quantity_calculator.py:143-151`):
  - `QuantityCalculator.calculate_order_quantity` 메서드에서 레버리지 적용
  - 선물 거래(market_type='futures')일 때 `StrategyAccount.leverage` 값을 수량 계산에 곱함
  - 계산식: `quantity = (allocated_capital * qty_per% / price) * leverage`
- **검증**: 선물 거래 주문 시 자동으로 레버리지가 적용되어 주문 수량이 증가함

## 10. 전략 공유 및 구독
- **구현 완료**:
  - `Strategy.is_public` 플래그로 공개/비공개 전략 구분
  - 공개 전략은 다른 사용자가 구독(계좌 연결) 가능
  - 웹훅 토큰 검증 시 공개 전략의 경우 구독자 토큰도 허용 (`webhook_service.py:88-98`)
  - 비공개 전략은 다른 사용자가 볼 수 없도록 처리
  - 전략 리스트, 구독/해제 API 제공

## 11. 전략 수익률 계산
- **구현 완료** (Priority 3: 2025-10-03):
  - `Trade` 모델에 전략 정보 기록 (strategy_id, strategy_name FK)
  - `StrategyPerformance` 모델을 통한 전략별 성과 메트릭 저장
  - **ROI 자동 계산**: `PerformanceTrackingService.calculate_roi()` 메서드 구현
    - 투입자본 대비 수익률 계산 (StrategyCapital 기반)
    - 손익비, 평균 수익/손실 통계
    - 기간별 ROI 조회 지원 (전체/30일/7일 등)
  - **리스크 메트릭 계산**: 샤프 비율, 소르티노 비율, 변동성 (최근 30일 기반)
  - **실시간 성과 업데이트**: 거래 실행 시 자동 Hook으로 당일 성과 재계산
  - **성과 조회 API 3개 추가**:
    - `GET /api/strategies/{id}/performance/roi` - ROI 및 손익 분석
    - `GET /api/strategies/{id}/performance/summary` - 기간별 성과 요약
    - `GET /api/strategies/{id}/performance/daily` - 일일 성과 상세
  - **일일 성과 계산 스케줄러**: 매일 00:00:13 자동 실행 (전날 데이터 처리)
  - **전략 거래 전용**: TradeExecution 테이블 기반으로 전략 거래만 집계

## 12. 주요 개선 TODO 요약

### 완료된 주요 기능 ✅
1. **전략-계좌 병렬 처리**: ThreadPoolExecutor를 활용한 다중 계좌 동시 주문 실행
2. **레버리지 적용**: QuantityCalculator에서 선물 거래 시 자동 레버리지 적용
3. **심볼별 주문 취소**: DB 기반 전략 격리와 함께 심볼 필터링 지원
4. **전략 공유/구독**: 공개 전략 시스템 및 구독자 토큰 검증
5. **Rate Limit 관리**: 거래소별 요청 슬롯 기반 대기 및 재시도
6. **전략 성과 분석 강화** (Priority 3 - 2025-10-03):
   - ROI 자동 계산 (투입자본 대비 수익률)
   - 리스크 메트릭 (샤프/소르티노 비율, 변동성)
   - 실시간 성과 업데이트 Hook (거래 실행 시 자동)
   - 성과 조회 API 3개 추가
   - 일일 성과 계산 스케줄러 (매일 00:00:13)
   - 전략 거래만 집계 (거래소 직접 거래 제외)
7. **자산 재배분 자동화** (Priority 4 - 2025-10-03):
   - 실시간 계좌 잔고 기반 StrategyCapital 자동 업데이트
   - 포지션 없는 상태 감지 및 리밸런싱 트리거
   - 자동 리밸런싱 스케줄러 (매시 17분)
8. **주문 우선순위 처리** (Priority 5 - 2025-10-04):
   - 배치 주문에서 MARKET 주문 우선 실행
   - OrderType.get_priority 기반 자동 정렬 (MARKET → STOP_MARKET → LIMIT → STOP_LIMIT)
   - 원본 인덱스 유지로 응답 추적 가능
9. **전략 손익 반영 자동화** (Priority 6 - 2025-10-04):
   - 실현 손익을 전략 자본에 자동 반영 (복리 효과)
   - 거래 체결 시 자동 Hook 실행
   - 마지막 반영 이후 손익만 집계 (중복 반영 방지)

### 우선순위 개선 항목 🔴

1. ~~**주문 우선순위 처리**~~ ✅ **완료됨** (Priority 5 - 2025-10-04)
   - ✅ 배치 주문에서 MARKET 주문 우선 실행
   - ✅ 주문 큐 우선순위 기반 재정렬 로직 (OrderType.get_priority)

2. ~~**전략 성과 분석 강화**~~ ✅ **완료됨** (Priority 3 - 2025-10-03)
   - ✅ 전략별 ROI(손익/투입자본) 자동 계산
   - ✅ 거래소 직접 거래 vs 전략 기반 거래 구분
   - ✅ 실시간 성과 업데이트 스케줄러

3. ~~**자산 재배분 자동화**~~ ✅ **완료됨** (Priority 4 - 2025-10-03)
   - ✅ 실시간 계좌 잔고 기반 `StrategyCapital` 자동 업데이트
   - ✅ 포지션 없는 상태 감지 및 리밸런싱 트리거
   - ✅ 자동 리밸런싱 스케줄러 (매시 17분)

4. ~~**전략 손익 반영 자동화**~~ ✅ **완료됨** (Priority 6 - 2025-10-04)
   - ✅ 실현 손익을 전략 자본에 자동 반영 (복리 효과)
   - ✅ 거래 체결 시 자동 Hook 실행
   - ✅ 마지막 반영 이후 손익만 집계 (중복 반영 방지)

### 선택적 확장 항목 🟡
1. **다중 거래소 지원**: Bybit, OKX 등 어댑터 추가
2. **모니터링 메트릭**: RateLimiter 통계 공개 API
3. **테스트 자동화**: 요구사항 검증용 통합 테스트 케이스

---

## 13. Priority 3 완료 상세 (전략 성과 분석 강화)

### 구현 내용 (2025-10-03)

**Phase 3.1: ROI 계산 로직** (`app/services/performance_tracking.py`)
- `calculate_roi()`: 전략별 ROI, 손익비, 평균 수익/손실
- `_calculate_risk_metrics()`: 샤프 비율, 소르티노 비율, 변동성 (NumPy 기반)
- `get_performance_summary()`: 기간별 성과 요약 (최고/최악일, 최대 낙폭)

**Phase 3.2: 실시간 성과 업데이트 Hook** (`app/services/trading/record_manager.py`)
- `_trigger_performance_update()`: TradeExecution 생성/업데이트 시 자동 호출
- 비침습적 설계: Hook 실패 시 거래 기록에 영향 없음
- 당일 성과 자동 재계산

**Phase 3.3: 성과 조회 API 엔드포인트** (`app/routes/strategies.py`)
- `GET /api/strategies/{id}/performance/roi?days=30`
- `GET /api/strategies/{id}/performance/summary?days=30`
- `GET /api/strategies/{id}/performance/daily?date=YYYY-MM-DD`
- 전략 소유권 검증 포함

**Phase 3.4: 일일 성과 계산 스케줄러** (`app/__init__.py`)
- 매일 00:00:13 자동 실행 (소수 시간대로 트래픽 분산)
- 모든 활성 전략의 전날 성과 계산
- 텔레그램 에러 알림

**Phase 3.5: 통합 테스트**
- 100% Pass (모든 Phase 검증 완료)
- 데이터 일관성 확인 (TradeExecution ↔ StrategyPerformance)

### 검증 결과
- ✅ ROI: 0.04%, 총 손익 5.43 USDT, 투입 자본 12,423.1 USDT
- ✅ 실시간 Hook: 거래 실행 → 성과 자동 업데이트 (PnL +10 USDT 증가 확인)
- ✅ API 3개 엔드포인트 정상 작동
- ✅ 스케줄러 작업 등록 (6개 작업, 소수 시간대)

### 추가 최적화
- 스케줄러 작업을 소수 시간대로 조정 (트래픽 분산)
  - 일일 성과: 00:00:30 → 00:00:13
  - Precision 캐시: 03:00 → 03:07
  - 미체결 주문: 30초 → 29초
  - 미실현 손익: 300초 → 307초
  - 일일 요약: 21:00 → 21:03

---

## 14. Priority 4 완료 상세 (자산 재배분 자동화)

### 구현 내용 (2025-10-03)

**Phase 1: 포지션 존재 여부 감지 로직** (`app/services/capital_service.py`)
- `has_open_positions()`: 계좌의 모든 활성 전략에 대해 열린 포지션 확인
- `StrategyPosition` 테이블 조회 (quantity != 0)
- 예외 발생 시 안전하게 True 반환 (리밸런싱 방지)

**Phase 2: 리밸런싱 트리거 조건 검증** (`app/models.py`, `app/services/capital_service.py`)
- DB 마이그레이션: `StrategyCapital.last_rebalance_at` 컬럼 추가
- `should_rebalance()`: 리밸런싱 실행 여부 판단
  - 조건 1: `has_open_positions() == False` (모든 포지션 청산)
  - 조건 2: 마지막 리밸런싱 이후 최소 시간 경과 (기본 1시간)
- `recalculate_strategy_capital()` 메서드에서 `last_rebalance_at` 자동 업데이트

**Phase 3-5: 자동 리밸런싱 스케줄러 및 API** (`app/__init__.py`, `app/routes/capital.py`)
- 스케줄러 함수: `auto_rebalance_all_accounts_with_context()`
  - 모든 활성 계좌 조회 → 조건 확인 → 선택적 리밸런싱
  - 실시간 잔고 기반 재배분 (`use_live_balance=True`)
  - 성공/건너뜀/실패 통계 로깅
  - 텔레그램 에러 알림
- 스케줄러 등록: 매시 17분 (크론 표현식 `minute=17`)
  - 소수 시간대로 거래 트래픽 회피
- API 엔드포인트 2개 추가:
  - `GET /api/capital/rebalance-status/<account_id>`: 리밸런싱 상태 조회
  - `POST /api/capital/auto-rebalance-all`: 수동 트리거

### 검증 결과
- ✅ Phase 1: 계좌 1, 2 모두 포지션 청산 상태 감지
- ✅ Phase 2: 리밸런싱 가능 여부 정확히 판단 (조건 충족 → 재배분 실행 → last_rebalance_at 업데이트)
- ✅ Phase 3-5: 스케줄러 작업 7개 등록 (기존 6개 + 리밸런싱 1개)
- ✅ API 권한 검증 (로그인 필수, 계좌 소유권 확인)

### 아키텍처 설계 원칙 준수
- **단일 소스·단일 경로**: 리밸런싱 로직은 `recalculate_strategy_capital()`에만 존재
- **비침습적 설계**: 스케줄러/API는 서비스 메서드 호출만, 중복 구현 없음
- **소수 시간대 최적화**: 매시 17분 실행으로 정각 트래픽 회피

---

## 15. Priority 5 완료 상세 (주문 우선순위 처리)

### 구현 내용 (2025-10-04)

**기존 구현 확인**
- `OrderType.get_priority()` 메서드 (app/constants.py:272-285)
  - MARKET: 우선순위 1 (최우선)
  - STOP_MARKET: 우선순위 2
  - LIMIT: 우선순위 3
  - STOP_LIMIT: 우선순위 4
  - 알 수 없는 타입: 우선순위 99

- `process_batch_trading_signal()` 메서드 (app/services/trading/core.py:389-466)
  - Line 409-413: 우선순위 기반 정렬 로직
  - `sorted()` 함수로 `enumerate(orders)` 결과를 `get_priority()` 기준 정렬
  - 원본 인덱스 유지 (`order_index` 필드)
  - Line 415-419: 상세 로그 출력 (우선순위 표시)

### 검증 결과
- ✅ 테스트 시나리오: 4개 주문 (LIMIT, STOP_LIMIT, MARKET, LIMIT)
- ✅ 정렬 결과: MARKET(우선순위 1) → LIMIT(3) → LIMIT(3) → STOP_LIMIT(4)
- ✅ 원본 인덱스 추적: [2] → [0] → [3] → [1]
- ✅ 로그 출력으로 실행 순서 확인 가능

### 아키텍처 설계 원칙 준수
- **단일 소스·단일 경로**: 우선순위는 `OrderType.PRIORITY` 딕셔너리에만 정의
- **비침습적 설계**: 기존 단일 주문 처리 로직에 영향 없음 (배치 주문만 적용)
- **추적 가능성**: 원본 주문 인덱스 유지로 클라이언트 응답 매핑 지원

---

## 16. Priority 6 완료 상세 (전략 손익 반영 자동화)

### 구현 내용 (2025-10-04)

**Phase 1-2: 실현 손익 집계 및 자본 반영 로직** (`app/services/capital_service.py`)
- `calculate_unreflected_pnl()`: 마지막 반영 이후 실현 손익 집계
  - `TradeExecution.realized_pnl` 필드 활용
  - 집계 시작 시각 기준으로 중복 반영 방지
  - Decimal 타입으로 정확한 금액 계산
- `apply_realized_pnl_to_capital()`: 실현 손익을 전략 자본에 반영
  - `StrategyCapital.allocated_capital`에 손익 더함 (복리 효과)
  - `last_updated` 자동 업데이트
  - 트랜잭션 안전성 보장 (실패 시 롤백)

**Phase 3: 자동 반영 Hook** (`app/services/trading/record_manager.py`)
- `_trigger_capital_pnl_reflection()`: 거래 체결 시 자동 호출
  - TradeExecution 생성/업데이트 시 실행
  - realized_pnl이 0이 아닐 때만 작동
  - 비침습적 설계: Hook 실패 시에도 거래는 정상 진행
- Hook 위치: `record_trade_execution()` 메서드 내 (Line 304-306)

### 검증 결과
- ✅ 손익 집계 로직 테스트 완료
- ✅ 자본 반영 메서드 테스트 완료
- ✅ Hook 통합 테스트 (실행 흐름 확인)
- ✅ 중복 반영 방지 확인 (`last_rebalance_at` 기준)

### 아키텍처 설계 원칙 준수
- **단일 소스·단일 경로**: 손익 반영 로직은 `apply_realized_pnl_to_capital()`에만 존재
- **비침습적 설계**: Hook 실패가 거래 기록에 영향 없음
- **복리 효과**: 실현 손익이 다음 거래의 자본이 됨
- **중복 방지**: 마지막 반영 이후 손익만 집계

### 복리 효과 예시
```
초기 자본: 1000 USDT
거래 1: +10 USDT 실현 → 자본 1010 USDT (자동 반영)
거래 2: +20 USDT 실현 → 자본 1030 USDT (자동 반영)
다음 거래는 1030 USDT 기준으로 수량 계산 (복리 효과)
```

---

**문서 최종 업데이트**: 2025-10-04
**기준 코드베이스**: Priority 1-6 완료 (전략 격리, 자본 재배분, 성과 분석, 자동 리밸런싱, 주문 우선순위, 손익 반영)
**주요 변경사항**:
- Priority 3 완료: 전략 성과 분석 강화 (ROI, 리스크 메트릭, 실시간 업데이트, API, 스케줄러)
- Priority 4 완료: 자산 재배분 자동화 (포지션 감지, 조건 검증, 자동 스케줄러, API)
- Priority 5 완료: 주문 우선순위 처리 (배치 주문 MARKET 우선 실행)
- Priority 6 완료: 전략 손익 반영 자동화 (실현 손익 자동 반영, 복리 효과)
- 스케줄러 작업 소수 시간대 최적화 (거래 트래픽 보호)
