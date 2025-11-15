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
- `POST /api/positions/<position_id>/close`: 포지션 청산 (Service 계층 위임)
- `GET /api/positions-with-orders`: 포지션과 열린 주문 통합 조회
- `GET /api/symbol/<symbol>/positions-orders`: 심볼별 포지션/주문 조회
- `GET /api/strategies/<strategy_id>/positions`: 전략별 포지션 조회 (API 엔드포인트)

**주문 관리:**
- `GET /api/open-orders`: 사용자의 모든 열린 주문 조회
- `POST /api/open-orders/<order_id>/cancel`: 개별 주문 취소
- `POST /api/open-orders/cancel-all`: 일괄 주문 취소 (전략/계좌/심볼 필터 지원)
- `POST /api/open-orders/status-update`: 주문 상태 수동 업데이트 트리거
- `GET /api/strategies/<strategy_id>/my/open-orders`: 구독 전략의 내 주문 조회 (구독자 계좌만)

**실시간 업데이트:**
- `GET /api/events/stream`: SSE (Server-Sent Events) 스트림 (strategy_id 필수)
- `GET /api/auth/check`: 로그인 상태 확인 (인증 불필요, SSE 연결 전 체크용)
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
- **analytics_service** (`@FEAT:analytics`): 대시보드 통계 집계, 최근 거래 내역 조회
- **trading_service** (`@FEAT:position-tracking`, `@FEAT:order-tracking`): 포지션/주문 조회, 청산, 취소, 상태 업데이트
- **strategy_service** (`@FEAT:strategy-management`): 전략 CRUD, 계좌 연결, 공개 전략 구독, 접근 권한 검증
- **capital_service** (`@FEAT:capital-management`): 자본 배분, 리밸런싱 (현재 문서에서 미사용)
- **event_service** (`@FEAT:event-sse`): SSE 이벤트 스트림 관리, 실시간 업데이트
- **performance_tracking_service** (`@FEAT:analytics`): 전략 성과 추적, ROI 계산 (현재 문서에서 미사용)

### Models
- **Strategy**, **Account**, **StrategyAccount**: 전략/계좌 관계
- **StrategyPosition**: 포지션 데이터
- **OpenOrder**, **PendingOrder**: 주문 데이터
- **Trade**: 거래 내역

## 보안 고려사항

1. **사용자 인증**:
   - 대부분의 API 엔드포인트에 `@login_required` 적용
   - 예외: `/api/auth/check` (로그인 상태 조회, 사전 인증용)
2. **권한 검증**:
   - 전략 접근: `StrategyService.verify_strategy_access(strategy_id, user_id)` 사용
   - 포지션/주문: 현재 사용자의 계좌에 속한 데이터만 조회 (`Account.user_id == current_user.id`)
   - 관리자 전용 API: `/api/events/stats` 등에서 `current_user.is_admin` 검증
3. **데이터 격리**:
   - 사용자별 데이터만 반환 (`current_user.id` 필터)
   - SSE 스트림은 strategy_id 필수 파라미터로 특정 전략만 구독 가능
4. **입력 검증**:
   - `strategy_id`, `account_id` 정수 타입 검증
   - `limit` 최대값 제한 (100)
   - JSON 파싱 실패 시 안전한 기본값 사용
   - 필수 파라미터 부재 시 명확한 에러 메시지 반환
5. **실시간 스트림**:
   - SSE 연결 전 권한 검증 (유효하지 않은 strategy_id 시 403 반환)

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
   - Service 계층 위임 패턴 유지 (라우트는 검증만, 비즈니스 로직은 Service에)
   - 사용자 권한 검증: `@login_required` 기본, 공개 엔드포인트는 명시적으로 문서화
   - 권한 검증: 관리자 API는 `current_user.is_admin`, 전략 접근은 `StrategyService.verify_strategy_access()` 사용

2. **API 응답 명명 규칙**:
   - 포지션: `position_id` 사용 (DB pk는 `StrategyPosition.id`)
   - 주문: `order_id` 사용 (DB pk는 `OpenOrder.exchange_order_id`)
   - 계좌: `account` 객체 중첩 구조 (name, exchange 포함)
   - 프론트엔드 호환성 변경 시 웹 UI 함께 수정

3. **SSE 스트림 관리**:
   - `strategy_id` 필수 파라미터 필수
   - 연결 전 권한 검증으로 데이터 격리
   - `/api/auth/check` 통해 사전 인증 상태 확인 권장
   - 응답 상태 코드: 권한 부재 시 403, 파라미터 누락 시 400

4. **성능 최적화**:
   - ORM joinedload/selectinload 활용 (N+1 쿼리 방지)
   - 페이지네이션 구현: `limit` (기본 20, 최대 100), `offset`
   - 대량 데이터 조회 시 DB 직접 쿼리 검토 필요

5. **에러 처리 패턴**:
   - Service 계층 에러 반환값 사용: `success`, `error` 필드
   - HTTP 상태: 성공 200, 권한 403, 불완전 207, 실패 400/500

## 주요 변경 이력

- **2025-10-30**: 코드 기준 동기화
  - `/api/strategies/<strategy_id>/positions` API 엔드포인트 명확화
  - `/api/auth/check` 인증 불필요 명시
  - Service 계층 의존성 설명 정확화
  - SSE 권한 검증 절차 추가
  - 보안 고려사항: 입력 검증 및 에러 처리 실제 구현 기반 업데이트
  - 유지보수 노트: 명명 규칙 및 패턴 실제 코드 기준 재작성

Last Updated: 2025-10-30
