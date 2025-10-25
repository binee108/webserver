# Upbit Batch Orders Unit Tests

업비트 거래소의 `create_batch_orders` 메서드에 대한 단위 테스트입니다.

## 테스트 파일

- **test_upbit_batch_orders.py**: Upbit 배치 주문 메서드 테스트

## 테스트 시나리오 (총 6개)

### 1. Rate Limiting Test (CRITICAL - 최우선)
**목표**: Lock 기반 순차 실행으로 초당 8회 제한을 준수하는지 검증

- 16개 주문을 배치로 실행
- 최소 2.0초 이상 소요되어야 함 (0.125초 × 16회)
- asyncio.Lock으로 완전한 순차 실행 보장
- 실제 테스트 결과: **2.02초 소요** (평균 0.126초/주문)

**검증 항목**:
- Rate Limit 준수 (초당 8회 = 0.125초 간격)
- 응답 포맷 (`success`, `implementation`, `summary`)
- 모든 주문 성공 (16/16)
- create_order_async 호출 횟수 (16회)

### 2. Empty Batch Test
**목표**: 빈 배치 처리 테스트

- 빈 리스트 `[]` 전달 시 정상 처리
- `implementation='NONE'` 반환
- 에러 없이 정상 완료

### 3. Error Handling Test
**목표**: 일부 주문 실패 시에도 나머지 계속 진행

- 4개 주문 중 2개 성공, 2개 실패 시뮬레이션
- 홀수 인덱스는 성공, 짝수 인덱스는 실패 (Insufficient balance)
- 전체 프로세스는 `success=True` 유지
- 실패한 주문에 에러 메시지 포함

**검증 항목**:
- 부분 실패 허용
- 실패 주문에 error 필드 존재
- 성공 주문에 order_id 포함

### 4. Market Type Validation Test
**목표**: Spot만 지원하는지 검증

- Futures 시장 타입 시도 시 ValueError 발생
- 에러 메시지: "Spot 거래만 지원"

### 5. Success Path Test
**목표**: 정상 경로 테스트 (모든 주문 성공)

- 3개 주문 실행 (BTC/KRW, ETH/KRW, XRP/KRW)
- 다양한 주문 타입 (LIMIT, MARKET)
- 모든 주문 성공 (3/3)
- 각 주문의 파라미터 검증 (symbol, side, type, amount, price)

**검증 항목**:
- 응답 포맷 완전성
- order_id 고유성
- create_order_async 호출 파라미터 정확성

### 6. Additional Params Test
**목표**: 추가 params 전달 테스트

- `params` 딕셔너리가 create_order_async로 전달되는지 확인
- 커스텀 필드 전달 및 수신 검증

## 테스트 실행 방법

### 전체 테스트 실행
```bash
# 프로젝트 루트에서
python -m pytest tests/exchanges/test_upbit_batch_orders.py -v
```

### 특정 테스트만 실행
```bash
# Rate Limiting 테스트만
python -m pytest tests/exchanges/test_upbit_batch_orders.py::TestUpbitBatchOrders::test_upbit_batch_orders_rate_limiting -v

# Error Handling 테스트만
python -m pytest tests/exchanges/test_upbit_batch_orders.py::TestUpbitBatchOrders::test_upbit_batch_orders_error_handling -v
```

### 상세 출력 포함
```bash
python -m pytest tests/exchanges/test_upbit_batch_orders.py -v -s
```

## 테스트 결과

```
============================== test session starts ==============================
platform darwin -- Python 3.10.12, pytest-8.3.5, pluggy-1.5.0
collected 6 items

tests/exchanges/test_upbit_batch_orders.py::TestUpbitBatchOrders::test_upbit_batch_orders_rate_limiting PASSED [ 16%]
tests/exchanges/test_upbit_batch_orders.py::TestUpbitBatchOrders::test_upbit_batch_orders_empty PASSED [ 33%]
tests/exchanges/test_upbit_batch_orders.py::TestUpbitBatchOrders::test_upbit_batch_orders_error_handling PASSED [ 50%]
tests/exchanges/test_upbit_batch_orders.py::TestUpbitBatchOrders::test_upbit_batch_orders_market_type_validation PASSED [ 66%]
tests/exchanges/test_upbit_batch_orders.py::TestUpbitBatchOrders::test_upbit_batch_orders_success_path PASSED [ 83%]
tests/exchanges/test_upbit_batch_orders.py::TestUpbitBatchOrders::test_upbit_batch_orders_with_params PASSED [100%]

============================== 6 passed in 3.37s ===============================
```

## 테스트 커버리지

### 검증된 기능
- ✅ Rate Limiting (초당 8회 제한)
- ✅ 빈 배치 처리
- ✅ 에러 핸들링 (부분 실패 허용)
- ✅ Market Type 검증 (Spot 전용)
- ✅ 정상 경로 (모든 주문 성공)
- ✅ 추가 params 전달

### 핵심 검증 포인트
1. **Rate Limiting**: asyncio.Lock 기반 완전 순차 실행으로 초당 8회 제한 준수
2. **에러 핸들링**: 일부 주문 실패해도 전체 프로세스는 계속 진행
3. **응답 포맷**: 표준화된 응답 구조 (`success`, `results`, `summary`, `implementation`)
4. **Market Type**: Spot 시장만 지원하며, 다른 시장 타입은 ValueError 발생
5. **파라미터 전달**: symbol, side, type, amount, price, params 등 모든 파라미터 정확히 전달

## 주의사항

1. **Mock 사용**: 실제 API 호출 대신 AsyncMock 사용 (Upbit Testnet 미지원)
2. **Rate Limiting 검증**: 가장 중요한 테스트 - 반드시 통과해야 함
3. **시간 여유**: `elapsed >= 2.0` (2.0초 예상, 실제 2.02초 소요)
4. **테스트 격리**: 각 테스트는 독립적으로 실행 가능

## 의존성

- pytest
- pytest-asyncio
- PyJWT (jwt 모듈)
- unittest.mock (AsyncMock, patch)

## 파일 구조

```
tests/
├── conftest.py                          # pytest 설정 (Python path 추가)
├── exchanges/
│   ├── __init__.py
│   ├── test_upbit_batch_orders.py      # Upbit 배치 주문 테스트
│   └── README.md                        # 이 문서
```

## 추가 개선 사항

향후 추가 가능한 테스트:
- 매우 큰 배치 (100개 이상 주문) 처리 테스트
- 네트워크 타임아웃 시나리오
- 동시성 테스트 (여러 배치 동시 실행)
- Rate Limit 초과 시 재시도 로직 (현재는 단순 딜레이만 사용)
