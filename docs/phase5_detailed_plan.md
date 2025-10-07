# Phase 5: UnifiedExchangeFactory 증권 지원 확장 - 상세 계획

## 📋 작업 개요

**목표**: UnifiedExchangeFactory의 증권 지원 로직 검증 및 개선

**예상 소요 시간**: 30분

**담당**: Backend Developer

---

## 🔍 현재 상태 분석

### 1. UnifiedExchangeFactory 구현 상태

**파일**: `web_server/app/exchanges/unified_factory.py`

**현재 구현된 기능**:
- ✅ `create(account)` 메서드: Account.account_type 기반 분기
- ✅ Crypto 계좌 처리: CryptoExchangeFactory 호출
- ✅ Securities 계좌 처리: SecuritiesExchangeFactory 호출
- ✅ `list_exchanges(account_type)` 메서드: 거래소 목록 조회
- ✅ `is_supported(exchange_name, account_type)` 메서드: 지원 여부 확인

**사용 예시**:
```python
# Crypto 계좌
account = Account.query.filter_by(exchange='BINANCE').first()
exchange = UnifiedExchangeFactory.create(account)
# → BinanceExchange 반환

# Securities 계좌
account = Account.query.filter_by(exchange='KIS').first()
exchange = UnifiedExchangeFactory.create(account)
# → KoreaInvestmentExchange 반환
```

---

## 📝 작업 항목

### ✅ 작업 1: 코드 검증 및 개선

#### 1-1. 현재 구현 검증
- [x] AccountType.is_crypto() 메서드 사용 확인
- [x] AccountType.is_securities() 메서드 사용 확인
- [x] CryptoExchangeFactory import 경로 확인
- [x] SecuritiesExchangeFactory import 경로 확인
- [x] 에러 처리 로직 확인

#### 1-2. 개선 사항 구현 (필요 시)

**A. 타입 힌트 추가/개선**
- 반환 타입: `Union[BaseCryptoExchange, BaseSecuritiesExchange]`
- Account 모델 타입 힌트 명확화

**B. 로깅 개선**
- 성공/실패 케이스별 상세 로깅
- account_id, exchange, account_type 정보 포함

**C. 에러 메시지 개선**
- 더 명확한 에러 메시지
- 지원되는 타입 목록 명시

**D. Docstring 보완**
- Examples 섹션 추가
- Raises 섹션 상세화
- Args/Returns 타입 명시

**E. 유닛 테스트 작성 가능성 검토**
- 테스트 케이스 시나리오 문서화 (구현은 하지 않음)

---

## 🎯 완료 조건

### 필수 조건
- [ ] AccountType 기반 분기 로직 정상 동작 확인
- [ ] CryptoExchangeFactory 정상 호출 확인
- [ ] SecuritiesExchangeFactory 정상 호출 확인
- [ ] Import 오류 없음 (Python 구문 검증)
- [ ] 로깅이 적절히 추가됨

### 선택 조건
- [ ] 타입 힌트 개선 (TYPE_CHECKING 사용 권장)
- [ ] Docstring 보완
- [ ] 에러 메시지 개선

---

## 📊 검증 방법

### 1. Python 구문 검증
```bash
python3 -m py_compile web_server/app/exchanges/unified_factory.py
```

### 2. Import 체인 검증
```bash
python3 -c "from app.exchanges import UnifiedExchangeFactory; print('✅ Import 성공')"
```

### 3. 코드 스타일 검증 (선택)
```bash
flake8 web_server/app/exchanges/unified_factory.py --max-line-length=120
```

---

## 🚫 작업 범위 제외

**다음 항목은 이 Phase에서 수행하지 않습니다**:
- ❌ 실제 거래소 API 호출 테스트
- ❌ 통합 테스트 작성 및 실행
- ❌ DB 마이그레이션
- ❌ 새로운 증권사 어댑터 추가 (KoreaInvestmentExchange는 이미 구현됨)
- ❌ CryptoExchangeFactory 수정
- ❌ SecuritiesExchangeFactory 수정

---

## 📁 수정 대상 파일

### 주 파일
- `web_server/app/exchanges/unified_factory.py` (검증 및 개선)

### 참조 파일 (읽기 전용)
- `web_server/app/exchanges/crypto/factory.py`
- `web_server/app/exchanges/securities/factory.py`
- `web_server/app/constants.py` (AccountType)
- `web_server/app/models.py` (Account 모델)

---

## 🎓 개선 방향 가이드

### 1. 타입 안전성 개선

**현재**:
```python
def create(account: Account):
    # 반환 타입 명시 없음
```

**개선안**:
```python
from typing import Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .crypto.base import BaseCryptoExchange
    from .securities.base import BaseSecuritiesExchange

def create(account: Account) -> Union['BaseCryptoExchange', 'BaseSecuritiesExchange']:
    """
    계좌 타입에 따라 적절한 거래소 어댑터 생성

    Args:
        account: Account 모델 (DB)

    Returns:
        BaseCryptoExchange 또는 BaseSecuritiesExchange 인스턴스

    Raises:
        ValueError: account가 None인 경우
        ValueError: 지원하지 않는 계좌 타입
        ValueError: 지원하지 않는 거래소

    Examples:
        >>> # Crypto 계좌
        >>> account = Account.query.filter_by(exchange='BINANCE').first()
        >>> exchange = UnifiedExchangeFactory.create(account)
        >>> isinstance(exchange, BaseCryptoExchange)
        True

        >>> # Securities 계좌
        >>> account = Account.query.filter_by(exchange='KIS').first()
        >>> exchange = UnifiedExchangeFactory.create(account)
        >>> isinstance(exchange, BaseSecuritiesExchange)
        True
    """
```

### 2. 로깅 개선

**현재**:
```python
logger.info(f"🔹 Crypto Factory 호출 (exchange={account.exchange}, account_id={account.id})")
```

**개선안**:
```python
logger.info(
    f"🔹 Crypto Factory 호출 "
    f"(account_id={account.id}, exchange={account.exchange}, "
    f"account_type={account_type}, testnet={account.is_testnet})"
)
```

### 3. 에러 처리 개선

**현재**:
```python
if not account:
    raise ValueError("Account 객체가 필요합니다")
```

**개선안**:
```python
if not account:
    raise ValueError(
        "UnifiedExchangeFactory.create()는 Account 객체가 필요합니다. "
        "None이 전달되었습니다."
    )

if not hasattr(account, 'account_type'):
    raise ValueError(
        f"Account 객체에 account_type 속성이 없습니다. "
        f"account_id={getattr(account, 'id', 'N/A')}"
    )
```

---

## 📌 참고 사항

### AccountType 클래스 메서드
```python
# constants.py
class AccountType:
    CRYPTO = 'CRYPTO'
    STOCK = 'STOCK'

    @classmethod
    def is_crypto(cls, account_type):
        return account_type == cls.CRYPTO

    @classmethod
    def is_securities(cls, account_type):
        return account_type == cls.STOCK
```

### CryptoExchangeFactory 호출 시그니처
```python
# exchanges/crypto/factory.py
@staticmethod
def create(exchange_name: str, api_key: str, secret: str, testnet: bool = False):
    """크립토 거래소 인스턴스 생성"""
```

### SecuritiesExchangeFactory 호출 시그니처
```python
# exchanges/securities/factory.py
@classmethod
def create(cls, account: 'Account') -> BaseSecuritiesExchange:
    """증권 거래소 인스턴스 생성"""
```

---

## ✅ 성공 기준

1. **구문 오류 없음**: `python3 -m py_compile` 통과
2. **Import 오류 없음**: 순환 참조 없음
3. **로직 검증 완료**: account_type 기반 분기 정상
4. **코드 품질 향상**: 타입 힌트, Docstring, 로깅 개선
5. **CLAUDE.md 준수**: DRY 원칙, 단일 소스 원칙 준수

---

## 🚀 다음 단계 (Phase 5 완료 후)

- Phase 6: 웹훅 메시지 포맷 문서 작성
- Phase 7: 코드 검토 및 정리
- 최종: 사용자 수동 테스트

---

**작성일**: 2025-10-07
**담당**: Backend Developer Agent
**예상 완료 시간**: 30분
