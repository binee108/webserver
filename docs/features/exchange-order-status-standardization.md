# 거래소 주문 상태 표준화 (Exchange Order Status Standardization)

> 🏷️ **TAG**: `@FEAT:order-status-standardization @COMP:transformer @TYPE:standardization`

거래소별 상이한 주문 상태를 표준 형식으로 통합하는 기능입니다. 모든 거래소의 주문 상태를 `StandardOrderStatus` 열거형으로 변환하여 일관된 처리를 가능하게 합니다.

## 📋 개요

### 문제점
- 각 거래소(Binance, Upbit, Bithumb, Bybit)마다 고유한 주문 상태 체계 사용
- 거래소별 상태 호환성 처리 로직 중복
- 새로운 거래소 추가 시 상태 매핑 코드 재구현 필요
- 주문 상태 기반 비즈니스 로직의 일관성 부족

### 해결책
- **StandardOrderStatus**: 거래소 중립적 표준 상태 정의
- **OrderStatusTransformer**: 거래소별 상태를 표준 상태로 변환
- **하위 호환성**: 기존 OrderStatus 클래스와의 호환성 유지
- **확장성**: 새로운 거래소 추가 시 상태 매핑만 등록

## 🏗️ 아키텍처

### 핵심 컴포넌트

```
┌─────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│   Exchange API      │    │ OrderStatusTransformer │    │ StandardOrderStatus │
│                     │───▶│                      │───▶│                     │
│ - BINANCE: NEW      │    │ - transform()         │    │ - PENDING           │
│ - UPBIT: wait       │    │ - get_supported()     │    │ - NEW               │
│ - BITHUMB: bid      │    │ - is_supported()      │    │ - OPEN              │
│ - BYBIT: Created    │    │ - validate()          │    │ - FILLED            │
│                     │    │                       │    │ - CANCELLED         │
└─────────────────────┘    └──────────────────────┘    └─────────────────────┘
```

### 상태 분류 체계

#### 활성 상태 (Active)
- **PENDING**: 거래소 전송 대기 중
- **NEW**: 새 주문 (거래소 수신 완료)
- **OPEN**: 미체결 상태
- **PARTIALLY_FILLED**: 부분 체결

#### 최종 상태 (Terminal)
- **FILLED**: 완전 체결
- **CANCELLED**: 취소됨
- **REJECTED**: 거부됨
- **EXPIRED**: 만료됨
- **FAILED**: 실패

## 📊 거래소별 상태 매핑

### BINANCE
| 원본 상태 | 표준 상태 | 설명 |
|---------|---------|------|
| NEW | NEW | 새 주문 |
| PARTIALLY_FILLED | PARTIALLY_FILLED | 부분 체결 |
| FILLED | FILLED | 완전 체결 |
| CANCELED/CANCELLED | CANCELLED | 취소됨 |
| REJECTED | REJECTED | 거부됨 |
| EXPIRED | EXPIRED | 만료됨 |

### UPBIT
| 원본 상태 | 표준 상태 | 설명 |
|---------|---------|------|
| wait | OPEN | 미체결 |
| watch | OPEN | 미체결 (호환성) |
| done | FILLED | 체결됨 |
| completed | FILLED | 체결됨 (호환성) |
| cancel/cancelled | CANCELLED | 취소됨 |

### BITHUMB
| 원본 상태 | 표준 상태 | 설명 |
|---------|---------|------|
| bid/ask | OPEN | 미체결 (매수/매도) |
| fill | FILLED | 체결됨 |
| complete | FILLED | 완전 체결 |
| cancel | CANCELLED | 취소됨 |

### BYBIT
| 원본 상태 | 표준 상태 | 설명 |
|---------|---------|------|
| Created | NEW | 생성된 주문 |
| New | OPEN | 새 주문 |
| PartiallyFilled | PARTIALLY_FILLED | 부분 체결 |
| Filled | FILLED | 완전 체결 |
| Cancelled/Canceled | CANCELLED | 취소됨 |
| Rejected | REJECTED | 거부됨 |

## 💻 사용 방법

### 기본 사용법

```python
from web_server.app.exchanges.transformers.order_status_transformer import OrderStatusTransformer
from web_server.app.constants import StandardOrderStatus

# 변환기 인스턴스 생성
transformer = OrderStatusTransformer()

# 거래소별 상태 변환
standard_status = transformer.transform('NEW', 'BINANCE')
print(standard_status)  # 'NEW'

standard_status = transformer.transform('wait', 'UPBIT')
print(standard_status)  # 'OPEN'

# 지원되는 거래소 확인
supported = transformer.get_supported_exchanges()
print(supported)  # ['BINANCE', 'UPBIT', 'BITHUMB', 'BYBIT']

# 거래소 지원 여부 확인
is_supported = transformer.is_supported_exchange('BINANCE')
print(is_supported)  # True
```

### 유효성 검증 포함 변환

```python
# 상태 변환과 유효성 검증을 함께 수행
result = transformer.transform_with_validation('NEW', 'BINANCE')
print(result)
# {
#     'original_status': 'NEW',
#     'transformed_status': 'NEW',
#     'is_valid_standard': True,
#     'is_terminal': False,
#     'is_active': True,
#     'exchange_supported': True
# }
```

### StandardOrderStatus 활용

```python
from web_server.app.constants import StandardOrderStatus

# 상태 유효성 확인
is_valid = StandardOrderStatus.is_valid('FILLED')
print(is_valid)  # True

# 최종 상태 확인
is_terminal = StandardOrderStatus.is_terminal('FILLED')
print(is_terminal)  # True

# 활성 상태 확인
is_active = StandardOrderStatus.is_active('NEW')
print(is_active)  # True

# 상태 정규화
normalized = StandardOrderStatus.normalize('canceled')
print(normalized)  # 'CANCELLED'
```

### 레거시 호환성

```python
# 기존 코드와의 호환성을 위한 어댑터
legacy_adapter = transformer.create_legacy_adapter()
legacy_status = legacy_adapter('NEW', 'BINANCE')
print(legacy_status)  # 'NEW'
```

## 🔧 확장 방법

### 새로운 거래소 추가

1. **OrderStatusTransformer에 상태 매핑 추가**

```python
# OrderStatusTransformer._STATUS_MAPPINGS에 추가
_STATUS_MAPPINGS = {
    # ... 기존 거래소 ...
    'NEW_EXCHANGE': {
        'status_a': StandardOrderStatus.NEW,
        'status_b': StandardOrderStatus.FILLED,
        'status_c': StandardOrderStatus.CANCELLED,
    }
}
```

2. **테스트 케이스 추가**

```python
# test_order_status_transformer.py에 테스트 추가
def test_transform_new_exchange_statuses(self):
    transformer = OrderStatusTransformer()

    assert transformer.transform('status_a', 'NEW_EXCHANGE') == StandardOrderStatus.NEW
    assert transformer.transform('status_b', 'NEW_EXCHANGE') == StandardOrderStatus.FILLED
```

### 새로운 표준 상태 추가

1. **StandardOrderStatus에 상수 추가**

```python
class StandardOrderStatus:
    # ... 기존 상수 ...
    NEW_STATUS = 'NEW_STATUS'  # 새로운 상태 추가

    VALID_STATUSES = [
        # ... 기존 상태 ...
        NEW_STATUS
    ]
```

2. **분류 업데이트**

```python
# 활성 또는 최종 상태 분류에 추가
ACTIVE_STATUSES = [
    # ... 기존 상태 ...
    NEW_STATUS
]
```

## 🧪 테스트

### 테스트 커버리지
- StandardOrderStatus 클래스 메서드 (100%)
- OrderStatusTransformer 변환 로직 (100%)
- 거래소별 상태 매핑 (100%)
- 하위 호환성 (100%)
- 통합 워크플로우 (100%)

### 테스트 실행

```bash
# StandardOrderStatus 테스트
pytest tests/test_standard_order_status.py -v

# OrderStatusTransformer 테스트
pytest tests/test_order_status_transformer.py -v

# 통합 테스트
pytest tests/test_exchange_status_integration.py -v
```

### 주요 테스트 시나리오

1. **기본 변환 테스트**: 모든 거래소의 상태가 올바르게 변환되는지 확인
2. **예외 처리 테스트**: 미지원 거래소/상태, None 입력 등
3. **하위 호환성 테스트**: 기존 OrderStatus와의 호환성
4. **상태 분류 테스트**: 활성/최종 상태 분류 정확성
5. **통합 워크플로우 테스트**: 실제 사용 시나리오 시뮬레이션

## 📈 마이그레이션 가이드

### 기존 시스템에서의 마이그레이션

1. **기존 OrderStatus 사용 코드 식별**

```python
# 기존 코드
from web_server.app.constants import OrderStatus
status = OrderStatus.from_exchange(original_status, exchange)
```

2. **새로운 표준화 시스템으로 변경**

```python
# 새로운 코드
from web_server.app.exchanges.transformers.order_status_transformer import OrderStatusTransformer
from web_server.app.constants import StandardOrderStatus

transformer = OrderStatusTransformer()
standard_status = transformer.transform(original_status, exchange)
```

3. **DB 데이터 마이그레이션**

```python
# 기존 주문 상태 데이터 정규화
for order in existing_orders:
    normalized_status = StandardOrderStatus.normalize(order.status)
    if normalized_status:
        order.status = normalized_status
        # DB 업데이트
```

### 롤백 계획

- 기존 OrderStatus 클래스는 하위 호환성을 위해 유지
- StandardOrderStatus.normalize() 메서드로 레거시 상태 처리
- 점진적 마이그레이션을 통한 안정성 확보

## 🎯 장점

### 1. 일관성
- 모든 거래소의 주문 상태를 표준 형식으로 통합
- 비즈니스 로직에서 거래소 종속적 코드 제거

### 2. 확장성
- 새로운 거래소 추가 시 상태 매핑만 등록
- 플러그인 아키텍처 기반 확장 지원

### 3. 유지보수성
- 단일 책임 원칙에 따른 분리된 구조
- 포괄적인 테스트 커버리지

### 4. 하위 호환성
- 기존 코드와의 호환성 유지
- 점진적 마이그레이션 지원

### 5. 검증 기능
- 상태 유효성 검증
- 활성/최종 상태 분류
- 변환 결과 상세 정보 제공

## 🔗 관련 기능

- **webhook-order-processing**: 웹훅 기반 주문 처리
- **order-tracking**: 주문 상태 추적 및 모니터링
- **exchange-integration**: 거래소 통합 레이어
- **order-queue-system**: 주문 대기열 관리

## 📝 Known Issues

### 현재 없음
- 모든 거래소 상태 매핑 완료
- 하위 호환성 확보
- 포괄적인 테스트 커버리지

---

**작성일**: 2025-01-22
**버전**: 1.0.0
**담당자**: documentation-manager