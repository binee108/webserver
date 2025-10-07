# Exchange 디렉토리 구조 개선 계획

## 📋 프로젝트 개요

**목적**: 한국투자증권 API 통합을 위해 `/app/exchanges`와 `/app/securities` 디렉토리를 통합하여 체계적인 구조로 개선

**브랜치**: `feature/securities-integration`

**작업 시작일**: 2025-10-07

---

## 🎯 최종 디렉토리 구조

```
web_server/app/exchanges/
├── __init__.py                    # 통합 진입점 (하위 호환)
├── base.py                        # 공통 BaseExchange (유지)
├── models.py                      # 공통 데이터 모델 (유지)
├── exceptions.py                  # 공통 예외 클래스 (신규)
├── metadata.py                    # 거래소 메타데이터 (유지)
├── unified_factory.py             # UnifiedExchangeFactory (대폭 수정)
├── README.md                      # 전체 설명서 (업데이트)
│
├── crypto/                        # 크립토 거래소 디렉토리 (신규)
│   ├── __init__.py                # Crypto 진입점
│   ├── base.py                    # BaseCryptoExchange
│   ├── factory.py                 # CryptoExchangeFactory
│   ├── binance.py                 # BinanceExchange (이동)
│   ├── upbit.py                   # UpbitExchange (이동)
│   └── README.md                  # Crypto 사용 가이드
│
└── securities/                    # 증권 거래소 디렉토리 (이동)
    ├── __init__.py                # Securities 진입점
    ├── base.py                    # BaseSecuritiesExchange (이동)
    ├── factory.py                 # SecuritiesExchangeFactory (이동)
    ├── models.py                  # StockOrder, StockBalance 등 (이동)
    ├── exceptions.py              # Securities 특화 예외 (이동)
    ├── korea_investment.py        # KoreaInvestmentExchange (이동)
    └── README.md                  # Securities 사용 가이드
```

---

## 📝 Phase별 작업 계획

### ✅ Phase 0: 체크포인트 생성 및 계획 문서화

**담당**: General Agent

**작업 내용**:
1. 현재 상태 Git 커밋 (롤백 포인트)
2. 구현 계획 문서화 (`docs/task_plan.md` 생성) ✅
3. Todo 리스트 업데이트 ✅

**Git 커밋 메시지**:
```
chore: checkpoint before exchanges refactoring

현재 상태 저장 (롤백 포인트):
- feature/securities-integration 브랜치 작업 중
- securities/ 디렉토리 기본 구조 존재
- 다음: exchanges 디렉토리 통합 구조로 개선
```

**완료 조건**:
- [ ] Git 커밋 완료
- [x] `docs/task_plan.md` 생성
- [x] Todo 리스트 업데이트

---

### 🔄 Phase 1: 디렉토리 생성 및 파일 이동

**담당**: Backend Developer Agent

**작업 내용**:
1. 새 디렉토리 생성
   - `exchanges/crypto/`
   - `exchanges/securities/`

2. 크립토 파일 이동 (Git history 보존)
   - `exchanges/binance.py` → `exchanges/crypto/binance.py`
   - `exchanges/upbit.py` → `exchanges/crypto/upbit.py`
   - `exchanges/factory.py` → `exchanges/crypto/factory.py`

3. 증권 파일 이동
   - `securities/base.py` → `exchanges/securities/base.py`
   - `securities/factory.py` → `exchanges/securities/factory.py`
   - `securities/models.py` → `exchanges/securities/models.py`
   - `securities/exceptions.py` → `exchanges/securities/exceptions.py`
   - `securities/korea_investment.py` → `exchanges/securities/korea_investment.py`
   - `securities/__init__.py` → `exchanges/securities/__init__.py`

4. 기존 `securities/` 디렉토리 제거

**Git 커밋 메시지**:
```
refactor: exchanges 디렉토리 구조 개선 - crypto/securities 분리

주요 변경사항:
- crypto/ 디렉토리 생성 (Binance, Upbit 이동)
- securities/ 디렉토리를 exchanges/securities로 통합
- Git history 보존 (git mv 사용)

Breaking Changes: 없음 (하위 호환 유지)
```

**완료 조건**:
- [ ] 모든 파일이 올바른 위치로 이동
- [ ] Git history 보존 확인 (`git log --follow`)
- [ ] 기존 `securities/` 디렉토리 삭제 완료

---

### 🔧 Phase 2: 파일 내용 수정 (Factory 분리)

**담당**: Backend Developer Agent

**작업 내용**:
1. 공통 예외 클래스 생성 (`exchanges/exceptions.py`)
2. Crypto 모듈 생성
   - `crypto/__init__.py` (진입점)
   - `crypto/base.py` (BaseCryptoExchange)
   - `crypto/factory.py` 수정 (ExchangeFactory → CryptoExchangeFactory)

3. Securities 모듈 수정
   - `securities/__init__.py` (진입점 수정)
   - `securities/factory.py` (import 경로 수정)

4. UnifiedExchangeFactory 대폭 수정
   - account_type 기반 자동 분기
   - CryptoExchangeFactory/SecuritiesExchangeFactory 통합

5. `exchanges/__init__.py` 하위 호환 추가

**Git 커밋 메시지**:
```
refactor: Factory 분리 및 UnifiedExchangeFactory 구현

주요 변경사항:
- CryptoExchangeFactory 생성 (crypto/factory.py)
- SecuritiesExchangeFactory import 경로 변경
- UnifiedExchangeFactory 대폭 개선 (account_type 기반 자동 분기)
- 공통 예외 클래스 exchanges/exceptions.py로 통합
- 하위 호환성 유지 (exchanges/__init__.py에서 재export)

Breaking Changes: 없음
```

**완료 조건**:
- [ ] CryptoExchangeFactory 정상 동작
- [ ] SecuritiesExchangeFactory 정상 동작
- [ ] UnifiedExchangeFactory.create() 정상 분기
- [ ] Python import 오류 없음

---

### 🔗 Phase 3: Import 경로 수정

**담당**: Backend Developer Agent

**작업 내용**:

영향받는 파일 (총 6개):
1. `app/services/exchange.py`
   - `from app.exchanges.base import BaseExchange` → `from app.exchanges.crypto.base import BaseCryptoExchange`
   - `from app.securities.base import BaseSecuritiesExchange` → `from app.exchanges.securities.base import BaseSecuritiesExchange`

2. `app/jobs/securities_token_refresh.py`
   - `from app.securities.factory import SecuritiesFactory` → `from app.exchanges.securities.factory import SecuritiesExchangeFactory`
   - `SecuritiesFactory.create_exchange()` → `SecuritiesExchangeFactory.create()`

3. `app/exceptions/exchange_exception.py`
   - `from app.exchanges.base import ExchangeError` → `from app.exchanges.exceptions import ExchangeError`

4. `app/services/symbol_validator.py`
   - 필요 시 수정

5. `app/exchanges/crypto/binance.py`
   - `from app.exchanges.base import BaseExchange` → `from app.exchanges.crypto.base import BaseCryptoExchange`
   - `class BinanceExchange(BaseExchange)` → `class BinanceExchange(BaseCryptoExchange)`

6. `app/exchanges/crypto/upbit.py`
   - `from app.exchanges.base import BaseExchange` → `from app.exchanges.crypto.base import BaseCryptoExchange`
   - `class UpbitExchange(BaseExchange)` → `class UpbitExchange(BaseCryptoExchange)`

7. `app/exchanges/securities/korea_investment.py`
   - `from app.securities.base import BaseSecuritiesExchange` → `from app.exchanges.securities.base import BaseSecuritiesExchange`
   - `from app.securities.models import StockOrder` → `from app.exchanges.securities.models import StockOrder`
   - `from app.securities.exceptions import AuthenticationError` → `from app.exchanges.securities.exceptions import AuthenticationError`

**Git 커밋 메시지**:
```
refactor: Import 경로 신규 구조 적용

주요 변경사항:
- services/exchange.py: crypto.base import
- jobs/securities_token_refresh.py: securities.factory import
- binance.py, upbit.py: BaseCryptoExchange 상속
- korea_investment.py: import 경로 업데이트

Breaking Changes: 없음
```

**완료 조건**:
- [ ] 모든 파일 import 오류 없음
- [ ] Python 구문 검증 통과
- [ ] 앱 시작 테스트 통과

---

### 📚 Phase 4: README 문서 작성

**담당**: General Agent

**작업 내용**:
1. `crypto/README.md` 작성
   - 지원 거래소 목록
   - 사용 예시 (Factory, 직접 생성)
   - 새 거래소 추가 방법

2. `securities/README.md` 작성
   - 지원 증권사 목록
   - 사용 예시 (Factory, OAuth 토큰 관리)
   - 새 증권사 추가 방법

3. `exchanges/README.md` 업데이트
   - 전체 구조 설명
   - 통합 사용법 (UnifiedExchangeFactory)
   - 마이그레이션 가이드 (기존 코드 → 신규 코드)

**Git 커밋 메시지**:
```
docs: exchanges 디렉토리 구조 문서화

주요 변경사항:
- crypto/README.md 추가
- securities/README.md 추가
- exchanges/README.md 업데이트 (마이그레이션 가이드)
```

**완료 조건**:
- [ ] 3개 README 파일 작성 완료
- [ ] 사용 예시 코드 검증
- [ ] 마이그레이션 가이드 명확성 확인

---

### ✅ Phase 5: 테스트 및 검증

**담당**: Feature Tester Agent

**작업 내용**:
1. **Import 검증**
   ```bash
   python -c "from app.exchanges.crypto import BinanceExchange; print('✅ Crypto OK')"
   python -c "from app.exchanges.securities import KoreaInvestmentExchange; print('✅ Securities OK')"
   python -c "from app.exchanges import UnifiedExchangeFactory; print('✅ Unified OK')"
   ```

2. **앱 시작 테스트**
   ```bash
   python run.py restart
   # 로그 확인: 에러 없이 시작되는지 확인
   ```

3. **Binance 어댑터 테스트**
   - 잔액 조회 (Testnet)
   - 주문 생성 (Testnet)

4. **Upbit 어댑터 테스트**
   - 잔액 조회
   - 주문 조회

5. **한투 OAuth 토큰 발급 테스트**
   - 토큰 발급 (`authenticate()`)
   - 토큰 캐시 확인 (`SecuritiesToken` 테이블)

6. **UnifiedExchangeFactory 통합 테스트**
   - Crypto 계좌 → BinanceExchange 반환 확인
   - Securities 계좌 → KoreaInvestmentExchange 반환 확인

**Git 커밋 메시지**:
```
test: 통합 구조 검증 완료

검증 내용:
- Import 검증 통과
- 앱 시작 정상
- Binance/Upbit 어댑터 동작 확인
- 한투 OAuth 토큰 발급 정상
- UnifiedExchangeFactory 분기 정상

Breaking Changes: 없음
```

**완료 조건**:
- [ ] 모든 Import 검증 통과
- [ ] 앱 정상 시작
- [ ] 기존 웹훅 기능 정상 동작
- [ ] Crypto/Securities 어댑터 모두 정상

---

## 🔐 하위 호환성 보장

### 기존 코드 (계속 작동)
```python
# Deprecated but works
from app.exchanges import BinanceExchange  # ✅
from app.securities import KoreaInvestmentExchange  # ❌ 작동하지 않음 (삭제됨)
```

### 권장 코드 (신규)
```python
# Recommended
from app.exchanges.crypto import BinanceExchange
from app.exchanges.securities import KoreaInvestmentExchange
from app.exchanges import UnifiedExchangeFactory  # 통합 사용
```

---

## ⚠️ Breaking Changes

**없음** - 완전 하위 호환

**예외**: `from app.securities import ...` 형태는 작동하지 않음 (디렉토리 이동)
→ 해결: `exchanges/__init__.py`에서 재export로 하위 호환 유지

---

## 📊 예상 효과

1. **명확한 타입 분리**: crypto vs securities
2. **확장성 극대화**: 새 거래소 추가 용이
3. **코드 재사용성**: 공통 모듈 통합
4. **유지보수성 향상**: 파일 위치만으로 타입 구분

---

## 📋 체크리스트

### Phase 0: 체크포인트 생성 및 계획 문서화
- [ ] Git 커밋 (현재 상태 저장)
- [x] `docs/task_plan.md` 생성
- [x] Todo 리스트 업데이트

### Phase 1: 디렉토리 생성 및 파일 이동
- [ ] `exchanges/crypto/` 디렉토리 생성
- [ ] `exchanges/securities/` 디렉토리 생성
- [ ] Binance, Upbit → `crypto/` 이동
- [ ] Securities 파일 → `exchanges/securities/` 이동
- [ ] 기존 `securities/` 디렉토리 삭제
- [ ] Git 커밋

### Phase 2: 파일 내용 수정
- [ ] `exchanges/exceptions.py` 생성
- [ ] `crypto/__init__.py` 생성
- [ ] `crypto/base.py` 생성
- [ ] `crypto/factory.py` 수정
- [ ] `securities/__init__.py` 수정
- [ ] `securities/factory.py` 수정
- [ ] `unified_factory.py` 대폭 수정
- [ ] `exchanges/__init__.py` 하위 호환 추가
- [ ] Git 커밋

### Phase 3: Import 경로 수정
- [ ] `services/exchange.py`
- [ ] `jobs/securities_token_refresh.py`
- [ ] `exceptions/exchange_exception.py`
- [ ] `services/symbol_validator.py`
- [ ] `crypto/binance.py`, `crypto/upbit.py`
- [ ] `securities/korea_investment.py`
- [ ] Git 커밋

### Phase 4: README 문서 작성
- [ ] `crypto/README.md` 작성
- [ ] `securities/README.md` 작성
- [ ] `exchanges/README.md` 업데이트
- [ ] Git 커밋

### Phase 5: 테스트 및 검증
- [ ] Import 검증
- [ ] 앱 시작 테스트
- [ ] Binance 어댑터 테스트
- [ ] Upbit 어댑터 테스트
- [ ] 한투 OAuth 테스트
- [ ] UnifiedExchangeFactory 테스트
- [ ] Git 커밋

---

## 🎯 최종 목표

**완료 시점**: 모든 Phase 완료 및 검증 통과

**성공 기준**:
1. 기존 웹훅 기능 정상 동작
2. Crypto/Securities 어댑터 모두 정상 동작
3. UnifiedExchangeFactory 분기 정상
4. 하위 호환성 유지
5. 모든 테스트 통과

---

*Last Updated: 2025-10-07*
*Branch: feature/securities-integration*
*Author: Claude Code*
