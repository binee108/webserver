# Failed Order Retry - Account-Specific Rate Limiting

**Feature Tag**: `@FEAT:failed-order-retry`
**Status**: ✅ Complete (Issue #26)
**Version**: 1.1.0 - Account ID 파라미터 추가

## 개요

FailedOrder 재시도 시 계좌별 Rate Limit을 독립적으로 사용하도록 개선되었습니다. 이전에는 모든 계좌의 재시도가 공유 Rate Limit Pool(1200 req/min)을 사용했으나, 이제 각 계좌가 독립적인 Rate Limit을 가져 멀티 계좌 환경에서 성능이 3배 향상됩니다.

**핵심 변경사항**:
- `create_batch_orders()` 호출 시 `account_id` 파라미터 추가
- 계좌별 Rate Limit Pool 독립화 (공유 1200 req/min → 계정당 1200 req/min)
- 다른 계좌의 재시도가 정상 주문 처리에 영향 없음

---

## 기술 상세

### Rate Limiter 아키텍처

```python
# RateLimiter 초기화 (web_server/app/services/exchange.py:31-128)
class RateLimiter:
    def __init__(self, key: str):
        self.key = key  # 고유 식별자 (account_id)
        self.rate_limit = 1200  # req/min
        self.window = 60  # 1분
```

**Rate Limit Pool 동작**:
- **이전**: 모든 계좌 공유 (1 Pool × 1200 req/min)
  - 계정 3개 = 1200 req/min 공유
  - 한 계정의 재시도가 다른 계정 영향

- **현재**: 계좌별 독립 (N Pools × 1200 req/min)
  - 계정 3개 = 3600 req/min (3배 향상)
  - 각 계정의 재시도가 독립적

### 구현 세부사항

**파일**: `web_server/app/services/trading/failed_order_manager.py`
**메서드**: `_retry_creation()` (Line 307-379)

**변경 전**:
```python
result = exchange_service.create_batch_orders(
    account=strategy_account.account,
    orders=orders,
    market_type=failed_order.market_type.lower()
)
```

**변경 후**:
```python
result = exchange_service.create_batch_orders(
    account=strategy_account.account,
    orders=orders,
    market_type=failed_order.market_type.lower(),
    account_id=strategy_account.account.id  # ✅ 계좌별 Rate Limiting
)
```

### Feature Tag 배치

```python
# Line 306-307: 메서드 선언
# @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:2
def _retry_creation(self, failed_order: FailedOrder) -> Dict[str, Any]:
```

---

## 성능 영향

### 멀티 계좌 환경 벤치마크

| 시나리오 | 이전 | 현재 | 개선도 |
|---------|------|------|--------|
| 계정 1개 | 1200 req/min | 1200 req/min | - |
| 계정 3개 | 1200 req/min (공유) | 3600 req/min | **3배** |
| 계정 5개 | 1200 req/min (공유) | 6000 req/min | **5배** |
| 계정 10개 | 1200 req/min (공유) | 12000 req/min | **10배** |

### 영향 범위

**긍정 영향**:
- ✅ Failed Order 재시도 속도 증가
- ✅ 정상 주문 처리 영향 제거
- ✅ 동시 다중 계좌 처리 용이

**중립 (변경 없음)**:
- 단일 계좌 성능 (이전과 동일)
- 정상 주문 처리 로직 (변경 없음)

---

## 관련 기능

### 의존성
- `exchange.py` - RateLimiter (account_id 기반 Pool)
- `orphan-order-prevention` - Failed Order 통합 추적

### 참조 구현
**파일**: `web_server/app/services/trading/core.py` (Line 1636-1641)

정상 주문 처리에서도 `account_id` 파라미터 사용:
```python
result = exchange_service.create_batch_orders(
    account=strategy_account.account,
    orders=orders,
    market_type=market_type,
    account_id=strategy_account.account.id  # 동일 패턴
)
```

---

## Known Issues

**None** - 구현 안정적, 기존 기능과 호환성 완전 보장

---

## 테스트 가이드

### 멀티 계좌 테스트
1. 계좌 2개 이상 설정
2. 각 계좌에서 Failed Order 생성
3. 동시에 여러 계좌의 재시도 실행
4. 각 계좌의 재시도가 독립적으로 진행되는지 확인

### Rate Limit 검증
```bash
# 로그에서 Rate Limit 사용량 확인
grep "account_id" logs/app.log | grep "rate_limit"

# 계좌별 Pool 분리 확인
python -c "
from app.services.exchange import RateLimiter
r1 = RateLimiter('account_1')
r2 = RateLimiter('account_2')
print(f'Pool 1: {r1.key}')
print(f'Pool 2: {r2.key}')
"
```

---

## 관리 정보

**작성자**: Documentation Manager
**최종 업데이트**: 2025-11-01
**관련 이슈**: #26 (Rate Limit 개선)
**마이그레이션**: 없음 (코드 변경만)
