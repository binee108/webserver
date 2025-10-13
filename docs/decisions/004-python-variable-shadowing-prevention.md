# Python Variable Shadowing 예방 가이드

**날짜**: 2025-10-13
**상태**: Accepted
**카테고리**: Code Quality, Bug Prevention
**관련 이슈**: 422 Error - Account Name Update Bug

---

## 문제 정의

### 발생한 버그
계좌 이름만 변경 시 `UnboundLocalError: local variable 'Account' referenced before assignment` 에러 발생

### 재현 코드
```python
# security.py
from app.models import User, Account, UserSession, DailyAccountSummary  # Line 22

def update_account(self, account_id: int, user_id: int, update_data: Dict[str, Any]):
    try:
        account = Account.query.filter_by(id=account_id, user_id=user_id).first()  # Line 611 - ❌ UnboundLocalError
        # ...
        if 'public_api' in update_data or 'secret_api' in update_data:
            from app.models import Account  # Line 634 - ❌ 중복 import (조건부 지역 import)
            Account.clear_cache(account.id)
```

### 에러 메시지
```
UnboundLocalError: local variable 'Account' referenced before assignment
```

---

## 근본 원인: Python Variable Shadowing

### 1. Python 스코프 규칙
Python 인터프리터는 **함수 정의 시점**에 함수 내부의 모든 변수 할당을 스캔하여 지역 변수로 분류합니다.

```python
# 잘못된 예시
global_var = 10

def bad_function():
    print(global_var)  # ❌ UnboundLocalError: local variable 'global_var' referenced before assignment
    global_var = 20    # Python은 이 줄을 보고 global_var를 지역 변수로 판단
```

### 2. 조건부 Import의 함정
조건문 안에 `from ... import ...`가 있어도 Python은 함수 정의 시점에 이를 감지하여 지역 변수로 취급합니다.

```python
# 잘못된 패턴 (우리 버그 사례)
from app.models import Account  # 모듈 레벨 import

def update_account(...):
    account = Account.query.filter_by(...)  # ❌ UnboundLocalError

    if some_condition:
        from app.models import Account  # 조건부 지역 import → Account를 지역 변수로 인식
        Account.clear_cache(...)
```

### 3. Python의 LEGB 규칙
Python 변수 스코프 검색 순서:
1. **L (Local)**: 함수 내 지역 변수
2. **E (Enclosing)**: 중첩 함수의 외부 함수 스코프
3. **G (Global)**: 모듈 레벨 전역 변수
4. **B (Built-in)**: 내장 함수

조건부 import는 **Local** 스코프에 변수를 생성하므로, 모듈 레벨 import보다 우선합니다.

---

## 해결 방법

### Phase 1: 중복 Import 제거 (백엔드 수정)

**Before**:
```python
# security.py:634
if 'public_api' in update_data or 'secret_api' in update_data:
    from app.models import Account  # ❌ 중복 import
    Account.clear_cache(account.id)
```

**After**:
```python
# security.py:634
if 'public_api' in update_data or 'secret_api' in update_data:
    Account.clear_cache(account.id)  # ✅ 모듈 레벨 import 사용
```

**수정 이유**:
- Line 22에 이미 `from app.models import Account` 존재
- 중복 import는 불필요하며 Variable Shadowing 원인
- 모듈 레벨 import는 함수 전체에서 안전하게 사용 가능

---

## 예방 지침

### 1. 절대 하지 말아야 할 패턴

#### 패턴 A: 조건부 Import (함수 내부)
```python
# ❌ Bad
def my_function():
    result = SomeClass.method()  # UnboundLocalError 가능

    if condition:
        from module import SomeClass  # 지역 변수로 인식됨
        SomeClass.do_something()
```

#### 패턴 B: 전역 변수와 동일한 이름의 지역 변수
```python
# ❌ Bad
counter = 0

def increment():
    counter = counter + 1  # UnboundLocalError
    return counter
```

#### 패턴 C: 중복 Import
```python
# ❌ Bad
from app.models import User  # 모듈 레벨

def process_user():
    user = User.query.first()
    from app.models import User  # 불필요한 중복
```

---

### 2. 권장 패턴

#### 패턴 1: 모듈 레벨 Import 우선
```python
# ✅ Good
from app.models import Account, User, Trade

def update_account(...):
    account = Account.query.filter_by(...)
    Account.clear_cache(account.id)  # 모듈 레벨 import 사용
```

#### 패턴 2: 필요 시 함수 상단에 Import
```python
# ✅ Good (순환 import 회피 등 특수한 경우)
def process_data():
    from app.models import SpecialClass  # 함수 최상단에 명시

    result = SpecialClass.method()
    return result
```

#### 패턴 3: global/nonlocal 명시
```python
# ✅ Good
counter = 0

def increment():
    global counter  # 명시적으로 전역 변수 선언
    counter = counter + 1
    return counter
```

---

### 3. 코드 리뷰 체크리스트

코드 리뷰 시 다음 항목을 확인하세요:

- [ ] 함수 내부에 조건부 import가 있는가?
- [ ] 모듈 레벨 import와 동일한 이름의 함수 내 import가 있는가?
- [ ] 전역 변수와 동일한 이름의 지역 변수를 사용하는가?
- [ ] import 순서가 명확한가? (표준 라이브러리 → 서드파티 → 로컬)

---

## 디버깅 방법

### 1. PyLint/Flake8 활용
```bash
# PyLint로 Variable Shadowing 감지
pylint web_server/app/services/security.py

# Flake8로 import 중복 감지
flake8 web_server/app/services/security.py
```

### 2. 에러 발생 시 진단
```python
# UnboundLocalError 발생 시:
# 1. 함수 내부에서 해당 변수가 어디서 할당되는지 검색
# 2. 모듈 레벨 import와 중복되는지 확인
# 3. 조건부 import를 제거하거나 함수 상단으로 이동
```

### 3. 로깅 추가
```python
import logging
logger = logging.getLogger(__name__)

def update_account(...):
    logger.debug(f"Account 변수 타입: {type(Account)}")  # 디버깅용
    account = Account.query.filter_by(...)
```

---

## 적용 사례: 422 에러 수정

### 수정 전 (Bug)
```python
# security.py
from app.models import Account  # Line 22

def update_account(self, account_id, user_id, update_data):
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()  # ❌ UnboundLocalError

    if 'public_api' in update_data or 'secret_api' in update_data:
        from app.models import Account  # Line 634 - Variable Shadowing 발생
        Account.clear_cache(account.id)
```

### 수정 후 (Fixed)
```python
# security.py
from app.models import Account  # Line 22

def update_account(self, account_id, user_id, update_data):
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()  # ✅ 정상 작동

    if 'public_api' in update_data or 'secret_api' in update_data:
        Account.clear_cache(account.id)  # ✅ 모듈 레벨 import 사용
```

### 테스트 결과
```python
# Before: UnboundLocalError
update_data = {'name': '테스트계좌'}
result = security_service.update_account(account_id=1, user_id=1, update_data=update_data)
# 결과: UnboundLocalError 발생

# After: 정상 작동
update_data = {'name': '테스트계좌'}
result = security_service.update_account(account_id=1, user_id=1, update_data=update_data)
# 결과: {'success': True, 'account_id': 1, 'name': '테스트계좌', ...}
```

---

## 교훈 및 가이드라인

### 핵심 원칙
1. **모듈 레벨 Import 우선**: 특별한 이유가 없으면 함수 내 import 지양
2. **조건부 Import 금지**: 함수 내 조건문 안에서 import 하지 않음
3. **명시적 스코프 선언**: `global`, `nonlocal` 키워드로 의도를 명확히
4. **코드 리뷰 필수**: Variable Shadowing은 런타임 에러이므로 사전 검토 중요

### 프로젝트 적용 규칙
- **CLAUDE.md 원칙**: "스파게티식 수정 방지 - 근본 원인 해결 우선"
- **최소 변경 원칙**: 1줄 삭제로 버그 수정 (중복 import 제거)
- **문서화 의무**: 이 문서를 참고하여 동일한 실수 방지

---

## 참고 자료
- [Python Scopes and Namespaces (공식 문서)](https://docs.python.org/3/tutorial/classes.html#python-scopes-and-namespaces)
- [PEP 227 - Statically Nested Scopes](https://www.python.org/dev/peps/pep-0227/)
- [Real Python - Variable Scope](https://realpython.com/python-scope-legb-rule/)

---

## 관련 문서
- [Account Management 기능 문서](../features/account-management.md)
- [CLAUDE.md - 스파게티식 수정 방지 지침](/Users/binee/Desktop/quant/webserver/CLAUDE.md)

---

*Last Updated: 2025-10-13*
*Author: documentation-manager*
*Status: ✅ 검증 완료 (사용자 테스트 통과)*
