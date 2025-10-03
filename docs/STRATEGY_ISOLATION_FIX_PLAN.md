# 전략별 주문 격리 수정 계획서

**작성일**: 2025-10-03
**최종 업데이트**: 2025-10-03 17:56 KST
**목적**: 전략 간 주문 간섭 방지, DB 기반 전략 격리 보장
**우선순위**: 🔴 **최우선** (다른 전략 주문 취소 위험)
**상태**: ✅ **Phase 1 완료** | Phase 2 대기 중

---

## 🚨 치명적 결함 분석

### 문제 요약
**현재 `cancel_all_orders()`는 거래소 API에서 계좌의 모든 주문을 조회하여 취소**
→ 동일 계좌를 사용하는 다른 전략의 주문까지 취소될 위험

### 결함 근본 원인

#### 현재 로직 흐름
```
webhook: CANCEL_ALL_ORDER (전략 A)
         ↓
order_manager.cancel_all_orders(strategy_id=A, account_id=X)
         ↓
exchange_service.get_open_orders(account_id=X)  ❌
         ↓
거래소 응답: [주문1(전략A), 주문2(전략B), 주문3(전략A)]
         ↓
모든 주문 취소 시도  ❌ 전략 B 주문도 취소됨!
```

#### 거래소 API의 한계
```python
# order_manager.py:252
open_orders_result = self.service.get_open_orders(account.id, symbol, strategy_market_type)
                                   ↓
                     거래소 API: GET /api/v3/openOrders
                                   ↓
                     응답: 계좌의 "모든" 열린 주문
                     (전략 정보 없음, 구분 불가능)
```

**거래소는 전략 개념을 모름** → DB로만 구분 가능

#### DB 구조는 이미 전략 격리 지원
```python
# models.py:283-303
class OpenOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    strategy_account_id = db.Column(db.Integer, db.ForeignKey('strategy_accounts.id'), nullable=False)
    exchange_order_id = db.Column(db.String(100), unique=True, nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    # ...

# ✅ strategy_account_id FK로 전략별 완전 격리 가능
# ✅ 하지만 cancel_all_orders()가 이를 활용하지 않음!
```

---

## 📋 수정 계획

### 설계 원칙
1. **단일 소스**: DB `OpenOrder` 테이블 = 유일한 진실의 원천
2. **전략 격리**: `strategy_account_id` FK로 완전 격리
3. **최소 수정**: 기존 구조 유지, 조회 방식만 변경
4. **공개/비공개 통합**: 구분 불필요 (FK가 자동 격리)

---

## Phase 1: DB 기반 주문 취소로 전환 (긴급)

### 1.1 `cancel_all_orders()` 수정

**파일**: `order_manager.py:195-294`

#### 변경 전 (위험한 로직)
```python
def cancel_all_orders(self, strategy_id: int, symbol: Optional[str] = None,
                      account_id: Optional[int] = None,
                      timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    # ... 전략/계좌 조회 ...

    # ❌ 문제: 거래소 API에서 계좌의 모든 주문 조회 (전략 구분 없음)
    open_orders_result = self.service.get_open_orders(account.id, symbol, strategy_market_type)
    if not open_orders_result['success']:
        return open_orders_result

    open_orders = open_orders_result.get('orders', [])

    # ❌ 문제: 다른 전략의 주문도 포함되어 있을 수 있음
    for order in open_orders:
        cancel_result = self.service.cancel_order(order.id, order.symbol, account.id)
        # ...
```

#### 변경 후 (안전한 로직)
```python
def cancel_all_orders(self, strategy_id: int, symbol: Optional[str] = None,
                      account_id: Optional[int] = None,
                      timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    # ... 전략/계좌 조회 ...

    # ✅ 해결: DB에서 해당 전략의 주문만 조회 (전략 격리 보장)
    db_query = OpenOrder.query.filter_by(strategy_account_id=strategy_account.id)
    if symbol:
        db_query = db_query.filter_by(symbol=symbol)

    db_open_orders = db_query.all()

    if not db_open_orders:
        logger.info(f"취소할 미체결 주문이 없습니다 - 전략: {strategy_id}, 계좌: {account.id}")
        return {
            'success': True,
            'cancelled_orders': 0,
            'failed_orders': 0,
            'message': '취소할 미체결 주문이 없습니다'
        }

    # ✅ 해결: DB 기록 기준으로 취소 (전략 격리 보장)
    cancelled_count = 0
    failed_count = 0
    results = []

    for db_order in db_open_orders:
        try:
            # DB의 exchange_order_id로 거래소 API 호출
            cancel_result = self.service.cancel_order(
                db_order.exchange_order_id,  # 거래소 주문 ID
                db_order.symbol,
                account.id
            )

            if cancel_result['success']:
                cancelled_count += 1
                logger.info(f"✅ 주문 취소 성공: {db_order.exchange_order_id} (전략: {strategy_id})")
            else:
                failed_count += 1
                logger.warning(f"❌ 주문 취소 실패: {db_order.exchange_order_id} - {cancel_result.get('error')}")

            results.append({
                'order_id': db_order.exchange_order_id,
                'symbol': db_order.symbol,
                'success': cancel_result['success']
            })

        except Exception as e:
            failed_count += 1
            logger.error(f"주문 취소 중 오류: {db_order.exchange_order_id} - {e}")
            results.append({
                'order_id': db_order.exchange_order_id,
                'symbol': db_order.symbol,
                'success': False,
                'error': str(e)
            })

    # ... 결과 반환 ...
```

#### 핵심 변경사항
| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| **조회 소스** | 거래소 API | DB `OpenOrder` 테이블 |
| **필터링** | `account.id` + `symbol` | `strategy_account_id` + `symbol` |
| **전략 격리** | ❌ 불가능 (거래소가 전략 모름) | ✅ 보장 (FK로 격리) |
| **타 전략 간섭** | ❌ 위험 있음 | ✅ 원천 차단 |

---

### 1.2 공개/비공개 전략 구분 불필요

#### 기존 우려사항
> "공개 전략의 경우, 해당 전략을 구독한 다른 유저의 연동된 계좌의 열린 주문도 취소가 되어야 한다"

#### 해결 방법: 이미 해결되어 있음
```python
# webhook_service.py:399-412
strategy_accounts = strategy.strategy_accounts  # ✅ 소유자 + 구독자 모두 포함

for sa in strategy_accounts:
    account = sa.account
    # 각 계좌마다 cancel_all_orders 호출
    cancel_result = order_service.cancel_all_orders(
        strategy_id=strategy.id,
        symbol=symbol,
        account_id=account.id,  # ✅ 각 계좌 독립 처리
        timing_context={'webhook_received_at': webhook_received_at}
    )
```

**핵심**:
- `strategy.strategy_accounts`가 이미 모든 계좌 포함
- 각 계좌의 `strategy_account_id`가 다름 → FK로 자동 격리
- 공개/비공개 여부 무관하게 동일 로직 적용 가능

---

### 1.3 예상 결과

#### 테스트 시나리오
```
상황:
- 전략 A (id=1): BTCUSDT 주문 3개 (계좌 X)
- 전략 B (id=2): BTCUSDT 주문 2개 (계좌 X, 동일 계좌 사용)

CANCEL_ALL_ORDER 웹훅 전송 (전략 A, symbol=BTCUSDT)
```

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| **조회 쿼리** | 거래소: 계좌 X의 모든 BTCUSDT 주문 | DB: `strategy_account_id=1` + `symbol=BTCUSDT` |
| **조회 결과** | 5개 (전략 A 3개 + 전략 B 2개) | 3개 (전략 A만) |
| **취소 대상** | 5개 모두 취소 ❌ | 3개만 취소 ✅ |
| **전략 B 영향** | 2개 주문 취소됨 ❌ | 영향 없음 ✅ |

---

## Phase 2: 성능 최적화 (Phase 1 안정화 후)

### 2.1 배치 취소 메서드 추가 (선택사항)

**파일**: `order_manager.py` (신규 메서드)

```python
def cancel_all_orders_batch(self, strategy_accounts: List[StrategyAccount],
                            symbol: Optional[str] = None,
                            timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """다중 계좌의 주문을 배치로 취소 (병렬 처리, 전략 격리 보장)

    Args:
        strategy_accounts: 전략 계좌 리스트 (소유자 + 구독자)
        symbol: 심볼 필터 (None이면 전체)
        timing_context: 타이밍 정보

    Returns:
        Dict with keys: success, total_cancelled, total_failed, results
    """
    from concurrent.futures import ThreadPoolExecutor
    from flask import current_app

    def cancel_for_account(sa: StrategyAccount) -> Dict[str, Any]:
        """단일 계좌의 주문 취소 (스레드 안전)"""
        # Flask app context 전달 필요
        with current_app.app_context():
            # ✅ DB 기반 조회로 전략 격리 보장
            db_query = OpenOrder.query.filter_by(strategy_account_id=sa.id)
            if symbol:
                db_query = db_query.filter_by(symbol=symbol)

            db_open_orders = db_query.all()

            cancelled = 0
            failed = 0
            for db_order in db_open_orders:
                result = self.service.cancel_order(
                    db_order.exchange_order_id,
                    db_order.symbol,
                    sa.account_id
                )
                if result['success']:
                    cancelled += 1
                else:
                    failed += 1

            return {
                'account_id': sa.account_id,
                'cancelled': cancelled,
                'failed': failed
            }

    # 병렬 처리 (5-10x 성능 향상)
    with ThreadPoolExecutor(max_workers=min(len(strategy_accounts), 10)) as executor:
        results = list(executor.map(cancel_for_account, strategy_accounts))

    total_cancelled = sum(r['cancelled'] for r in results)
    total_failed = sum(r['failed'] for r in results)

    return {
        'success': True,
        'total_cancelled': total_cancelled,
        'total_failed': total_failed,
        'results': results
    }
```

**장점**:
- ✅ 병렬 처리로 N배 성능 향상
- ✅ DB 기반 조회로 전략 격리 유지
- ✅ 공개 전략 구독자 다수일 때 효과적

---

## 🔍 검증 계획

### 테스트 1: 전략 격리 검증
```bash
# 준비
1. 전략 A 생성 (BTCUSDT, 계좌 X)
2. 전략 B 생성 (BTCUSDT, 계좌 X, 동일 계좌 사용)
3. 각 전략에서 LIMIT 주문 3개씩 생성

# 실행
curl -k -X POST https://222.98.151.163/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "전략A",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "order_type": "CANCEL_ALL_ORDER",
    "token": "<전략A_토큰>"
  }'

# 검증
- 전략 A 주문: 3개 → 0개 ✅
- 전략 B 주문: 3개 → 3개 (영향 없음) ✅
```

### 테스트 2: 공개 전략 구독자 검증
```bash
# 준비
1. 공개 전략 생성 (소유자: 계좌 A)
2. 사용자 B가 구독 (계좌 B)
3. 사용자 C가 구독 (계좌 C)
4. 각 계좌에서 주문 3개씩 생성

# 실행
CANCEL_ALL_ORDER 웹훅 전송

# 검증
- 계좌 A 주문: 3개 → 0개 ✅
- 계좌 B 주문: 3개 → 0개 ✅
- 계좌 C 주문: 3개 → 0개 ✅
```

---

## ✅ Phase 1 완료 보고서

### 구현 내용
**파일**: `order_manager.py:247-311`

#### 핵심 변경
```python
# 변경 전: 거래소 API 조회 (전략 구분 불가)
open_orders_result = self.service.get_open_orders(account.id, symbol, strategy_market_type)

# 변경 후: DB 조회 (전략 격리 보장)
db_query = OpenOrder.query.filter_by(strategy_account_id=strategy_account.id)
if symbol:
    db_query = db_query.filter_by(symbol=symbol)
db_open_orders = db_query.all()

for db_order in db_open_orders:
    cancel_result = self.service.cancel_order(
        db_order.exchange_order_id,  # 거래소 주문 ID
        db_order.symbol,
        account.id
    )
```

### 테스트 결과

#### 테스트 1: 전략 격리 검증 ✅
**시나리오**: 동일 계좌(account_id=1)에 2개 전략의 주문 생성
- test1: ETHUSDT 주문 1개 (8389765972051697424)
- test2: ETHUSDT 주문 1개 (8389765972051727679)

**결과**:
```
test1 CANCEL_ALL_ORDER 실행
→ 로그: 📋 DB에서 조회된 미체결 주문: 1개 (전략: 1, 계좌: 1)
→ 로그: ✅ 주문 취소 성공: 8389765972051697424 (전략: 1)
→ test2 주문은 유지됨 ✅

test2 CANCEL_ALL_ORDER 실행
→ 로그: 📋 DB에서 조회된 미체결 주문: 1개 (전략: 2, 계좌: 1)
→ 로그: ✅ 주문 취소 성공: 8389765972051727679 (전략: 2)
→ 전략 격리 완벽 ✅
```

#### 테스트 2: 다중 계좌 취소 ✅
**시나리오**: test1 전략에 2개 계좌 연동, 총 3개 주문 생성
- account_id=2: 783414559446 (BUY @95000)
- account_id=1: 783414951438 (SELL @120000)
- account_id=2: 783414951427 (SELL @120000)

**결과**:
```
test1 CANCEL_ALL_ORDER 실행
→ 로그: 📋 DB에서 조회된 미체결 주문: 1개 (전략: 1, 계좌: 1)
→ 로그: ✅ 주문 취소 성공: 783414951438 (전략: 1)
→ 로그: 📋 DB에서 조회된 미체결 주문: 2개 (전략: 1, 계좌: 2)
→ 로그: ✅ 주문 취소 성공: 783414559446 (전략: 1)
→ 로그: ✅ 주문 취소 성공: 783414951427 (전략: 1)
→ 총 3개 주문 모두 취소 ✅
```

### 검증 완료
- ✅ `order_manager.py:cancel_all_orders()` 수정
  - ✅ 거래소 API 조회 → DB 조회로 변경
  - ✅ `strategy_account_id` 필터링 추가
  - ✅ 로그 메시지 업데이트 (전략 ID 표시)
- ✅ 테스트 1 (전략 격리) 실행 및 검증
- ✅ 테스트 2 (다중 계좌) 실행 및 검증
- ✅ `/web_server/logs/` 정리 후 재시작
- ✅ `logs/app.log` 확인 (에러 없음, 정상 작동)

---

## 📝 Phase 2 체크리스트 (선택사항)

### Phase 2: 성능 최적화
**목표**: 공개 전략의 다중 구독자 처리 성능 향상 (5-10배)

**진행 조건**:
- Phase 1 안정화 확인 후
- 사용자 요청 시

**작업 목록**:
- [ ] `cancel_all_orders_batch()` 메서드 추가
- [ ] `webhook_service.py` 배치 메서드로 전환
- [ ] Flask app context 전달 구현
- [ ] 성능 테스트 (10개 계좌 시나리오)

---

## 🎯 기대 효과

### 안정성
- ✅ 전략 간 완전 격리 보장
- ✅ 타 전략 간섭 원천 차단
- ✅ DB를 단일 진실의 원천으로 사용

### 성능
- ✅ DB 인덱스 활용 (strategy_account_id FK)
- ✅ 불필요한 거래소 API 호출 제거
- ✅ Phase 2: 병렬 처리로 5-10배 향상

### 유지보수성
- ✅ 공개/비공개 구분 불필요 (통합 로직)
- ✅ 단일 소스 원칙 준수 (CLAUDE.md)
- ✅ 최소 수정으로 최대 효과

---

**다음 단계**: Phase 1 구현 승인 대기
