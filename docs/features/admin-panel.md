# Admin Panel (관리자 패널)

## 1. 개요 (Purpose)

시스템 관리자를 위한 통합 관리 인터페이스. 사용자 승인/삭제, 시스템 모니터링, 텔레그램 설정, 주문 추적 시스템 관리, 대기열 재정렬 등 핵심 운영 기능 제공.

**존재 이유**: 관리자가 코드 수정 없이 시스템 전반을 제어하고 모니터링하기 위함.

---

## 2. 실행 플로우 (Execution Flow)

```
사용자 로그인
    ↓
@admin_required (관리자 권한 검증)
    ↓
관리 기능 접근 (페이지/조회 API)
    ↓
민감 작업 시도 → @admin_verification_required (비밀번호 재확인)
    ↓                   ↓ (검증 실패)
작업 실행          세션 검증 요청 (POST /admin/verify-session)
    ↓                   ↓ (검증 성공, 10분 유효)
DB 트랜잭션 ←──────────┘
    ↓
JSON 응답 or 페이지 리다이렉트
```

**핵심 단계**:
1. **권한 검증**: `@admin_required` - 관리자 권한 보유 확인
2. **세션 검증**: `@admin_verification_required` - 민감 작업은 비밀번호 재확인 (10분 유효)
3. **자기 보호**: 관리자가 자신을 삭제/비활성화/권한 제거 불가
4. **트랜잭션 처리**: 모든 DB 수정은 예외 처리 및 롤백

---

## 3. 데이터 플로우 (Data Flow)

**Input**: HTTP 요청 (GET/POST/DELETE) + 세션 쿠키 + CSRF 토큰
**Process**:
- 권한 검증 데코레이터 (`@admin_required`, `@admin_verification_required`)
- 입력 검증 (사용자명/이메일 중복, 비밀번호 길이, 텔레그램 설정 완전성)
- DB 조작 (User, Account, Strategy, OpenOrder, PendingOrder 등)
- 외부 API 호출 (텔레그램, 거래소)

**Output**: JSON 응답 (`{"success": true/false, "message": "..."}`) 또는 HTML 페이지 렌더링

**주요 의존성**:
- `@FEAT:auth-session` - 사용자 인증 및 세션 관리
- `@FEAT:telegram-notification` - 텔레그램 설정 및 알림
- `@FEAT:order-tracking` - 주문 추적 시스템 관리
- `@FEAT:order-queue` - 대기열 재정렬

---

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `routes/admin.py` | 관리자 페이지 및 API | `@FEAT:admin-panel @COMP:route @TYPE:core` | `admin_required()`, `admin_verification_required()` |
| `templates/admin/*.html` | 관리자 UI (6개 템플릿) | `@FEAT:admin-panel @COMP:template @TYPE:core` | users.html, system.html, edit_user.html, change_admin_password.html, change_user_password.html, user_telegram_settings.html ⚠️ **order_tracking.html 미구현** |
| `models.py` | User, SystemSetting 모델 | `@FEAT:admin-panel @COMP:model @TYPE:core` | User.is_admin, SystemSetting |

**검색 예시**:
```bash
# 모든 관리자 패널 코드
grep -r "@FEAT:admin-panel" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:admin-panel" --include="*.py" | grep "@TYPE:core"

# 민감 작업 찾기
grep -rn "@admin_verification_required" web_server/app/routes/admin.py

# auth-session 통합 지점
grep -r "@FEAT:admin-panel" --include="*.py" | grep "@FEAT:auth-session"
```

---

## 5. 주요 기능 세부사항

### 5.1 권한 시스템

**`@admin_required`**: 모든 관리자 페이지에 적용. 로그인 + `is_admin=True` 검증.
**`@admin_verification_required`**: 민감 작업에 적용. 10분 내 비밀번호 재확인 필요.

**민감 작업 목록**: 사용자 삭제/승인/거부, 비밀번호 초기화, 권한 토글, 텔레그램 테스트, Precision 캐시 조작, 주문 동기화, 성과 계산, 세션 정리

```bash
# 세션 검증 (10분 유효)
POST /admin/verify-session
{"password": "admin_password"}
```

---

### 5.2 사용자 관리

| 기능 | 엔드포인트 | 권한 | 설명 |
|------|------------|------|------|
| 목록 조회 | `GET /admin/users` | `@admin_required` | 전체/대기 중 사용자 + 통계 |
| 정보 수정 | `POST /admin/users/<id>/edit` | `@admin_required` | 사용자명/이메일/활성화/관리자 권한 (자신 제외) |
| 비밀번호 변경 | `POST /admin/users/<id>/change-password` | `@admin_required` | 다른 사용자 비밀번호 변경 (최소 6자) |
| 비밀번호 초기화 | `POST /admin/users/<id>/reset-password` | `@admin_verification_required` | 임시 비밀번호 8자 생성, 다음 로그인 시 변경 강제 |
| 승인 | `POST /admin/users/<id>/approve` | `@admin_verification_required` | `is_active=True` 설정 |
| 거부 | `POST /admin/users/<id>/reject` | `@admin_verification_required` | 계정 삭제 (영구) |
| 삭제 | `DELETE /admin/users/<id>` | `@admin_verification_required` | 승인된 사용자 삭제 (자신 제외) |
| 활성화 토글 | `POST /admin/users/<id>/toggle-active` | `@admin_verification_required` | 활성화/비활성화 (자신 제외) |
| 관리자 권한 토글 | `POST /admin/users/<id>/toggle-admin` | `@admin_verification_required` | 관리자 권한 부여/제거 (자신 제외) |

**자기 보호 규칙**: 관리자는 자신을 삭제/비활성화/권한 제거 불가.

---

### 5.3 시스템 모니터링

**페이지**: `GET /admin/system`
**표시 정보**:
- 스케줄러 상태 (실행 여부, 등록된 작업 목록)
- 시스템 통계 (총 사용자/계좌/전략, 활성 사용자/계좌/전략)
- Precision 캐시 통계 (캐시된 거래소 수, 총 심볼 수, 마지막 업데이트)

**Precision 캐시 관리**:
- `POST /admin/system/precision-cache/clear` - 전체 또는 특정 거래소 캐시 정리
- `POST /admin/system/precision-cache/warmup` - 백그라운드 캐시 재로딩
- `GET /admin/system/precision-cache/stats` - 실시간 캐시 상태 JSON

---

### 5.4 텔레그램 설정

**사용자별 설정**: `POST /admin/users/<id>/telegram-settings`
- `telegram_id` + `telegram_bot_token` 둘 다 입력 or 둘 다 비워야 함
- `POST /admin/users/<id>/test-telegram` - 사용자 설정으로 테스트 메시지 전송
- `POST /admin/users/<id>/send-telegram-notification` - 관리자가 수동 알림 전송

**전역 설정**: `GET/POST /admin/system/telegram-settings`
- SystemSetting 테이블에 저장 (`bot_token`, `chat_id`)
- `POST /admin/system/test-global-telegram` - 전역 설정 테스트

---

### 5.5 주문 추적 시스템 관리

**페이지**: `GET /admin/system/order-tracking` ⚠️ **UI 미구현** (템플릿 파일 없음, 엔드포인트만 존재)
**표시 정보 (계획)**: 세션 통계, 최근 추적 세션 (10개), 최근 체결 내역 (20개), 오늘의 성과 요약

**API** (정상 작동):
- `POST /admin/system/order-tracking/sync-orders` - 거래소와 DB 간 미체결 주문 동기화 (`account_id` 필수)
- `POST /admin/system/order-tracking/calculate-performance` - 특정 전략/날짜 또는 최근 N일 성과 계산
- `POST /admin/system/order-tracking/cleanup-sessions` - 오래된 비활성 세션 정리 (기본 5분 타임아웃)
- `GET /admin/system/order-tracking/stats` - 세션/체결/로그 통계 JSON

---

### 5.6 대기열 시스템 관리

**대기열 현황**: `GET /admin/api/queue-status`
- 계좌별 심볼별 활성/대기 주문 수, 제한값
- 전체 활성/대기 주문 수

**수동 재정렬**: `POST /admin/api/queue-rebalance`
- 특정 계좌/심볼의 대기열 재정렬 (`account_id`, `symbol` 필수)
- 응답: 취소/실행 주문 수, 재정렬 메시지

**메트릭**: `GET /admin/api/metrics`
- 재정렬 메트릭 (총 횟수, 취소/실행 수, 평균 소요 시간)
- 대기열 통계 (총 대기 주문, 심볼별 분포)
- WebSocket 통계 (연결 수, 구독 수, 고유 심볼 수)

---

## 6. API 엔드포인트 요약

### 페이지 렌더링 (GET, @admin_required)
- `/admin/` - 대시보드 (users로 리다이렉트)
- `/admin/users` - 사용자 관리
- `/admin/users/<id>/edit` - 사용자 수정
- `/admin/users/<id>/change-password` - 비밀번호 변경
- `/admin/change-password` - 관리자 자신의 비밀번호 변경
- `/admin/users/<id>/telegram-settings` - 텔레그램 설정
- `/admin/system` - 시스템 모니터링
- `/admin/system/order-tracking` ⚠️ **UI 미구현** - 주문 추적 관리 (템플릿 없음, API만 작동)

### 세션 검증 (POST, @admin_required)
- `/admin/verify-session` - 비밀번호 재확인 (10분 유효)

### 사용자 관리 API (POST/DELETE)
- **기본 권한** (`@admin_required`): 정보 수정, 비밀번호 변경
- **민감 작업** (`@admin_verification_required`): 승인, 거부, 삭제, 비밀번호 초기화, 권한 토글

### 텔레그램 API (GET/POST)
- **조회/설정** (`@admin_required`): 전역/사용자별 설정 조회 및 업데이트
- **테스트/알림** (`@admin_verification_required`): 연결 테스트, 수동 알림 전송

### 시스템 관리 API (GET/POST)
- **조회** (`@admin_required`): Precision 캐시 통계
- **조작** (`@admin_verification_required`): 캐시 정리, 웜업

### 주문 추적 API (GET/POST)
- **조회** (`@admin_required`): 추적 시스템 통계
- **조작** (`@admin_verification_required`): 주문 동기화, 성과 계산, 세션 정리

### 대기열 API (GET/POST, @admin_required)
- `GET /admin/api/queue-status` - 대기열 현황
- `POST /admin/api/queue-rebalance` - 수동 재정렬
- `GET /admin/api/metrics` - 메트릭 조회

---

## 7. 설계 결정 히스토리

### 이중 권한 검증 (`@admin_verification_required`)
**이유**: 사용자 삭제, 비밀번호 초기화 등 위험한 작업은 관리자 권한만으로 불충분. 실수로 인한 데이터 손실 방지 위해 10분 내 비밀번호 재확인 필요.

### 자기 보호 로직
**이유**: 관리자가 자신을 삭제/비활성화하면 시스템 복구 불가능. 마지막 관리자 보호 위해 자기 자신에 대한 위험 작업 차단.

### 텔레그램 설정 완전성 검증
**이유**: `telegram_id`만 있고 `telegram_bot_token`이 없으면 알림 전송 실패. 부분 설정으로 인한 혼란 방지 위해 둘 다 입력 or 둘 다 비워야 함.

---

## 8. 보안 고려사항

1. **이중 권한 검증**: 민감 작업은 `@admin_required` + `@admin_verification_required`
2. **자기 보호**: 관리자는 자신을 삭제/비활성화/권한 제거 불가
3. **입력 검증**: 중복 사용자명/이메일, 비밀번호 최소 6자, 텔레그램 설정 완전성, 계좌/전략 ID 존재 여부
4. **트랜잭션 안전성**: 모든 DB 수정에 예외 처리 및 롤백
5. **CSRF 보호**: Flask-WTF CSRF 토큰 검증 (POST 요청)

---

## 9. 유지보수 가이드

### 주의사항
- 민감 작업 추가 시 반드시 `@admin_verification_required` 데코레이터 적용
- 자기 보호 로직은 모든 사용자 삭제/비활성화/권한 변경 API에 필수
- 텔레그램 설정은 완전성 검증 (둘 다 입력 or 둘 다 비움) 유지
- DB 수정 작업은 항상 try-except + rollback

### 확장 포인트
- 새로운 시스템 통계 추가: `/admin/system` 페이지에 데이터 수집 로직 추가
- 새로운 관리 기능: `routes/admin.py`에 엔드포인트 추가 + `@admin_required` 데코레이터 적용
- 민감 작업 추가: `@admin_verification_required` 데코레이터 + 세션 검증 UI 연동

### 트러블슈팅
- **"관리자 권한이 필요합니다"**: 로그인 상태 확인, `User.is_admin=True` 확인, 필요시 DB에서 직접 권한 부여
- **"관리자 확인이 필요합니다"**: `POST /admin/verify-session`으로 세션 검증 (10분 유효)
- **사용자 삭제/비활성화 실패**: 자기 자신 보호 로직 - 다른 관리자 계정으로 작업
- **텔레그램 테스트 실패**: Bot Token/Chat ID 재확인, 봇과 `/start` 대화 시작 여부 확인, 로그 확인

---

## 10. 관련 문서

- **인증 시스템**: [auth-session.md](./auth-session.md)
- **텔레그램 알림**: [telegram-notification.md](./telegram-notification.md)
- **주문 추적**: [order-tracking.md](./order-tracking.md)
- **주문 큐**: [order-queue-system.md](./order-queue-system.md)
- **아키텍처**: [../ARCHITECTURE.md](../ARCHITECTURE.md)

---

*Last Updated: 2025-10-11*
*Endpoints: 30+ APIs*
*Security: Double verification for sensitive actions*
