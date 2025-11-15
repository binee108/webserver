# 텔레그램 알림 (Telegram Notification)

## 1. 개요 (Purpose)

거래 체결, 시스템 오류, 중요 이벤트를 텔레그램으로 실시간 알림하는 시스템입니다.

**핵심 특징**:
- 사용자별 개인 텔레그램 봇 지원 (우선순위 높음)
- 시스템 전역 텔레그램 봇 폴백
- 주문 체결, 오류, 시스템 상태 등 다양한 알림 타입
- 비동기 전송으로 주 서비스 성능 영향 최소화

---

## 2. 실행 플로우 (Execution Flow)

```
이벤트 발생 (주문 체결, 오류, 시스템 상태)
    ↓
TelegramService 메서드 호출
    ↓
봇 및 Chat ID 결정 (우선순위 기반)
  1순위: 사용자별 봇 (user.telegram_bot_token + user.telegram_id)
  2순위: 전역 봇 + 사용자 Chat ID
  3순위: 전역 봇 + 전역 Chat ID
    ↓
메시지 포맷팅 (HTML, 이모지)
    ↓
Telegram Bot API 호출 (비동기)
    ↓
사용자 텔레그램으로 알림 전송
```

**설계 결정**: 동기 Flask 환경에서 비동기 Telegram API 사용을 위해 새 이벤트 루프 생성 (`asyncio.new_event_loop()`). 텔레그램 알림 실패는 주요 서비스 중단시키지 않음 (로그 기록 후 계속 진행).

---

## 3. 데이터 플로우 (Data Flow)

**Input** → **Process** → **Output**

```
알림 트리거
  • 주문 체결/실패
  • 시스템 오류
  • 웹훅 처리 오류
  • 거래소 연결 오류
  • 일일 요약 스케줄
    ↓
TelegramService
  • 봇/Chat ID 결정 (우선순위)
  • 메시지 포맷팅 (HTML)
  • 비동기 전송
    ↓
사용자 텔레그램 앱
  • HTML 마크다운
  • 이모지
  • 타임스탬프
```

**주요 의존성**:
- `python-telegram-bot`: Telegram Bot API 클라이언트
- `SystemSetting` 테이블: 전역 봇 설정 (Bot Token, Chat ID)
- `User` 테이블: 사용자별 봇 설정 (telegram_bot_token, telegram_id)

---

## 4. 주요 컴포넌트 (Components)

### 4.1 TelegramService (`services/telegram.py`)

| 영역 | 메서드 | 설명 | 태그 |
|------|--------|------|------|
| **설정 초기화** | `__init__()` | 전역 설정 초기화 (DB 우선, 환경변수 폴백) | `@TYPE:config` |
| | `_initialize_global_settings()` | DB 및 환경변수에서 설정 로드 | `@TYPE:config` |
| **설정 관리** | `get_global_settings()` | 전역 봇 설정 조회 | `@TYPE:helper` |
| | `update_global_settings()` | 전역 봇 설정 업데이트 및 재초기화 | `@TYPE:helper` |
| **연결 테스트** | `test_global_settings()` | 저장된 전역 설정 연결 테스트 | `@TYPE:validation` |
| | `test_with_params()` | 입력된 파라미터로 연결 테스트 (설정 저장 전) | `@TYPE:validation` |
| | `test_user_connection()` | 사용자별 봇 연결 테스트 | `@TYPE:validation` |
| | `test_connection()` | 전역 봇 연결 테스트 (유틸리티) | `@TYPE:validation` |
| **메시지 전송** | `send_message()` | 전역 채팅에 동기 메시지 전송 | `@TYPE:core` |
| | `send_message_async()` | 전역 채팅에 비동기 메시지 전송 | `@TYPE:core` |
| | `send_message_to_user()` | 특정 사용자에게 메시지 전송 (사용자별 봇 지원) | `@TYPE:core` |
| | `_send_message_to_user_async()` | 특정 사용자에게 비동기 메시지 전송 | `@TYPE:core` |
| **알림 메서드** | `send_order_adjustment_notification()` | 주문 수량 자동 조정 알림 | `@TYPE:core` |
| | `send_error_alert()` | 시스템 오류 알림 | `@TYPE:core` |
| | `send_webhook_error()` | 웹훅 처리 오류 알림 | `@TYPE:core` |
| | `send_exchange_error()` | 거래소 연결 오류 알림 | `@TYPE:core` |
| | `send_trading_error()` | 거래 실행 오류 알림 | `@TYPE:core` |
| | `send_order_failure_alert()` | 주문 실패 알림 (복구 불가능) | `@TYPE:core @DEPS:order-queue` |
| | `send_system_status()` | 시스템 시작/종료 상태 알림 | `@TYPE:core` |
| | `send_daily_summary()` | 일일 트레이딩 요약 보고서 전송 | `@TYPE:core` |
| **사용자 기능** | `send_user_notification()` | 사용자에게 커스텀 알림 전송 | `@TYPE:helper` |
| **유틸리티** | `get_user_bot()` | 사용자별 봇 인스턴스 생성 | `@TYPE:helper` |
| | `get_effective_bot_and_chat()` | 우선순위에 따라 효과적인 봇과 Chat ID 선택 | `@TYPE:helper` |
| | `is_enabled()` | 전역 텔레그램 알림 활성화 여부 확인 | `@TYPE:helper` |
| | `get_stats()` | 서비스 통계 (설정 상태) | `@TYPE:helper` |
| | `is_available()` | 서비스 사용 가능 여부 | `@TYPE:helper` |

**우선순위 기반 봇 선택 로직** (`services/telegram.py:222-250`):
```python
# @FEAT:telegram-notification @COMP:service @TYPE:helper
def get_effective_bot_and_chat(self, user_telegram_bot_token=None,
                              user_telegram_id=None) -> tuple[Optional[Bot], Optional[str]]:
    """사용자별 또는 전역 봇과 채팅 ID 반환 (우선순위: 사용자 > 전역)"""
    # 1순위: 사용자별 봇 토큰이 있고 Chat ID가 있으면 사용자 봇 사용
    if user_telegram_bot_token and user_telegram_id:
        user_bot = self.get_user_bot(user_telegram_bot_token)
        if user_bot:
            return user_bot, user_telegram_id
        else:
            logger.warning("사용자별 봇 생성 실패, 전역 봇으로 폴백")

    # 2순위: 사용자별 Chat ID + 전역 봇 사용
    if user_telegram_id and self.bot:
        return self.bot, user_telegram_id

    # 3순위: 전역 봇 + 전역 Chat ID 사용
    elif self.bot and self.chat_id:
        return self.bot, self.chat_id

    # 대체 방안 없음
    else:
        logger.warning("사용 가능한 봇과 채팅 ID가 없습니다")
        return None, None
```

**특징**:
- 빈 문자열을 자동으로 None으로 정규화 (빈 값 필터링)
- 사용자별 봇 생성 실패 시 자동으로 전역 봇으로 폴백
- 명확한 우선순위 순서: 사용자 봇 > 전역 봇 + 사용자 Chat ID > 전역 봇 + 전역 Chat ID

### 4.2 알림 발송 위치 (Integration Points)

| 위치 | 파일 | 알림 메서드 | 알림 타입 | 태그 |
|------|------|-------------|-----------|------|
| 웹훅 처리 | `routes/webhook.py` | `send_webhook_error()` | 웹훅 오류 | `@FEAT:telegram-notification @TYPE:integration` |
| 주문 큐 | `trading/order_queue_manager.py` | `send_order_failure_alert()` | 주문 실패 | `@FEAT:telegram-notification @TYPE:integration` |
| 수량 조정 | `services/position_sizing.py` | `send_order_adjustment_notification()` | 수량 조정 | `@FEAT:telegram-notification @TYPE:integration` |
| 백그라운드 | `background/queue_rebalancer.py` | `send_error_alert()` | 시스템 오류 | `@FEAT:telegram-notification @TYPE:integration` |
| WebSocket | `exchanges/binance_websocket.py`<br>`exchanges/bybit_websocket.py` | `send_error_alert()` | WebSocket 오류 | `@FEAT:telegram-notification @TYPE:integration` |
| 시스템 시작 | `app/__init__.py` | `send_system_status('startup')` | 시스템 상태 | `@FEAT:telegram-notification @TYPE:integration` |

**참고**:
- 모든 메서드는 구현 완료되었으며 실제 사용 중입니다.

### 4.3 알림 타입 및 메시지 포맷

| 알림 타입 | 메서드 | 설명 | 헤더 이모지 | 사용 여부 |
|-----------|--------|------|-----------|-----------|
| 주문 수량 조정 | `send_order_adjustment_notification()` | 최소 요구사항 미달로 자동 조정된 주문 알림 (사용자별 봇) | 📊 | ✅ 활성 |
| 시스템 오류 | `send_error_alert()` | WebSocket 오류, 백그라운드 작업 실패 등 일반 오류 | 🚨 | ✅ 활성 |
| 웹훅 오류 | `send_webhook_error()` | 웹훅 처리 중 발생한 오류 | 🚨 | ✅ 활성 |
| 거래 실행 오류 | `send_trading_error()` | 거래 실행 중 발생한 오류 | 🚨 | ✅ 활성 |
| 거래소 연결 오류 | `send_exchange_error()` | 거래소 API 호출 실패 | ⚠️ | ✅ 활성 |
| 주문 실패 | `send_order_failure_alert()` | 복구 불가능한 오류 (잔고 부족, 심볼 오류 등) | ⚠️ | ✅ 활성 |
| 시스템 상태 | `send_system_status()` | 시스템 시작(`startup`), 종료(`shutdown`), 기타 상태 | ✅/🔴/ℹ️ | ✅ 활성 |
| 일일 요약 | `send_daily_summary()` | 일일 트레이딩 성과, 통계, 손익 요약 보고서 | 📊 | ✅ 활성 |
| 사용자 알림 | `send_user_notification()` | 커스텀 사용자 알림 (제목, 메시지, 컨텍스트) | 📢 | ✅ 활성 |

---

## 5. 설정 (Configuration)

### 5.1 전역 봇 (SystemSetting 테이블)
- **Bot Token**: `TELEGRAM_BOT_TOKEN` (DB 우선, 환경변수 폴백)
- **Chat ID**: `TELEGRAM_CHAT_ID` (DB 우선, 환경변수 폴백)
- **관리**: `/admin/system/telegram-settings` (웹 UI)
- **용도**: 시스템 전체 알림

### 5.2 사용자별 봇 (User 테이블)
- **Bot Token**: `user.telegram_bot_token` (TEXT, 평문 저장, nullable)
- **Chat ID**: `user.telegram_id` (String(100), nullable)
- **관리**: `/admin/users/<user_id>/telegram-settings` (관리자용)
- **용도**: 사용자 개인 알림
- **참고**: 봇 토큰과 Chat ID는 둘 다 설정하거나 둘 다 비워야 함

### 5.3 설정 방법 및 API

#### 텔레그램 봇 및 Chat ID 준비
1. **텔레그램 봇 생성**:
   - Telegram에서 `@BotFather` 검색 → `/newbot` 명령어
   - Bot Token 복사 (형식: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

2. **Chat ID 확인**:
   - `@userinfobot`에게 메시지 전송하여 Chat ID 확인 (양수, 예: `123456789`)

#### 웹 UI 설정 (관리자용)
- **전역 봇 설정**: `/admin/system/telegram-settings` (GET/POST)
  - 전역 Bot Token 및 Chat ID 저장 → DB 우선, 환경변수 폴백
  - `test-global-telegram` 엔드포인트로 연결 테스트 가능

- **사용자별 봇 설정**: `/admin/users/<user_id>/telegram-settings` (GET/POST)
  - 사용자별 Bot Token 및 Chat ID 저장
  - `test-telegram` 엔드포인트로 연결 테스트 가능

- **권한**: `@admin_verification_required` 데코레이터로 보호됨 (관리자 비밀번호 재확인 필요)

---

## 6. 메시지 포맷팅

### HTML 마크다운
```html
<b>볼드</b>
<i>이탤릭</i>
<code>코드</code>
<pre>코드 블록</pre>
```

### 이모지
- **상태**: ✅ 성공, ⚠️ 경고, ❌ 실패, 🔴 심각, 🟢 정상
- **카테고리**: 🎯 주문, 📊 통계, 💰 손익, 📈 상승, 📉 하락, ⬆️ 증가, ⬇️ 감소, 🏦 계좌, 🔄 처리 중, ⏰ 시간, 🚨 긴급

---

## 7. 보안 고려사항

### Bot Token 저장 및 보호
| 구분 | 저장 위치 | 형식 | 보호 방법 |
|------|---------|------|---------|
| 전역 봇 | `SystemSetting` DB 테이블 | 평문 (TEXT) | DB 접근 제한, 관리자 비밀번호 재확인 |
| 사용자 봇 | `User.telegram_bot_token` DB 필드 | 평문 (TEXT) | DB 접근 제한, 소유자만 수정 가능 |
| 환경변수 | `.env` 파일 (폴백) | 평문 | `.gitignore` 포함, 서버에서만 관리 |

### 권고사항
- Bot Token은 절대 하드코딩하지 마세요
- `.env` 파일을 `.gitignore`에 반드시 포함시키세요
- 관리자만 텔레그램 설정을 수정할 수 있도록 제한됩니다
- 향후 암호화 저장 (encryption at rest) 검토 필요

### 에러 처리 원칙
텔레그램 알림 실패는 **non-blocking** (서비스 중단 없음):

```python
# @FEAT:telegram-notification @COMP:service @TYPE:core
def send_order_failure_alert(self, strategy, account, symbol, error_type, error_message):
    """복구 불가능한 주문 실패 시 알림 (에러 처리)"""
    try:
        # 사용자별/전역 봇으로 메시지 전송
        # 실패해도 Exception 발생 안 함 (try-except로 처리됨)
        return self.send_message(...) or self.send_message_to_user(...)
    except Exception as e:
        logger.error(f"텔레그램 알림 발송 실패: {e}")
        return False  # 실패만 기록, 주요 서비스 계속 진행
```

**특징**:
- 텔레그램 API 오류 (`TelegramError`)는 로그만 기록
- 연결 실패, 토큰 오류 등은 자동으로 무시됨
- 주요 기능(주문 처리, 거래 실행 등)은 텔레그램 상태와 무관하게 진행

---

## 8. 유지보수 가이드

### 주의사항 (Critical Points)
- **Non-blocking 설계**: 텔레그램 알림 실패는 주요 서비스를 중단시키지 않음
  - 모든 호출부에 `try-except`로 보호됨
  - 예외는 로그에만 기록되고 계속 진행됨
- **빈 값 정규화**: 사용자 설정에서 빈 문자열(`""`)은 자동으로 `None`으로 변환됨
- **토큰 검증**: 사용자별 봇 토큰 생성 실패 시 자동으로 전역 봇으로 폴백
- **Rate Limit**: Telegram Bot API는 초당 30개 메시지 제한
  - 고빈도 알림 필요 시 배치 처리 권장 (일일 요약 예시)

### 새 기능 추가

#### 알림 타입 추가
1. `TelegramService`에 새 메서드 작성:
```python
# @FEAT:telegram-notification @COMP:service @TYPE:core
def send_new_alert(self, title, message, context=None):
    """새 알림 타입 추가"""
    if not self.is_enabled():
        return False
    # 메시지 포맷팅 + 전송
    return self.send_message(formatted_message)
```

2. 호출 지점에 통합:
```python
# 적절한 곳에서 호출
telegram_service.send_new_alert("제목", "메시지")
```

#### 메시지 포맷 커스터마이징
- 기본 제공 메서드들은 HTML 마크다운을 사용하고 있습니다
- 커스텀 포맷은 직접 메시지를 구성 후 `send_message()` 또는 `send_message_to_user()` 호출

### 트러블슈팅

| 증상 | 원인 | 해결 방법 |
|------|------|---------|
| 알림 미수신 | Chat ID 오류 | `User.query.get(id).telegram_id` 확인, 유효한 양수인지 검증 |
| | 봇 차단 | Telegram 앱에서 봇 차단 여부 확인, `/start` 메시지 전송 |
| | 토큰 오류 | `@BotFather` → `/mybots` 에서 토큰 재확인 |
| 메시지 포맷 깨짐 | HTML 태그 미닫음 | `<b>` 등의 태그 쌍 확인 |
| | 특수문자 | `<` → `&lt;`, `>` → `&gt;` 이스케이프 |
| 연결 테스트 실패 | 유효하지 않은 토큰 | 토큰 형식 확인 (콜론 포함: `123:ABC-xyz`) |
| | Chat ID 오류 | Chat ID가 유효한 양수인지 확인 |

**로그 확인**:
```bash
tail -f web_server/logs/app.log | grep -i "telegram"
# 특정 알림 타입
tail -f web_server/logs/app.log | grep -i "텔레그램\|telegram"
```

---

## 9. Known Issues

### 평문 저장 (security concern)
**문제**: Bot Token이 DB에 평문으로 저장됨
**현황**: `User.telegram_bot_token` (TEXT) 및 `SystemSetting` 테이블
**이유**: 초기 구현 단계에서 빠른 개발을 위해 선택됨
**개선**: 향후 encryption-at-rest(AES-256) 추가 예정

---

## 10. 코드 태그 (Grep Search)

```bash
# 텔레그램 알림 핵심 서비스 (메인 로직)
grep -r "@FEAT:telegram-notification" --include="*.py" | grep "@TYPE:core"

# 텔레그램 알림 헬퍼 함수 (유틸리티)
grep -r "@FEAT:telegram-notification" --include="*.py" | grep "@TYPE:helper"

# 텔레그램 알림 통합 지점 (호출 위치)
grep -r "@FEAT:telegram-notification" --include="*.py" | grep "@TYPE:integration"

# 모든 텔레그램 관련 코드
grep -r "@FEAT:telegram-notification" --include="*.py"

# 메인 서비스 파일
find web_server/app/services/ -name "*telegram*" -type f
```

---

## 11. 테스트 시나리오

### 전역 봇 연결 테스트

#### 1. 파라미터로 테스트 (저장 전 검증)
```bash
curl -X POST http://localhost:5000/admin/system/test-global-telegram \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_ID" \
  -d '{"bot_token": "123456:ABC-DEF...", "chat_id": "123456789"}'
```

**응답**:
```json
{
  "success": true,
  "message": "전역 텔레그램 연결 테스트 성공"
}
```

#### 2. 저장된 설정으로 테스트
```bash
curl -X POST http://localhost:5000/admin/system/test-global-telegram \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_ID" \
  -d '{}'  # 저장된 설정 사용
```

**필수 조건**:
- 관리자 권한 (`@admin_required`)
- 비밀번호 재확인 (`@admin_verification_required`)

### 사용자별 봇 연결 테스트
```bash
# 사용자 1번의 저장된 텔레그램 설정 테스트
curl -X POST http://localhost:5000/admin/users/1/test-telegram \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_ID"
```

**필수 조건**:
- 관리자 권한
- 비밀번호 재확인 (`@admin_verification_required`)

**응답**:
```json
{
  "success": true,
  "message": "텔레그램 연결 테스트 성공"
}
```

### 시스템 시작 알림 확인
```bash
# 서비스 재시작 (시스템 시작 알림 자동 발송)
python run.py restart

# 로그에서 확인
tail -f web_server/logs/app.log | grep "시스템 시작"
```

**예상 결과**:
- Telegram 앱에서 "트레이딩 시스템 시작" 알림 수신
- 로그: `✅ 통합 텔레그램 서비스 초기화 완료`

---

## 12. 관련 문서

- [웹훅 주문 처리](./webhook-order-processing.md)
- [주문 큐 시스템](./order-queue-system.md)
- [백그라운드 스케줄러](./background-scheduler.md)
- [아키텍처 개요](../ARCHITECTURE.md)

---

*Last Updated: 2025-10-30 (문서-코드 동기화 완료)*
*Version: 2.1.0 (Code-Synchronized)*
*Files Modified*:
- `services/telegram.py` (Main service, 801 lines)
- `routes/admin.py` (Admin endpoints with telegram settings)

**주요 개선 사항**:
- 완전한 메서드 매트릭스 추가 (25개 메서드 상세 설명)
- 우선순위 기반 봇 선택 로직 상세화
- 모든 알림 타입 코드 기준 업데이트
- 포괄적인 트러블슈팅 가이드
- API 엔드포인트 상세화
- Known Issues 섹션 추가
