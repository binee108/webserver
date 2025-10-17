# 백그라운드 스케줄러

> **목적**: APScheduler를 사용한 주기적 작업 자동화 및 Flask Reloader 환경에서 중복 실행 방지

## 시스템 개요

### 핵심 기능
- **주문 큐 재정렬** (1초): OpenOrder ↔ PendingOrder 우선순위 기반 이동
- **미체결 주문 업데이트** (29초): 미체결 주문 상태 확인 및 Position 업데이트
- **가격 캐시 갱신** (31초): 활성 심볼 최신 가격 메모리 캐싱 (소수 주기)
- **미실현 손익 계산** (307초 ≈ 5분): 포지션 미실현 손익 계산 (소수 주기)
- **일일 성과 계산** (매일 00:00:13): 전략별 일일 성과 집계
- **일일 요약 전송** (매일 21:03): 텔레그램 일일 리포트
- **자동 리밸런싱** (매시 :17분): 계좌별 자본 자동 재배분
- **증권 토큰 갱신** (6시간): 증권사 OAuth 토큰 자동 갱신
- **WebSocket 모니터링** (1분): WebSocket 연결 상태 확인 및 재연결

### 기술 스택
- **라이브러리**: APScheduler (BackgroundScheduler)
- **실행 모드**: 백그라운드 스레드 (Flask 메인 스레드와 독립)
- **시간대**: Asia/Seoul (KST)
- **Executor**: ThreadPoolExecutor (최대 20개 워커)

---

## 주요 구성 요소

### 1. 스케줄러 초기화
**파일**: `app/__init__.py` (L376-395)
**태그**: `@FEAT:background-scheduler @COMP:config @TYPE:core`

```python
# 전역 스케줄러 인스턴스
scheduler = BackgroundScheduler()

def init_scheduler(app):
    """APScheduler 초기화 및 작업 등록"""
    scheduler.configure(
        jobstores={'default': MemoryJobStore()},
        executors={'default': ThreadPoolExecutor(20)},
        job_defaults={'coalesce': False, 'max_instances': 3},
        timezone='Asia/Seoul'
    )
    register_background_jobs(app)
    scheduler.start()
```

### 2. Flask Reloader 중복 실행 방지
**파일**: `app/__init__.py` (L331-339)
**태그**: `@FEAT:background-scheduler @COMP:config @TYPE:validation`

**문제**: Flask 개발 서버는 파일 변경 감지를 위해 2개 프로세스 실행 (메인 프로세스 + 워커 프로세스)

**해결**: `WERKZEUG_RUN_MAIN` 환경 변수 체크로 워커 프로세스에서만 실행

```python
if os.environ.get('WERKZEUG_RUN_MAIN'):
    init_scheduler(app)  # 워커 프로세스만
else:
    app.logger.info('🔄 Flask reloader 메인 프로세스 - 스케줄러 건너뜀')
```

**검증**:
```bash
# 로그에 "APScheduler 시작됨" 메시지가 1번만 출력되어야 함
grep "APScheduler 시작됨" web_server/logs/app.log
```

---

## 백그라운드 작업 상세

### 1. 주문 큐 재정렬 (Rebalance Order Queue)
**파일**: `app/services/background/queue_rebalancer.py`
**태그**: `@FEAT:order-queue @FEAT:background-scheduler @COMP:service @TYPE:core`

**실행 주기**: 1초
**Job ID**: `rebalance_order_queue`
**역할**: OpenOrder + PendingOrder 통합 정렬, 우선순위 변경 시 주문 이동

**데이터 플로우**:
```
DB (OpenOrder, PendingOrder)
  → 활성 계좌 조회
  → (account_id, symbol) 조합 추출
  → 각 조합별 재정렬
  → 거래소 최대 심볼 수 제한 대응
```

**등록 방법**:
```python
scheduler.add_job(
    func=rebalance_all_symbols_with_context,
    args=[app],
    trigger="interval",
    seconds=1,
    id='rebalance_order_queue',
    max_instances=1,
    replace_existing=True
)
```

### 2. 가격 캐시 갱신 (Update Price Cache)
**파일**: `app/services/price_cache.py` (L224-317, `_refresh_price_cache`)
**태그**: `@FEAT:price-cache @FEAT:background-scheduler @COMP:service @TYPE:helper`

**실행 주기**: 31초 (소수 주기로 정각 트래픽 회피)
**Job ID**: `update_price_cache`
**역할**: 활성 심볼 최신 가격 조회 및 메모리 캐싱 (API 호출 감소)

**데이터 구조**:
```python
_price_cache = {
    (symbol, exchange, market_type): {
        'price': float,
        'timestamp': float
    }
}
```

**처리 단계**:
1. 거래소/마켓 전체 시세 갱신
2. 활성 포지션 심볼 우선 갱신

### 3. 미체결 주문 업데이트 (Update Open Orders)
**파일**: `app/__init__.py` (L339-357, `update_open_orders_with_context`)
**태그**: `@FEAT:order-tracking @FEAT:background-scheduler @COMP:service @TYPE:core`

**실행 주기**: 29초 (소수 주기)
**Job ID**: `update_open_orders`
**역할**: 미체결 주문 상태 확인 (거래소 API), Position 업데이트

**실행 흐름**:
```
trading_service.update_open_orders_status() 호출
  → 미체결 주문 조회 (status='NEW', 'PARTIALLY_FILLED')
  → 거래소 API로 주문 상태 조회
  → 체결 감지 시 Position 업데이트
```

### 4. 미실현 손익 계산 (Calculate Unrealized PnL)
**파일**: `app/__init__.py` (L358-376, `calculate_unrealized_pnl_with_context`)
**태그**: `@FEAT:position-tracking @FEAT:background-scheduler @COMP:service @TYPE:core`

**실행 주기**: 307초 ≈ 5분 7초 (소수 주기)
**Job ID**: `calculate_unrealized_pnl`
**역할**: 모든 활성 포지션의 미실현 손익 계산

**실행 흐름**:
```
trading_service.calculate_unrealized_pnl() 호출
  → 활성 포지션 조회 (quantity != 0)
  → 현재가 조회 (price_cache 활용)
  → 미실현 손익 계산 및 DB 업데이트
```

### 5. 일일 요약 전송 (Send Daily Summary)
**파일**: `app/__init__.py` (L377-409, `send_daily_summary_with_context`)
**태그**: `@FEAT:telegram-notification @FEAT:background-scheduler @COMP:service @TYPE:integration`

**실행 주기**: 매일 21:03 (cron)
**Job ID**: `send_daily_summary`
**역할**: 텔레그램으로 일일 요약 리포트 전송

**실행 흐름**:
```
모든 활성 계정 조회
  → analytics_service.get_daily_summary() 호출
  → telegram_service.send_daily_summary() 전송
```

### 6. 일일 성과 계산 (Calculate Daily Performance)
**파일**: `app/__init__.py` (L487-550, `calculate_daily_performance_with_context`)
**태그**: `@FEAT:performance-tracking @FEAT:background-scheduler @COMP:service @TYPE:core`

**실행 주기**: 매일 00:00:13 (cron)
**Job ID**: `calculate_daily_performance`
**역할**: 전날 전략별 성과 집계 및 DB 저장

**실행 흐름**:
```
모든 활성 전략 조회
  → performance_tracking_service.calculate_daily_performance()
  → 전날(yesterday) 거래 데이터 집계
  → StrategyDailyPerformance 테이블 저장
```

### 7. 자동 리밸런싱 (Auto Rebalance Accounts)
**파일**: `app/__init__.py` (L411-485, `auto_rebalance_all_accounts_with_context`)
**태그**: `@FEAT:capital-management @FEAT:background-scheduler @COMP:service @TYPE:core`

**실행 주기**: 매시 17분 (cron)
**Job ID**: `auto_rebalance_accounts`
**역할**: 계좌별 자본 자동 재배분 (실시간 잔고 기반)

**실행 흐름**:
```
모든 활성 계좌 조회
  → capital_allocation_service.should_rebalance() 조건 확인
  → 조건 충족 시 capital_allocation_service.recalculate_strategy_capital()
  → 전략별 자본 할당 비율 재계산
```

### 8. 증권 토큰 갱신 (Securities Token Refresh)
**파일**: `app/jobs/securities_token_refresh.py`
**태그**: `@FEAT:securities-token @COMP:job @TYPE:core`

**실행 주기**: 6시간 (interval)
**Job ID**: `securities_token_refresh`
**역할**: 증권사 OAuth 토큰 자동 갱신 (만료 방지)

**실행 흐름**:
```
증권 계좌 조회 (account_type like 'SECURITIES_%')
  → SecuritiesExchangeFactory.create()
  → exchange.ensure_token() (자동 갱신 판단)
  → 만료 5분 전 또는 6시간 경과 시 재발급
```

**관련 문서**: `docs/korea_investment_api_auth.md` (토큰 유효기간 24시간)

### 9. WebSocket 연결 모니터링 (Check WebSocket Health)
**파일**: `app/__init__.py` (L552-598, `check_websocket_health_with_context`)
**태그**: `@FEAT:websocket @FEAT:background-scheduler @COMP:service @TYPE:integration`

**실행 주기**: 1분 (interval)
**Job ID**: `check_websocket_health`
**역할**: WebSocket 연결 상태 확인 및 자동 재연결

**실행 흐름**:
```
활성 계정 조회 (BINANCE, BYBIT만)
  → websocket_manager.get_connection() 상태 확인
  → 연결되지 않은 경우 start_websocket_for_account()
  → 연결 끊김 감지 시 auto_reconnect() 예약
```

### 10. Precision 캐시 업데이트 (Daily Precision Cache Update)
**파일**: `app/__init__.py` (L678-722, `update_precision_cache_with_context`)
**태그**: `@FEAT:exchange-integration @FEAT:background-scheduler @COMP:service @TYPE:helper`

**실행 주기**: 매일 03:07 (cron)
**Job ID**: `precision_cache_update`
**역할**: 거래소 심볼별 precision 정보 캐시 업데이트

**실행 흐름**:
```
활성 계좌 조회
  → 거래소별 그룹화
  → exchange_service.precision_cache.update_exchange_precision_cache()
  → 심볼별 price/amount precision 캐싱
```

### 11. 심볼 검증기 갱신 (Symbol Validator Refresh)
**파일**: `app/services/symbol_validator.py`
**태그**: `@FEAT:symbol-validation @FEAT:background-scheduler @COMP:service @TYPE:helper`

**실행 주기**: 매시 15분 (cron)
**Job ID**: `symbol_validator_refresh`
**역할**: 거래소별 유효 심볼 목록 갱신

**실행 흐름**:
```
symbol_validator.refresh_symbols_with_context() 호출
  → 거래소 API로 유효 심볼 목록 조회
  → 내부 캐시 업데이트
```

---

## 작업 등록 및 관리

### 작업 등록 파라미터
**파일**: `app/__init__.py` (register_background_jobs)
**태그**: `@FEAT:background-scheduler @COMP:service @TYPE:config`

```python
scheduler.add_job(
    func=my_function,           # 실행 함수
    args=[app],                 # Flask app context 전달
    trigger="interval",         # 트리거 타입
    seconds=10,                 # 실행 주기
    id='unique_job_id',         # 고유 ID
    max_instances=1,            # 동시 실행 방지
    replace_existing=True       # 재등록 시 충돌 방지
)
```

**핵심 파라미터**:
- `max_instances=1`: 중복 실행 방지 (필수)
- `coalesce=False`: 밀린 작업 합치지 않음
- `replace_existing=True`: 재시작 시 안전한 재등록

### Flask App Context 필수
**WHY**: 백그라운드 스레드에서 DB 접근 시 Flask app context 필요

```python
def my_job_with_context(app):
    """Flask app context 내에서 실행"""
    with app.app_context():
        # DB 접근 가능
        orders = OpenOrder.query.all()
```

---

## 성능 모니터링

### 실행 간격 확인
```bash
# 1초 간격 작업 확인
grep "재정렬 대상 조합" web_server/logs/app.log | tail -5

# 예상 출력: 약 1초 간격 타임스탬프
# 08:34:29,055
# 08:34:30,056 (+1.001s)
# 08:34:31,056 (+1.000s)
```

### 스케줄러 상태 API
```bash
curl -k https://222.98.151.163/api/system/scheduler/status
```

**응답 예시**:
```json
{
  "running": true,
  "jobs": [
    {
      "id": "rebalance_order_queue",
      "name": "Rebalance Order Queue",
      "next_run": "2025-10-10T08:34:30+09:00",
      "trigger": "interval[0:00:01]"
    }
  ]
}
```

---

## 트러블슈팅

### 문제 1: 스케줄러 중복 실행
**증상**: 로그에 "APScheduler 시작됨"이 2번 출력
**원인**: Flask Reloader 2개 프로세스 실행
**해결**: `app/__init__.py:336` 확인 (WERKZEUG_RUN_MAIN 체크)

### 문제 2: Flask app context 에러
**증상**: `RuntimeError: Working outside of application context`
**원인**: 백그라운드 스레드에서 app context 없이 DB 접근
**해결**: `with app.app_context()` 래퍼 함수 사용

### 문제 3: 작업 미실행
**증상**: 로그에 작업 실행 메시지 없음
**원인**: 스케줄러 미시작 또는 작업 등록 실패
**해결**:
```bash
# 1. 스케줄러 시작 확인
grep "APScheduler 시작됨" web_server/logs/app.log

# 2. 등록된 작업 확인
curl -k https://222.98.151.163/api/system/scheduler/status

# 3. 서비스 재시작
python run.py restart
```

---

## 설계 결정

### WHY: BackgroundScheduler vs AsyncIOScheduler
- **결정**: BackgroundScheduler 사용
- **이유**: Flask 메인 스레드와 독립 실행, ThreadPoolExecutor로 안정적 병렬 처리
- **trade-off**: AsyncIO 대비 성능은 낮지만 코드 복잡도 감소

### WHY: 메모리 캐시 vs Redis
- **결정**: Python dict 기반 메모리 캐시 (가격 캐시)
- **이유**: 1초 TTL로 짧은 수명, Redis 의존성 제거
- **제약**: 서버 재시작 시 캐시 초기화 (허용 가능)

### WHY: 작업 실행 주기 설정 (소수 주기 전략)
- **주문 큐 재정렬 (1초)**: 우선순위 변경 즉시 반영 필요
- **미체결 주문 업데이트 (29초)**: 거래소 API rate limit 고려 + 소수 주기
- **가격 캐시 갱신 (31초)**: 수량 계산 정확도 vs API 비용 절충 + 소수 주기
- **미실현 손익 계산 (307초)**: 5분 간격 + 소수 주기로 정각 트래픽 회피
- **Cron 작업 (분 단위 소수)**: 03:07, 21:03, 00:00:13 등 소수 시간대로 동시 실행 방지

**소수 주기 이점**:
- 정각/정분 동시 실행 방지 → CPU/메모리 스파이크 완화
- 거래소 API 요청 분산 → rate limit 여유 확보
- 시스템 안정성 향상

---

## 관련 문서
- [주문 큐 시스템](./order-queue-system.md)
- [웹훅 주문 처리](./webhook-order-processing.md)
- [거래소 통합](./exchange-integration.md)

---

## 전체 작업 요약표

| Job ID | 실행 주기 | Trigger | 함수 | 역할 |
|--------|----------|---------|------|------|
| `rebalance_order_queue` | 1초 | interval | `rebalance_all_symbols_with_context` | 주문 큐 재정렬 |
| `update_price_cache` | 31초 | interval | `update_price_cache_with_context` | 가격 캐시 갱신 |
| `update_open_orders` | 29초 | interval | `update_open_orders_with_context` | 미체결 주문 업데이트 |
| `calculate_unrealized_pnl` | 307초 | interval | `calculate_unrealized_pnl_with_context` | 미실현 손익 계산 |
| `check_websocket_health` | 1분 | interval | `check_websocket_health_with_context` | WebSocket 모니터링 |
| `securities_token_refresh` | 6시간 | interval | `refresh_securities_tokens_with_context` | 증권 토큰 갱신 |
| `precision_cache_update` | 매일 03:07 | cron | `update_precision_cache_with_context` | Precision 캐시 업데이트 |
| `symbol_validator_refresh` | 매시 15분 | cron | `symbol_validator.refresh_symbols_with_context` | 심볼 검증기 갱신 |
| `send_daily_summary` | 매일 21:03 | cron | `send_daily_summary_with_context` | 일일 요약 전송 |
| `calculate_daily_performance` | 매일 00:00:13 | cron | `calculate_daily_performance_with_context` | 일일 성과 계산 |
| `auto_rebalance_accounts` | 매시 17분 | cron | `auto_rebalance_all_accounts_with_context` | 자동 리밸런싱 |

**총 11개 백그라운드 작업 등록**

---

*Last Updated: 2025-10-12*
*Version: 2.0 (전체 작업 검증 완료)*
*Lines: ~400 (11개 작업 상세 문서화)*
