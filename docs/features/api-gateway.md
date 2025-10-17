# API Gateway

## 개요

API Gateway는 웹 애플리케이션의 주요 라우팅 계층으로, 대시보드, 메인 페이지, 포지션/주문 조회 API 엔드포인트를 제공합니다. 사용자 인증을 기반으로 개인화된 데이터를 제공하며, Service 계층과 연계하여 비즈니스 로직을 처리합니다.

## 주요 기능

### 1. Dashboard API (`/api/dashboard/*`)

사용자별 대시보드 통계 및 최근 거래 내역을 제공합니다.

**엔드포인트:**
- `GET /api/dashboard/stats`: 대시보드 통계 조회 (전략 수, 총 수익률, 오늘 거래 등)
- `GET /api/dashboard/recent-trades`: 최근 거래 내역 조회 (페이지네이션 지원)

**핵심 로직:**
- `analytics_service`를 통한 통계 데이터 집계
- 사용자별 데이터 격리 (`current_user.id` 기반)
- 페이지네이션: `limit` (최대 100), `offset` 파라미터

### 2. Main Page Routes (`/`)

웹 애플리케이션의 메인 페이지 및 대시보드 렌더링을 담당합니다.

**엔드포인트:**
- `GET /`: 홈페이지 (로그인 시 대시보드로 리다이렉트)
- `GET /dashboard`: 대시보드 페이지 (전략/거래 요약)
- `GET /accounts`: 계좌 관리 페이지
- `GET /strategies`: 전략 관리 페이지
- `GET /strategies/<strategy_id>/positions`: 전략별 포지션 페이지

**핵심 로직:**
- Flask 템플릿 렌더링 (`render_template`)
- 사용자 인증 상태에 따른 리다이렉트
- DB 직접 조회를 통한 초기 데이터 로딩

### 3. Positions & Orders API (`/api/positions/*`, `/api/open-orders/*`)

포지션 및 주문 관리를 위한 RESTful API를 제공합니다.

**주요 엔드포인트:**

**포지션 관리:**
- `POST /api/positions/<position_id>/close`: 포지션 청산
- `GET /api/positions-with-orders`: 포지션과 열린 주문 통합 조회
- `GET /api/symbol/<symbol>/positions-orders`: 심볼별 포지션/주문 조회
- `GET /api/strategies/<strategy_id>/positions`: 전략별 포지션 조회

**주문 관리:**
- `GET /api/open-orders`: 사용자의 모든 열린 주문 조회
- `POST /api/open-orders/<order_id>/cancel`: 개별 주문 취소
- `POST /api/open-orders/cancel-all`: 일괄 주문 취소 (전략/계좌/심볼 필터 지원)
- `POST /api/open-orders/status-update`: 주문 상태 수동 업데이트 트리거
- `GET /api/strategies/<strategy_id>/my/open-orders`: 구독 전략의 내 주문 조회

**실시간 업데이트:**
- `GET /api/events/stream`: SSE (Server-Sent Events) 스트림
- `GET /api/auth/check`: 로그인 상태 확인 (SSE 연결 전 체크)
- `GET /api/events/stats`: 이벤트 서비스 통계 (관리자용)

### 4. Strategy Management API (`/api/strategies/*`)

전략 생성, 수정, 삭제, 계좌 연결, 공개 전략 구독 기능을 제공합니다.

**전략 CRUD:**
- `GET /api/strategies`: 사용자의 전략 목록 조회
- `POST /api/strategies`: 새 전략 생성
- `GET /api/strategies/<strategy_id>`: 전략 정보 조회
- `PUT /api/strategies/<strategy_id>`: 전략 정보 수정
- `DELETE /api/strategies/<strategy_id>`: 전략 삭제
- `POST /api/strategies/<strategy_id>/toggle`: 전략 활성화/비활성화 토글

**계좌 연결 관리:**
- `GET /api/strategies/<strategy_id>/accounts`: 전략에 연결된 계좌 목록
- `POST /api/strategies/<strategy_id>/accounts`: 전략에 계좌 연결
- `PUT /api/strategies/<strategy_id>/accounts/<account_id>`: 계좌 설정 업데이트
- `DELETE /api/strategies/<strategy_id>/accounts/<account_id>`: 계좌 연결 해제

**공개 전략 기능:**
- `GET /api/strategies/accessibles`: 접근 가능한 전략 목록 (소유+구독)
- `GET /api/strategies/public`: 공개 전략 목록 조회
- `GET /api/strategies/public/<strategy_id>`: 공개 전략 상세 조회
- `POST /api/strategies/<strategy_id>/subscribe`: 공개 전략 구독
- `DELETE /api/strategies/<strategy_id>/subscribe/<account_id>`: 구독 해제

**성과 조회:**
- `GET /api/strategies/<strategy_id>/performance/roi`: ROI 및 손익 분석
- `GET /api/strategies/<strategy_id>/performance/summary`: 성과 요약 조회
- `GET /api/strategies/<strategy_id>/performance/daily`: 일일 성과 조회

### 5. Capital Management API (`/api/capital/*`)

계좌별 자본 배분 및 리밸런싱 기능을 제공합니다.

**자본 배분:**
- `POST /api/capital/reallocate/<account_id>`: 계좌의 자본 재배분
- `POST /api/capital/reallocate-all`: 모든 계좌 자본 재배분
- `GET /api/capital/rebalance-status/<account_id>`: 리밸런스 상태 조회
- `POST /api/capital/auto-rebalance-all`: 자동 리밸런싱 수동 트리거

### 6. Admin & System API (`/api/*`, `/api/system/*`)

시스템 모니터링, 관리자 기능, 백그라운드 작업 제어를 제공합니다.

**시스템 모니터링:**
- `GET /api/system/health`: 시스템 헬스 체크 (공개)
- `GET /api/system/scheduler-status`: APScheduler 작업 상태 조회 (관리자)
- `GET /api/system/cache-stats`: 캐시 통계 조회 (관리자)
- `GET /api/metrics`: 시스템 메트릭 조회 (관리자)

**시스템 제어:**
- `POST /api/system/scheduler-control`: 스케줄러 시작/중지/재시작 (관리자)
- `POST /api/system/trigger-job`: 백그라운드 작업 수동 실행 (관리자)
- `POST /api/system/cache-clear`: 캐시 정리 (관리자)
- `POST /api/system/test-telegram`: 텔레그램 연결 테스트 (관리자)

**주문 대기열 관리:**
- `GET /api/queue-status`: 주문 대기열 상태 조회 (관리자)
- `POST /api/queue-rebalance`: 대기열 재정렬 수동 트리거 (관리자)

**핵심 로직:**
- Service 계층 위임: `trading_service`, `strategy_service`, `analytics_service`, `capital_service` 활용
- 사용자 권한 검증: 전략 소유자 또는 구독자만 접근 가능
- 전략 격리: `strategy_id` 기반 데이터 필터링
- 통합 조회: 포지션 + 열린 주문 단일 API로 제공
- SSE 기반 실시간 이벤트 푸시
- 관리자 전용 API: `current_user.is_admin` 검증

## 데이터 구조 일관성

### API 응답 필드 명명 규칙

```json
{
  "position_id": 123,           // ✅ StrategyPosition.id
  "order_id": "binance_order_1", // ✅ OpenOrder.exchange_order_id
  "account": {
    "name": "Account A",
    "exchange": "binance"
  }
}
```

**주의사항:**
- 포지션: `position_id` 사용 (~~id~~, ~~position.id~~ 금지)
- 주문: `order_id` 사용 (~~exchange_order_id~~ 노출 금지)
- 계좌: `account` 객체로 통일 (중첩 구조)

## 의존성

### Service 계층
- **analytics_service** (`@FEAT:analytics`): 대시보드 통계 집계, 일일 요약
- **trading_service** (`@FEAT:position-tracking`, `@FEAT:order-tracking`): 포지션/주문 조회, 청산, 취소
- **strategy_service** (`@FEAT:strategy-management`): 전략 CRUD, 계좌 연결, 공개 전략 구독
- **capital_service** (`@FEAT:capital-management`): 자본 배분, 리밸런싱
- **event_service** (`@FEAT:event-sse`): SSE 이벤트 스트림 관리
- **performance_tracking_service** (`@FEAT:analytics`): 전략 성과 추적, ROI 계산

### Models
- **Strategy**, **Account**, **StrategyAccount**: 전략/계좌 관계
- **StrategyPosition**: 포지션 데이터
- **OpenOrder**, **PendingOrder**: 주문 데이터
- **Trade**: 거래 내역

## 보안 고려사항

1. **사용자 인증**:
   - 대부분의 API 엔드포인트에 `@login_required` 적용
   - 예외: `/api/system/health` (공개), `/api/webhook` (토큰 인증)
2. **권한 검증**:
   - 전략 소유자 확인: `strategy.user_id == current_user.id`
   - 구독자 확인: `StrategyAccount` 테이블 조인 검증
   - 관리자 전용 API: `current_user.is_admin` 검증
3. **데이터 격리**: 사용자별 데이터만 반환 (`current_user.id` 필터)
4. **입력 검증**:
   - `strategy_id`, `account_id` 타입 검증
   - `limit` 최대값 제한 (100)
   - Response Formatter를 통한 표준 에러 처리 (`ErrorCode` 클래스 사용)
5. **CORS**: 현재 CORS 미설정 (필요 시 Flask-CORS 추가 필요)

## 검색 예시

```bash
# API Gateway의 모든 코드 찾기
grep -r "@FEAT:api-gateway" --include="*.py"

# 핵심 라우트 핸들러만 찾기
grep -r "@FEAT:api-gateway" --include="*.py" | grep "@TYPE:core"

# Dashboard API만 찾기
grep -r "@FEAT:api-gateway" --include="*.py" | grep "@FEAT:analytics"

# 포지션 관련 API만 찾기
grep -r "@FEAT:api-gateway" --include="*.py" | grep "@FEAT:position-tracking"

# 주문 관련 API만 찾기
grep -r "@FEAT:api-gateway" --include="*.py" | grep "@FEAT:order-tracking"
```

## 유지보수 노트

1. **라우트 추가 시**:
   - 적절한 `@FEAT` 태그 추가 (api-gateway + 관련 기능)
   - Service 계층 위임 패턴 유지
   - 사용자 권한 검증 필수 (`@login_required`, 관리자 API는 `is_admin` 체크)
   - 표준 Response Formatter 사용 (`create_success_response`, `create_error_response`)

2. **API 응답 수정 시**:
   - 명명 규칙 준수 (`position_id`, `order_id`)
   - 프론트엔드 호환성 확인
   - ErrorCode 클래스 사용 (HTTP 상태 코드 자동 매핑)

3. **SSE 관련**:
   - `event_service` 로직 확인 필요
   - 클라이언트 연결 관리 주의
   - `/api/auth/check`를 통한 사전 인증 체크 권장

4. **성능 최적화**:
   - 페이지네이션 활용 (`limit`, `offset`)
   - `joinedload`, `selectinload` ORM 최적화
   - 중복 DB 쿼리 방지
   - 캐시 활용 (가격 캐시, 거래소 연결 캐시)

5. **에러 처리**:
   - 비즈니스 로직 에러: `ErrorCode.BUSINESS_LOGIC_ERROR` (422)
   - 권한 에러: `ErrorCode.ACCESS_DENIED` (403)
   - 리소스 없음: `ErrorCode.STRATEGY_NOT_FOUND` (404)
   - 검증 에러: `ErrorCode.VALIDATION_ERROR` (422)
