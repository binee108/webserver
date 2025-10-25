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

### 4.1 TelegramService

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `services/telegram.py` | 텔레그램 메시지 전송 및 봇 관리 | `@FEAT:telegram-notification @COMP:service @TYPE:core` | `send_order_adjustment_notification()`<br>`send_error_alert()`<br>`send_webhook_error()`<br>`send_order_failure_alert()`<br>`send_daily_summary()`<br>`send_system_status()` |

**봇 선택 로직**:
```python
# @FEAT:telegram-notification @COMP:service @TYPE:core
def get_effective_bot_and_chat(user_telegram_bot_token, user_telegram_id):
    # 1순위: 사용자별 봇
    if user_telegram_bot_token and user_telegram_id:
        return self.get_user_bot(user_telegram_bot_token), user_telegram_id
    # 2순위: 전역 봇 + 사용자 Chat ID
    if user_telegram_id and self.bot:
        return self.bot, user_telegram_id
    # 3순위: 전역 봇 + 전역 Chat ID
    if self.bot and self.chat_id:
        return self.bot, self.chat_id
    return None, None
```

### 4.2 알림 발송 위치 (Integration Points)

| 위치 | 파일 | 알림 메서드 | 알림 타입 | 태그 |
|------|------|-------------|-----------|------|
| 웹훅 처리 | `routes/webhook.py` | `send_webhook_error()` | 웹훅 오류 | `@FEAT:telegram-notification @TYPE:integration` |
| 주문 큐 | `trading/order_queue_manager.py` | `send_order_failure_alert()` | 주문 실패 | `@FEAT:telegram-notification @TYPE:integration` |
| 수량 조정 | TBD | `send_order_adjustment_notification()` | 수량 조정 | `@FEAT:telegram-notification @TYPE:integration` |
| 백그라운드 | `background/queue_rebalancer.py` | `send_error_alert()` | 시스템 오류 | `@FEAT:telegram-notification @TYPE:integration` |
| WebSocket | `exchanges/binance_websocket.py`<br>`exchanges/bybit_websocket.py` | `send_error_alert()` | WebSocket 오류 | `@FEAT:telegram-notification @TYPE:integration` |
| 시스템 시작 | `app/__init__.py` | `send_system_status('startup')` | 시스템 상태 | `@FEAT:telegram-notification @TYPE:integration` |

**참고**:
- `send_exchange_error()` 메서드는 구현되어 있으나 현재 실제 사용되는 곳이 없음
- `send_trading_error()` 메서드는 구현되어 있으나 통합 지점이 명확하지 않음

### 4.3 알림 타입

| 알림 타입 | 메서드 | 트리거 | 이모지 | 사용 여부 |
|-----------|--------|--------|--------|-----------|
| 주문 수량 조정 | `send_order_adjustment_notification()` | 최소 요구사항 미달 자동 조정 | 📊 | ✅ 사용 중 |
| 시스템 오류 | `send_error_alert()` | WebSocket 오류, 백그라운드 작업 실패 | 🚨 | ✅ 사용 중 |
| 웹훅 오류 | `send_webhook_error()` | 웹훅 처리 중 예외 | 🚨 | ✅ 사용 중 |
| 거래 실행 오류 | `send_trading_error()` | 거래 실행 중 오류 | 🚨 | ✅ 사용 중 |
| 거래소 연결 오류 | `send_exchange_error()` | 거래소 API 호출 실패 | ⚠️ | ⚠️ 메서드 존재하나 미사용 |
| 주문 실패 | `send_order_failure_alert()` | 복구 불가능 오류 (잔고 부족 등) | ⚠️ | ✅ 사용 중 |
| 시스템 상태 | `send_system_status()` | 시스템 시작/종료 | ✅/🔴 | ✅ 사용 중 |
| 일일 요약 | `send_daily_summary()` | 매일 정해진 시간 | 📊 | ✅ 사용 중 |

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

### 5.3 설정 방법

1. **텔레그램 봇 생성**:
   - Telegram에서 `@BotFather` 검색 → `/newbot` 명령어
   - Bot Token 복사

2. **Chat ID 확인**:
   - `@userinfobot`에게 메시지 전송하여 Chat ID 확인

3. **웹 UI 설정**:
   - 전역 봇 설정 (관리자): `/admin/system/telegram-settings` (GET/POST)
   - 사용자별 봇 설정 (관리자): `/admin/users/<user_id>/telegram-settings` (GET/POST)
   - **참고**: 사용자 자신이 직접 설정하는 엔드포인트는 현재 미구현

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

### Bot Token 보호
- **전역 봇**: `SystemSetting` 테이블 (평문 저장, DB 접근 제한으로 보호)
- **사용자 봇**: `User.telegram_bot_token` (평문 저장 - TEXT 필드)
- **권고**: `.env` 파일 `.gitignore` 포함, 절대 하드코딩 금지

### 에러 처리
- 텔레그램 알림 실패는 **치명적 오류로 간주하지 않음**
- 로그 기록 후 주요 서비스 계속 진행

```python
try:
    telegram_service.send_error_alert(...)
except Exception as e:
    logger.warning(f"텔레그램 알림 발송 실패: {e}")
    # 서비스 계속 진행
```

---

## 8. 유지보수 가이드

### 주의사항
- 텔레그램 알림 실패로 주요 서비스 중단되지 않도록 try-except 필수
- Rate Limit 고려 (메시지 발송 빈도 조절)
- HTML 마크다운 태그 닫기 확인
- 사용자 봇 토큰은 평문 저장 (암호화 필요 시 향후 개선)

### 확장 포인트
- 새 알림 타입 추가: `TelegramService`에 메서드 추가 + 호출 지점에 통합
- 알림 템플릿: 메시지 포맷팅 로직을 별도 메서드로 분리 가능
- 메시지 큐: Rate Limit 대응을 위해 메시지 큐잉 시스템 추가 가능

### 트러블슈팅

1. **알림 미수신**:
   - Chat ID 확인: `User.query.get(user_id).telegram_id`
   - 봇 차단 여부 확인 (Telegram 앱)
   - 연결 테스트: `telegram_service.test_user_connection()`

2. **메시지 포맷 깨짐**:
   - HTML 태그 닫기 확인 (`<b>`, `</b>`)
   - 특수문자 이스케이프 (< → &lt;, > → &gt;)

3. **API 호출 실패**:
   - Bot Token 재확인 (`@BotFather` → `/mybots`)
   - 로그 확인: `tail -f web_server/logs/app.log | grep "텔레그램"`

4. **Rate Limit 초과**:
   - 메시지 발송 빈도 조절
   - 배치 알림으로 통합 (일일 요약)

---

## 9. 코드 태그 (Grep Search)

```bash
# 텔레그램 알림 핵심 서비스
grep -r "@FEAT:telegram-notification" --include="*.py" | grep "@TYPE:core"

# 텔레그램 알림 통합 지점
grep -r "@FEAT:telegram-notification" --include="*.py" | grep "@TYPE:integration"

# 모든 텔레그램 관련 코드
grep -r "@FEAT:telegram-notification" --include="*.py"

# 텔레그램 서비스 파일
grep -r "telegram" --include="*.py" web_server/app/services/
```

---

## 10. 테스트 시나리오

### 전역 봇 연결 테스트
```bash
# 입력된 파라미터로 테스트 (저장 전 검증용)
curl -k -X POST https://222.98.151.163/admin/system/test-global-telegram \
  -H "Content-Type: application/json" \
  -d '{"bot_token": "YOUR_BOT_TOKEN", "chat_id": "YOUR_CHAT_ID"}'

# 저장된 설정으로 테스트
curl -k -X POST https://222.98.151.163/admin/system/test-global-telegram \
  -H "Content-Type: application/json" \
  -d '{}'
```

**참고**: 이 엔드포인트는 `@admin_verification_required` 데코레이터가 적용되어 있어 비밀번호 재확인이 필요합니다.

### 사용자별 봇 연결 테스트
```bash
# 저장된 사용자 설정으로 테스트 (관리자만)
curl -k -X POST https://222.98.151.163/admin/users/1/test-telegram \
  -H "Content-Type: application/json"
```

**참고**: 이 엔드포인트는 `@admin_verification_required` 데코레이터가 적용되어 있어 비밀번호 재확인이 필요합니다.

### 시스템 시작 알림 확인
```bash
python run.py restart
# 텔레그램 앱에서 시스템 시작 알림 수신 확인
```

---

## 11. 관련 문서

- [웹훅 주문 처리](./webhook-order-processing.md)
- [주문 큐 시스템](./order-queue-system.md)
- [백그라운드 스케줄러](./background-scheduler.md)
- [아키텍처 개요](../ARCHITECTURE.md)

---

*Last Updated: 2025-10-11*
*Version: 2.0.0 (Condensed)*
