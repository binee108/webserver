# 성과 분석 (Analytics)

## 1. 개요 (Purpose)

거래 성과를 분석하고 ROI, 승률, 손익 통계, 리스크 메트릭을 제공하는 종합 분석 시스템.
- **통합 분석 서비스**: Analytics + Dashboard + Capital 기능 단일화
- **N+1 쿼리 최적화**: 벌크 로딩으로 10배 이상 성능 개선
- **리스크 메트릭**: Sharpe Ratio, Sortino Ratio, MDD, Volatility
- **실시간 성과 추적**: TradeExecution 기반 정확한 손익 집계
- **일별 자동 집계**: StrategyPerformance 테이블 히스토리 관리

## 2. 실행 플로우 (Execution Flow)

```
거래 체결 (TradeExecution)
    ↓
대시보드 API 조회 (dashboard.py routes)
    ├─ GET /api/dashboard/stats (get_user_dashboard_stats)
    └─ GET /api/dashboard/recent-trades (get_user_recent_trades)
    ↓
실시간 손익 계산 + N+1 최적화 벌크 로딩 (analytics_service)
    ↓
성과 메트릭 집계 (PerformanceTrackingService)
    ↓
ROI/승률/리스크 메트릭 계산 + StrategyPerformance 저장
```

## 3. 데이터 플로우 (Data Flow)

**Input**: TradeExecution 테이블 (realized_pnl 포함)
**Process**:
1. 실시간 조회: Trade/TradeExecution 테이블 직접 집계
2. 일별 배치: StrategyPerformance 레코드 생성 (리스크 메트릭 포함)
3. 벌크 로딩: N+1 쿼리 방지 (StrategyAccount, Position, Trade 일괄 조회)
**Output**: 대시보드 통계, 전략별 성과, 월간 리포트, 거래 통계

**주요 의존성**:
- **position-tracking**: 미실현 손익 계산
- **order-tracking**: Trade, TradeExecution 생성
- **strategy-management**: 전략별 성과 분리
- **capital-management**: 자본 대비 ROI 계산

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `services/analytics.py` | 통합 분석 서비스 | `@FEAT:analytics @COMP:service @TYPE:core` | `get_user_dashboard_stats()`, `get_capital_overview()`, `get_user_recent_trades()`, `auto_allocate_capital_for_account()` |
| `services/performance_tracking.py` | 성과 추적 서비스 | `@FEAT:analytics @COMP:service @TYPE:core` | `calculate_daily_performance()`, `_calculate_metrics()`, `_calculate_risk_metrics()` |
| `routes/dashboard.py` | 대시보드 API | `@FEAT:analytics @COMP:route @TYPE:core` | `GET /api/dashboard/stats`, `GET /api/dashboard/recent-trades` |

### AnalyticsService 주요 메서드

```python
# @FEAT:analytics @COMP:service @TYPE:core
def get_user_dashboard_stats(user_id: int) -> Dict[str, Any]
    """대시보드 통계 (N+1 최적화 벌크 로딩)

    반환값:
    - summary: {strategies, accounts, positions, orders, today}
    - strategy_details: 전략별 성과 (ROI, 승률, 포지션 수)
    - capital_overview: 계좌별 자본 현황
    """

def get_dashboard_summary(user_id: int) -> Dict[str, Any]
    """대시보드 요약 정보 (N+1 쿼리 최적화)
    - 전략/계좌 통계
    - 포지션 총액, 미체결 주문, 오늘의 거래 및 손익
    """

def get_recent_activities(user_id: int, limit: int = 10) -> Dict[str, Any]
    """최근 활동 내역 (벌크 로딩)"""

# @FEAT:analytics @FEAT:capital-management @COMP:service @TYPE:core
def get_capital_overview(user_id: int) -> Dict[str, Any]
    """자본 현황 개요 (계좌별 잔고)"""

def auto_allocate_capital_for_account(account_id: int) -> bool
    """계좌의 모든 전략에 마켓 타입별 자동 자본 할당

    **Market-Type 분리 로직**:
    - SPOT 전략들의 weight 합계 계산 → SPOT 잔고 배분
    - FUTURES 전략들의 weight 합계 계산 → FUTURES 잔고 배분
    - 각 마켓 타입 내에서 weight 비율에 따라 자본 할당
    """

def get_user_recent_trades(user_id: int, limit: int = 10, offset: int = 0) -> List[Dict]
    """최근 거래 내역 조회 (TradeExecution 기반, 페이지네이션)

    반환 필드: id, strategy_name, name(account_name), exchange, symbol, side,
               order_type, price, quantity, pnl(realized_pnl), fee(commission),
               timestamp, is_maker, market_type, exchange_trade_id, commission_asset
    """

# @FEAT:analytics @COMP:service @TYPE:helper
def _bulk_load_strategy_accounts(strategy_ids: List[int]) -> List[StrategyAccount]
    """StrategyAccount 벌크 로딩 (N+1 방지)"""

def _bulk_load_positions(sa_ids: List[int]) -> List[StrategyPosition]
    """포지션 벌크 로딩"""

def _bulk_load_orders(sa_ids: List[int]) -> List[OpenOrder]
    """미체결 주문 벌크 로딩"""

def _bulk_load_trades(sa_ids: List[int], start_date=None) -> List[Trade]
    """거래 벌크 로딩 (날짜 필터링 가능)"""
```

### PerformanceTrackingService 주요 메서드

```python
# @FEAT:analytics @COMP:service @TYPE:core
def calculate_daily_performance(strategy_id: int, target_date: date = None) -> Optional[StrategyPerformance]
    """일일 성과 계산 및 저장 (StrategyPerformance 레코드 생성)

    프로세스:
    1. StrategyPerformance 기존 레코드 확인 (없으면 생성)
    2. _calculate_metrics() 호출로 메트릭 계산
    3. daily_return, cumulative_return, daily_pnl, cumulative_pnl 저장
    4. win_rate, profit_factor, avg_win, avg_loss 저장
    5. sharpe_ratio, sortino_ratio, volatility 저장
    """

# @FEAT:analytics @COMP:service @TYPE:helper
def _calculate_metrics(strategy_id: int, target_date: date) -> Dict[str, Any]
    """메트릭 계산 (ROI, 리스크 메트릭 포함)

    계산 로직:
    1. 전략의 모든 계좌 조회 (strategy_account)
    2. StrategyCapital에서 투입 자본 합산
    3. 당일 TradeExecution에서 손익/거래 집계
    4. 누적 손익은 이전 날짜 StrategyPerformance 참조
    5. ROI = (daily_pnl / total_capital) × 100%
    """

def _calculate_risk_metrics(strategy_id: int, target_date: date) -> tuple
    """리스크 메트릭 계산 (최근 30일 기반 Sharpe, Sortino, Volatility)

    반환: (sharpe_ratio, sortino_ratio, volatility)
    """
```

## 5. 성과 지표 계산 공식

### ROI (Return on Investment)
```
ROI = (총 손익 / 투입 자본) × 100%
투입 자본 = StrategyCapital.allocated_capital (전략별 할당 자본)
총 손익 = StrategyPerformance.cumulative_pnl (누적 손익, 실시간 집계)

* 실제 구현: performance_tracking.py에서 total_pnl을 total_capital로 나눔
* StrategyPerformance는 일별 집계 테이블, Trade/TradeExecution에서 실시간 계산도 가능
```

### 승률 (Win Rate)
```
승률 = (수익 거래수 / 전체 거래수) × 100%
수익 거래 = realized_pnl > 0인 거래
```

### 손익비 (Profit Factor)
```
손익비 = 총 수익 / 총 손실
```

### 최대낙폭 (Max Drawdown, MDD)
```
MDD = (고점 - 저점) / 고점 × 100%
고점 = 누적 손익의 최고점
저점 = 고점 이후의 최저점
```

### 샤프 비율 (Sharpe Ratio)
```
Sharpe Ratio = (평균 일별 수익률 / 표준편차) × √252
252 = 연간 거래일 수 (연율화)
해석: >1.0 (좋음), >2.0 (매우 좋음), >3.0 (탁월)

**주의**: 구현 불일치 존재
- analytics.py (Line 1173-1183): √252 annualize 적용 ✅
- performance_tracking.py (Line 201): annualize 미적용 ⚠️
→ analytics.py 버전이 표준 Sharpe Ratio 계산법
```

### 소르티노 비율 (Sortino Ratio)
```
Sortino Ratio = (평균 일별 수익률 / 하방 편차) × √252
하방 편차 = 손실 거래만의 표준편차 (음수 수익률만 고려)
```

## 6. 설계 결정 히스토리 (Design Decisions)

### N+1 쿼리 최적화 필수 선택 이유
**문제**: 전략별 성과 조회 시 전략 수 × 계좌 수 × 쿼리 수만큼 DB 왕복 발생
**해결**: 벌크 로딩 패턴 도입 (selectinload + 단일 IN 쿼리)
```python
# Before: N+1 쿼리
for strategy in strategies:
    accounts = strategy.strategy_accounts  # 각 전략마다 쿼리

# After: 벌크 로딩 (5개 쿼리로 통합)
strategy_accounts = _bulk_load_strategy_accounts(strategy_ids)
```
**성과**: 10배 이상 성능 개선

### TradeExecution 기반 손익 추적
**이유**: Trade 테이블은 주문 단위, TradeExecution은 실제 체결 단위
- `realized_pnl` 필드로 정확한 손익 추적 (**nullable=True**, NULL 처리 필수)
- `is_maker` 필드로 수수료 할인 확인 가능
- 실제 체결된 거래만 집계하여 정확도 보장

**NULL 처리**:
```python
# analytics.py, performance_tracking.py에서 공통 패턴
if trade.realized_pnl is not None:
    total_pnl += trade.realized_pnl
```

### 리스크 메트릭 최근 30일 기반 계산
**이유**: Sharpe/Sortino Ratio는 충분한 샘플 데이터 필요 (최소 30일)
- 일일 수익률 30개 이상 → 통계적 유의미성 확보
- StrategyPerformance 테이블에 사전 계산하여 조회 성능 최적화

## 7. 유지보수 가이드

### 주의사항
1. **자본 정보 필수**: ROI 계산 전 StrategyCapital 테이블 설정 필요 (`auto_allocate_capital_for_account()` 사용)
2. **배치 작업 필요**: StrategyPerformance 일별 집계는 `batch_calculate()` 수동 실행 필요 (향후 스케줄러 추가 예정)
3. **벌크 로딩 필수**: 대시보드 조회 시 `_bulk_load_*()` 헬퍼 사용하여 N+1 방지
4. **realized_pnl 검증**: TradeExecution 테이블에 NULL이 없는지 확인 (손익 추적 필수)
5. **인덱스 유지**: `trades(strategy_account_id, timestamp)`, `strategy_performance(strategy_id, date)` 인덱스 필수

### 확장 포인트
1. **백그라운드 작업 자동화**: APScheduler로 매일 자정 `batch_calculate()` 실행
2. **실시간 업데이트**: 거래 체결 시 SSE 이벤트로 대시보드 실시간 업데이트
3. **캐싱 레이어**: Redis로 대시보드 통계 60초 캐싱 (성능 향상)
4. **거래 패턴 분석**: 시간대별/요일별 승률 분석 추가
5. **포트폴리오 리밸런싱**: Sharpe Ratio 기반 최적 자본 배분 제안

### 트러블슈팅
| 증상 | 원인 | 해결 |
|------|------|------|
| ROI 0% | StrategyCapital 미설정 | `auto_allocate_capital_for_account()` 실행 |
| 승률 NaN | realized_pnl NULL | TradeExecution 테이블 확인 |
| Sharpe Ratio NULL | 30일 데이터 부족 | 거래 데이터 축적 후 `batch_calculate()` 실행 |
| 대시보드 느림 (5초+) | N+1 쿼리 발생 | 벌크 로딩 사용 확인, 인덱스 추가 |
| 일별 집계 누락 | 백그라운드 작업 미실행 | `batch_calculate(days_back=7)` 수동 실행 |

## 8. API 엔드포인트

### 구현된 엔드포인트

```bash
# 대시보드 통계 (dashboard.py Line 18)
GET /api/dashboard/stats
→ analytics_service.get_user_dashboard_stats()

# 최근 거래 내역 (dashboard.py Line 45)
GET /api/dashboard/recent-trades?limit=20&offset=0
→ analytics_service.get_user_recent_trades()
```

### 미구현 엔드포인트 (계획 중)

다음 엔드포인트들은 서비스 메서드는 존재하나 routes/strategies.py에 API가 등록되지 않음:

```bash
# ⚠️ 미구현 - performance_tracking_service.calculate_roi() 메서드는 존재
GET /api/strategies/<strategy_id>/performance/roi?days=30

# ⚠️ 미구현 - performance_tracking_service.get_performance_summary() 메서드는 존재
GET /api/strategies/<strategy_id>/performance/summary?days=30

# ⚠️ 미구현 - performance_tracking_service.calculate_daily_performance() 메서드는 존재
GET /api/strategies/<strategy_id>/performance/daily?date=2025-10-11
```

**구현 방법**: routes/strategies.py에 다음 라우트 추가 필요
```python
@bp.route('/api/strategies/<int:strategy_id>/performance/roi')
@login_required
def get_strategy_roi(strategy_id):
    # performance_tracking_service.calculate_roi() 호출
    pass
```

## 9. 검색 예시

```bash
# analytics 기능의 모든 코드
grep -r "@FEAT:analytics" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:analytics" --include="*.py" | grep "@TYPE:core"

# 헬퍼 함수만
grep -r "@FEAT:analytics" --include="*.py" | grep "@TYPE:helper"

# 서비스 컴포넌트만
grep -r "@FEAT:analytics" --include="*.py" | grep "@COMP:service"

# 자본 관리 통합 지점
grep -r "@FEAT:analytics" --include="*.py" | grep "@FEAT:capital-management"

# ROI 계산 로직
grep -rn "calculate_roi" web_server/app/services/

# Sharpe Ratio 계산
grep -rn "sharpe_ratio" web_server/app/services/

# 벌크 로딩 헬퍼
grep -rn "_bulk_load" web_server/app/services/analytics.py
```

---

*Last Updated: 2025-10-30*
*Version: 2.2.0 (Code Sync)*
*Changes:*
- *벌크 로딩 헬퍼 함수 추가 (_bulk_load_positions, _bulk_load_orders, _bulk_load_trades)*
- *get_dashboard_summary() 메서드 추가 (요약 정보)*
- *get_recent_activities() 메서드 추가 (최근 활동)*
- *PerformanceTrackingService._calculate_metrics() 상세 로직 문서화*
- *실행 플로우 개선 (API 라우트 명시)*
- *AnalyticsService 메서드 시그니처 코드 기준 동기화*
