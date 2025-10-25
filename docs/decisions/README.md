# Architecture Decision Records (ADRs)

> **목적**: 중요한 아키텍처 및 기술 결정사항을 기록하여 "왜 이렇게 만들었는가"에 대한 답을 제공합니다.

**문제 방지**: Requirements Traceability Loss (Problem #4) - 의사결정 근거를 잃어버리는 것을 방지

---

## 📖 What is an ADR?

Architecture Decision Record (ADR)는 소프트웨어 개발 과정에서 내린 중요한 결정을 문서화하는 방법입니다.

### ADR을 작성해야 하는 경우

✅ **반드시 작성**:
- 아키텍처 패턴 선택 (MVC, Microservices, Event-Driven 등)
- 주요 라이브러리/프레임워크 선택 (Flask vs Django, PostgreSQL vs MongoDB)
- 보안 관련 결정 (인증 방식, 암호화 방법)
- 성능 트레이드오프 (캐싱 전략, 인덱싱 방식)
- 외부 서비스 통합 (거래소 선택, 결제 게이트웨이)

💡 **선택적 작성**:
- 구현 세부사항 (특정 알고리즘 선택)
- 리팩토링 결정 (코드 구조 변경)
- 개발 도구 선택 (IDE, 디버거)

❌ **작성하지 않음**:
- 일상적인 버그 수정
- 코드 스타일 변경
- 사소한 기능 추가

---

## 📝 ADR Template

```markdown
# [번호]. [결정 제목]

**Date**: YYYY-MM-DD
**Status**: [Proposed | Accepted | Deprecated | Superseded]
**Deciders**: [누가 결정했는가]
**Tags**: [관련 태그: architecture, security, performance 등]

## Context and Problem

[어떤 문제를 해결하려고 하는가? 어떤 상황에서 이 결정이 필요한가?]

## Decision Drivers

[결정을 내릴 때 고려한 요소들]
- [요소 1]
- [요소 2]
- [요소 3]

## Considered Options

[고려한 대안들]
- [Option 1]
- [Option 2]
- [Option 3]

## Decision

[최종적으로 선택한 옵션과 이유]

## Consequences

**Positive:**
- [긍정적 결과 1]
- [긍정적 결과 2]

**Negative:**
- [부정적 결과 1]
- [부정적 결과 2]

## Implementation Notes

[구현 시 주의사항, 관련 코드 위치 등]

## Related

- [관련된 다른 ADR]
- [관련 이슈/티켓]
- [관련 문서]

## Code References

[이 결정과 관련된 코드 위치]
- `path/to/file.py`: 설명
```

---

## 📋 ADR Index

### Active ADRs

| # | Title | Date | Status | Tags |
|---|-------|------|--------|------|
| [001](./001-use-flask-over-django.md) | Use Flask Over Django | 2024-01-15 | Accepted | architecture, framework |
| [002](./002-postgresql-as-primary-database.md) | PostgreSQL as Primary Database | 2024-01-20 | Accepted | database, architecture |
| [003](./003-order-queue-priority-system.md) | Order Queue Priority System | 2024-03-10 | Accepted | architecture, trading |

### Deprecated ADRs

| # | Title | Date | Status | Superseded By |
|---|-------|------|--------|---------------|
| - | - | - | - | - |

---

## 🔍 How to Find ADRs

### By Topic

**Architecture & Design**:
- [001 - Use Flask Over Django](./001-use-flask-over-django.md)

**Database**:
- [002 - PostgreSQL as Primary Database](./002-postgresql-as-primary-database.md)

**Trading System**:
- [003 - Order Queue Priority System](./003-order-queue-priority-system.md)

### By Tag

```bash
# Find all security-related ADRs
grep -r "Tags:.*security" docs/decisions/

# Find all architecture ADRs
grep -r "Tags:.*architecture" docs/decisions/

# Find all performance ADRs
grep -r "Tags:.*performance" docs/decisions/
```

---

## 📝 Creating a New ADR

### Step 1: 번호 결정

```bash
# 마지막 ADR 번호 확인
ls docs/decisions/ | grep "^[0-9]" | sort -n | tail -1
# 예: 003-order-queue-priority-system.md

# 새 ADR 번호: 004
```

### Step 2: 파일 생성

```bash
# 파일명 형식: [번호]-[slug].md
touch docs/decisions/004-your-decision-title.md
```

### Step 3: 템플릿 작성

위의 ADR Template을 사용하여 내용 작성

### Step 4: Index 업데이트

이 README.md 파일의 "ADR Index" 섹션에 추가

### Step 5: 코드에 참조 추가

```python
# @FEAT:your-feature @COMP:service @TYPE:core
# @WHY:Decision rationale documented in ADR-004
# @BIZ-REQ:REQ-123
def your_function():
    """
    Your function description.
    
    Decision: See ADR-004 for why we chose this approach.
    """
    pass
```

---

## 🔄 Updating ADRs

### ADR은 불변인가?

**원칙**: ADR은 "작성 당시의 결정"을 기록하므로 수정하지 않습니다.

**예외**:
- 오타 수정
- 명확성을 위한 문구 개선
- 관련 링크 추가

### 결정이 변경되었다면?

1. **기존 ADR 상태 변경**: `Status: Deprecated` 또는 `Status: Superseded`
2. **새 ADR 작성**: 새로운 결정 내용 기록
3. **상호 참조**: 두 ADR에서 서로 링크

**Example**:
```markdown
# 001. Use Flask Over Django

**Status**: Superseded by ADR-010
```

```markdown
# 010. Migrate to FastAPI

**Status**: Accepted
**Supersedes**: ADR-001
```

---

## 💡 Best Practices

### ✅ Good ADR

- **명확한 문제 정의**: "왜" 이 결정이 필요했는지
- **충분한 컨텍스트**: 당시 상황, 제약사항
- **여러 대안 고려**: 선택하지 않은 옵션과 이유
- **결과 예측**: 긍정적/부정적 영향
- **구현 가이드**: 실제 코드와 연결

### ❌ Bad ADR

- **결론만 있음**: "우리는 X를 선택했다" (왜?)
- **대안 없음**: 다른 선택지는 고려했는가?
- **추상적**: 구체적인 상황 설명 없음
- **코드 미연결**: 실제 구현과 연결 안 됨

---

## 🔗 Integration with Code

### ADR과 코드 연결하기

**1. 코드에 ADR 참조**:
```python
# @WHY:Use Repository Pattern per ADR-005
# @BIZ-REQ:DATA-101
class UserRepository:
    """
    User data access layer.
    
    Decision: Repository Pattern chosen per ADR-005
    Reason: Decouples business logic from data access
    """
    pass
```

**2. ADR에 코드 위치 명시**:
```markdown
## Code References

- `web_server/app/repositories/user_repository.py`: UserRepository implementation
- `web_server/app/services/user_service.py`: Uses Repository pattern
```

**3. 검색 가능하게**:
```bash
# ADR 번호로 관련 코드 찾기
grep -r "ADR-005" --include="*.py"
```

---

## 📊 ADR Statistics

```bash
# 총 ADR 개수
ls docs/decisions/*.md | wc -l

# 상태별 개수
grep -r "^**Status**: Accepted" docs/decisions/ | wc -l
grep -r "^**Status**: Deprecated" docs/decisions/ | wc -l

# 태그별 분류
grep -r "^**Tags**:" docs/decisions/ | sed 's/.*Tags**: //' | tr ',' '\n' | sort | uniq -c
```

---

## 🎯 Success Criteria

좋은 ADR 관리의 지표:

1. **발견 가능**: 주요 결정사항을 10초 내에 찾을 수 있음
2. **이해 가능**: 6개월 후에 읽어도 결정 배경이 이해됨
3. **추적 가능**: 코드에서 ADR로, ADR에서 코드로 양방향 추적
4. **최신 유지**: Deprecated된 ADR은 명확히 표시됨

---

*Last Updated: 2025-10-10*
*Version: 1.0.0*

