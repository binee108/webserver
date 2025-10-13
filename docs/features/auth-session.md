# auth-session Documentation

## Overview
사용자 인증, 세션 관리, 권한 검증을 담당하는 핵심 보안 기능. Flask-Login과 커스텀 세션 토큰으로 웹 UI와 API 인증을 제공합니다.

## Key Components

### Core Authentication Logic
- **Files**: `web_server/app/routes/auth.py`, `web_server/app/services/security.py`, `web_server/app/models.py`
- **Tags**: `@FEAT:auth-session @TYPE:core`
- **Purpose**: 사용자 인증, 세션 생성/검증, 비밀번호 관리

### Security Features
- **Files**: `web_server/app/services/security.py`
- **Tags**: `@FEAT:auth-session @TYPE:validation`
- **Purpose**: IP 기반 차단, 로그인 실패 추적, 보안 통계

## Main Features

### 1. User Authentication
- **로그인** (`/auth/login`): 사용자명/비밀번호 검증, Flask-Login 세션 생성
- **로그아웃** (`/auth/logout`): 세션 종료
- **회원가입** (`/auth/register`): 새 사용자 등록 (관리자 승인 필요, is_active=False)
- **프로필 관리** (`/auth/profile`): 이메일, 텔레그램, 비밀번호 변경, 웹훅 토큰 관리

### 2. Password Management
- **해싱**: `werkzeug.security.generate_password_hash()` (기본값: pbkdf2:sha256, Werkzeug 2.3+ 기준 260000 iterations)
- **검증**: `User.check_password()` 메서드 또는 직접 `check_password_hash()` 호출
- **강제 변경**: `must_change_password` 플래그 시 미들웨어가 `/auth/force-change-password`로 리다이렉트
- **최소 길이**: 6자 이상

### 3. Session Management
- **Flask-Login**: 쿠키 기반 (웹 UI용) - `/auth/login` 엔드포인트
- **커스텀 토큰**: `UserSession` 테이블 (내부 서비스용)
  - 생성: `secrets.token_urlsafe(32)` (SecurityService.authenticate_user())
  - 만료: 30일
  - 추적: IP, User-Agent, last_accessed 자동 갱신
  - **주의**: 현재 API 토큰 인증 엔드포인트는 없음 (내부 서비스 간 인증용)
- **검증**: `SecurityService.validate_session(token)`

### 4. Security Protections
- **IP 차단**: 5회 실패 시 1시간 차단
  - 저장 방식: 메모리 기반 딕셔너리 (`SecurityService.failed_login_attempts`)
  - 차단 조건: IP당 5회 연속 실패
  - 차단 기간: 3600초 (1시간)
  - 해제 방식: 차단 시간 만료 후 자동 해제, 로그인 성공 시 즉시 해제
  - 제한사항: 서버 재시작 시 차단 기록 초기화, 영구 저장 없음 (Redis 도입 권장)
- **실패 추적**: IP별 실패 횟수/시간 기록, 성공 시 초기화
- **피드백**: 남은 시도 횟수 표시 (authenticate_user 반환값의 attempts_left)

### 5. Permission Management
- **관리자** (`is_admin=True`): 모든 권한
- **일반 사용자**: dashboard, strategies, accounts, orders, positions 허용; settings, logs, users 차단
- **활성 검증**: `is_active=False` 사용자 로그인 차단
- **검증**: `SecurityService.check_permission(user, action)`

### 6. Webhook Token Management
- **자동 발급**: 회원가입 시 또는 프로필 페이지 GET 요청 시 (토큰이 없는 경우 자동 생성)
- **재발행**: 프로필 페이지에서 "웹훅 토큰 재발행" 버튼으로 가능
- **포맷**: `secrets.token_urlsafe(32)` (44자 Base64 URL-safe)

## Security Architecture

### Execution Flow
```
웹 UI (Flask-Login):
로그인 → login_user(remember=True) → @login_required 보호 → logout_user()

API (커스텀 토큰):
인증 → UserSession 생성 → validate_session(token) → logout_user(token)

IP 차단:
로그인 시도 → IP 확인 → 실패 기록 → 5회 실패 시 차단 → 1시간 후 해제
```

### Password Security
```python
# 저장: User.set_password(raw) → werkzeug.generate_password_hash()
# 검증 (Model): User.check_password(input) → werkzeug.check_password_hash()
# 검증 (Service): SecurityService.authenticate_user() → 직접 check_password_hash() 호출
```

## API Endpoints

### Web UI Routes (`/auth`)
| Route | Method | Purpose | Auth |
|-------|--------|---------|------|
| `/auth/login` | GET, POST | 로그인 | No |
| `/auth/logout` | GET | 로그아웃 | Yes |
| `/auth/register` | GET, POST | 회원가입 | No |
| `/auth/profile` | GET, POST | 프로필 관리 | Yes |
| `/auth/force-change-password` | GET, POST | 강제 비밀번호 변경 | Yes |
| `/auth/change-password` | GET, POST | 일반 비밀번호 변경 | Yes |
| `/auth/profile/test-telegram` | POST | 텔레그램 테스트 | Yes |

### Service Methods (SecurityService)
| Method | Purpose | Returns |
|--------|---------|---------|
| `authenticate_user(username, password)` | 사용자 인증 (IP 차단 확인 포함) | Dict (success, user, session_token, blocked, attempts_left) |
| `validate_session(session_token)` | 세션 검증 및 갱신 (만료 세션 자동 삭제, last_accessed 업데이트) | User or None |
| `logout_user(session_token)` | 커스텀 세션 로그아웃 (UserSession 삭제) | Boolean |
| `check_permission(user, action)` | 권한 확인 | Boolean |
| `get_security_stats()` | 보안 통계 | Dict |

**Note**: SecurityService는 싱글톤 인스턴스로 사용됩니다.
```python
from app.services.security import security_service
```

## Database Models

### User
- `username`, `email`, `password_hash`, `webhook_token`
- `is_active`, `is_admin`, `must_change_password`
- `last_login`, `telegram_id`, `telegram_bot_token`, `created_at`

### UserSession
- `user_id`, `session_token`, `ip_address`, `user_agent`
- `created_at`, `last_accessed`, `expires_at` (생성 + 30일)

## Dependencies
- **None** (다른 기능에 의존하지 않음)
- **Used by**: 모든 인증 필요 기능 (계정, 전략, 주문, 포지션 등)

## Quick Search

```bash
# 모든 인증 관련 코드
grep -r "@FEAT:auth-session" --include="*.py"

# 핵심 인증 로직만
grep -r "@FEAT:auth-session" --include="*.py" | grep "@TYPE:core"

# 보안 검증 코드
grep -r "@FEAT:auth-session" --include="*.py" | grep "@TYPE:validation"

# 라우트 핸들러
grep -r "@FEAT:auth-session" --include="*.py" | grep "@COMP:route"

# 강제 비밀번호 변경
grep -r "must_change_password" --include="*.py"

# 세션 토큰
grep -r "session_token" --include="*.py"
```

## Maintenance Notes

### Security Measures
- **비밀번호**: pbkdf2:sha256, 260000 iterations
- **세션 토큰**: 32바이트 랜덤 (충분히 강력)
- **IP 차단**: 메모리 기반 (Redis/DB 영구화 고려 필요)
- **XSS 방지**: Jinja2 autoescape 활성화
- **CSRF 방지**: Flask-WTF CSRF 토큰

### Known Limitations
- IP 차단 상태 메모리 저장 (재시작 시 초기화)
- 만료 세션 자동 정리 없음 (validate_session()에서 수동 삭제)
- 동시 로그인 제한 없음
- API 토큰 인증 엔드포인트 부재 (SecurityService는 내부 서비스용)

### Future Improvements
- 세션 자동 정리 배치 작업
- Redis 기반 IP 차단 (영구 저장)
- 2FA (이중 인증)
- 로그인 이력 추적 및 알림
- 비정상 로그인 탐지 (위치, 시간대)

## Testing Checklist

### Authentication
- [ ] 정상 로그인 (사용자명 + 비밀번호)
- [ ] 잘못된 비밀번호 → 오류
- [ ] 존재하지 않는 사용자 → 오류
- [ ] 비활성 계정 차단 (`is_active=False`)
- [ ] 로그아웃 → 세션 종료

### Password
- [ ] 비밀번호 변경 (현재 비밀번호 검증)
- [ ] 새 비밀번호 확인 불일치 → 오류
- [ ] 최소 길이 미달 (6자 미만) → 오류
- [ ] 강제 변경 플래그 동작
- [ ] 강제 변경 완료 후 정상 접근

### Session
- [ ] 세션 토큰 생성 및 검증
- [ ] 만료 토큰 → 인증 실패
- [ ] 로그아웃 시 토큰 삭제
- [ ] 세션 자동 갱신 (`last_accessed`)

### Security
- [ ] 5회 실패 → IP 차단
- [ ] 차단된 IP → 차단 메시지
- [ ] 1시간 후 자동 해제
- [ ] 로그인 성공 시 실패 기록 초기화

### Permission
- [ ] 관리자 권한 (`is_admin=True`)
- [ ] 일반 사용자 권한 제한
- [ ] 비인증 사용자 차단 (`@login_required`)

### Registration
- [ ] 신규 사용자 등록
- [ ] 중복 사용자명/이메일 → 오류
- [ ] 웹훅 토큰 자동 발급
- [ ] 초기 상태 `is_active=False`
