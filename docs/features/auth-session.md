# auth-session Documentation

## Overview
사용자 인증, 세션 관리, 권한 검증을 담당하는 핵심 보안 기능. Flask-Login과 커스텀 세션 토큰으로 웹 UI와 API 인증을 제공합니다.

## Key Components

### Core Authentication Routes
- **File**: `web_server/app/routes/auth.py`
- **Tag**: `@FEAT:auth-session @COMP:route @TYPE:core`
- **Functions**:
  - `login()` (line 13): Flask-Login 기반 웹 UI 로그인
  - `register()` (line 159): 회원가입 (관리자 승인 필요)
  - `profile()` (line 223): 프로필 및 웹훅 토큰 관리
  - `force_change_password()` (line 64): 비밀번호 강제 변경
  - `change_password()` (line 112): 일반 비밀번호 변경
  - `test_telegram()` (line 315): 텔레그램 연결 테스트
  - `logout()` (line 364): 로그아웃

### Admin Authentication
- **File**: `web_server/app/routes/admin.py`
- **Tag**: `@FEAT:auth-session @FEAT:admin-panel @COMP:route @TYPE:validation`
- **Functions**:
  - `admin_required()` (line 28): 관리자 권한 검증 데코레이터
  - `admin_verification_required()` (line 60): 추가 비밀번호 검증 데코레이터
  - `verify_admin_session()` (line 87): 관리자 세션 재검증
  - `_is_admin_session_verified()` (line 44): 검증 상태 확인

### Database Models
- **File**: `web_server/app/models.py`
- **Tags**: `@FEAT:auth-session @COMP:model @TYPE:core`
- **Models**:
  - `User`: 사용자 정보 (username, password_hash, webhook_token, is_admin, is_active, must_change_password, etc.)
  - `UserSession`: 커스텀 토큰 기반 세션 (미사용 상태 - 내부 서비스용 예약)

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
- **생성 시점**:
  1. 회원가입 완료 시 (auth.py:207): `secrets.token_urlsafe(32)` 자동 발급
  2. 프로필 GET 요청 시 (auth.py:307-309): 토큰이 없으면 자동 생성
- **재발행**: 프로필 페이지 POST에서 action='regenerate_webhook_token' (auth.py:237-246)
- **포맷**: Base64 URL-safe, 32바이트 (약 43자)
- **사용처**: 웹훅 인증 토큰 (현재 구현 예정)

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
| Route | Method | Purpose | Auth | Implementation |
|-------|--------|---------|------|-----------------|
| `/auth/login` | GET, POST | 로그인 | No | `auth.py:login()` |
| `/auth/logout` | GET | 로그아웃 | Yes | `auth.py:logout()` |
| `/auth/register` | GET, POST | 회원가입 | No | `auth.py:register()` |
| `/auth/profile` | GET, POST | 프로필 관리 | Yes | `auth.py:profile()` |
| `/auth/force-change-password` | GET, POST | 강제 비밀번호 변경 | Yes | `auth.py:force_change_password()` |
| `/auth/change-password` | GET, POST | 일반 비밀번호 변경 | Yes | `auth.py:change_password()` |
| `/auth/profile/test-telegram` | POST | 텔레그램 테스트 | Yes | `auth.py:test_telegram()` |

### Admin Routes (`/admin`)
| Route | Method | Purpose | Auth | Implementation |
|-------|--------|---------|------|-----------------|
| `/admin/verify-session` | POST | 관리자 비밀번호 재검증 | Yes | `admin.py:verify_admin_session()` |

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

## Implementation Details

### Login Flow (auth.py:13-61)
1. 기존 인증 사용자 → 대시보드 리다이렉트
2. 비밀번호 변경 필수 플래그 확인 → force_change_password 리다이렉트
3. 사용자명/비밀번호 검증
4. 비활성 계정 확인 (is_active=False)
5. last_login 시간 업데이트
6. Flask-Login 세션 생성 (remember=True)
7. next_page 파라미터로 원래 페이지 리다이렉트

### Register Flow (auth.py:159-220)
1. 입력 검증: username, email, password, confirm_password
2. 비밀번호 확인 및 최소 길이 검증 (6자)
3. 중복 확인: username, email
4. User 객체 생성 (is_active=False - 관리자 승인 필요)
5. 웹훅 토큰 자동 발급: `secrets.token_urlsafe(32)`
6. DB 커밋 후 로그인 페이지로 리다이렉트

### Profile Management (auth.py:223-312)
1. 강제 비밀번호 변경 플래그 확인
2. 이메일 중복 확인 및 업데이트
3. 텔레그램 설정 검증: 둘 다 있거나 둘 다 없어야 함
4. 비밀번호 변경 (선택사항, 모든 필드 필수 입력)
5. 웹훅 토큰 자동 발급: GET 요청 시 토큰 없으면 생성
6. 텔레그램 테스트: JSON 요청에서 임시 값 또는 저장된 값 사용

### Password Change Flow
**일반 비밀번호 변경** (auth.py:112-156):
- 현재 비밀번호 검증 필수
- 새 비밀번호 확인 및 최소 길이 검증 (6자)
- 강제 변경 플래그 확인

**강제 비밀번호 변경** (auth.py:64-109):
- must_change_password 플래그 설정 시에만 접근 가능
- 완료 후 플래그 해제
- 이후 정상 기능 접근 허용

### Admin Verification (admin.py:87-100+)
- 관리자 비밀번호 재검증 엔드포인트
- 검증 유효 시간: 10분 (session['admin_verified_until'])
- 민감한 작업(@admin_verification_required)에 선수 조건

### Admin Required Decorator (admin.py:28-41)
- 로그인 여부 + is_admin 권한 확인
- 실패 시 대시보드로 리다이렉트

### Test Telegram Function (auth.py:315-361)
- 사용자별 봇 토큰 지원
- JSON 요청에서 임시 값 또는 저장된 값 사용
- telegram_service.test_user_connection() 호출

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
