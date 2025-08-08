# Public/Private 전략 지원 구조 변경 및 수정 계획서

## 목적
- 전략을 private(기본)과 public으로 구분
- public 전략은 타 사용자도 구독(Subscribe)하여 자신의 계좌로 동일 신호를 실행 가능
- 소유자만 전략 정의 수정 가능, 구독자는 본인 계좌 연결/해제 및 일부 실행 파라미터만 조정 가능

## 현재 구조 요약 (구현 기준)
- 웹훅: POST `/api/webhook` → `WebhookService.process_webhook()` → `TradingService.process_trading_signal()`
- 전략 식별: `Strategy.group_name`(UNIQUE)로 활성 전략 1개 조회
- 실행 단위: 조회된 `Strategy`의 `strategy_accounts`(다수 계좌)에 병렬 거래 실행
- 권한: 전략 생성/수정/연결은 소유자(`Strategy.user_id`)만 가능
- 이벤트/알림: SSE 이벤트에 `user_id=strategy.user_id`가 포함되어 소유자 기준 전송

## 변경 개요
- DB: `Strategy`에 `is_public BOOLEAN NOT NULL DEFAULT FALSE` 추가
- 권한: 
  - 소유자(owner): 전략 정의(이름/설명/시장타입/공개여부) 수정 가능
  - 구독자(subscriber): public 전략에 본인 계좌를 연결/해제 가능(타 사용자 자원 비가시화)
- 실행: 웹훅은 기존처럼 `group_name`으로 단일 전략에 매핑되며, 연결된 모든 계좌(소유+구독자)에서 거래 실행
- 이벤트/알림: 계좌 소유자 기준으로 전송(`account.user_id`)

## 데이터베이스 변경
- `strategies`
  - `is_public BOOLEAN NOT NULL DEFAULT FALSE`
  - 인덱스 권장: `CREATE INDEX idx_strategy_is_public ON strategies(is_public);`
- (선택) `webhook_logs`
  - 문서/구현 불일치 정리 시 `strategy_id` 컬럼 추가 고려

## 백엔드 API/서비스 변경
- 신규 API
  - GET `/api/strategies/public`: 공개 전략 목록(기본 정보, 일부 성능요약)
  - GET `/api/strategies/public/<strategy_id>`: 공개 전략 상세(정의 정보만)
  - POST `/api/strategies/<strategy_id>/subscribe`: 본인 계좌 연결(조건: `is_public==True` 또는 소유자)
  - DELETE `/api/strategies/<strategy_id>/subscribe/<account_id>`: 본인 계좌 연결 해제(활성 포지션 없음)
  - GET `/api/strategies/accessibles`: 내가 소유하거나 구독 중인 전략 목록
- 기존 API 조정
  - 소유자 전용 CRUD 유지
  - 계좌 연결/수정/삭제는 소유자 경로 유지, 구독자 경로는 subscribe 전용 API로 분리
- 서비스 로직
  - `get_accessible_strategies(user_id)`: 소유 전략 + 구독 전략을 합쳐 반환(계좌 정보는 본인 계좌로 한정)
  - `StrategyAccount` 생성 로직 분기(소유자/구독자)
  - `TradingService._emit_trading_events`: 이벤트의 `user_id`를 `account.user_id`로 설정
  - 텔레그램/알림도 계좌 소유자 단위로 분배

## 프런트엔드/UX 변경
- 전략 화면 탭: "내 전략" / "구독 전략" / "공개 전략 탐색"
- 공개 전략 상세: 소개/시장타입/예시, "구독하기"로 계좌 선택 후 연결
- 전략 상세(구독자): 본인 계좌에 한해 weight/leverage/max_symbols 설정 가능
- 포지션/주문/손익: 기본적으로 내 계좌 기준 필터(구독 전략 포함)

## 마이그레이션/배포 계획
1) DB: `is_public` 컬럼 및 인덱스 추가
2) API: 공개 목록/상세/구독 엔드포인트 추가, 접근 제어 반영
3) 이벤트: SSE/텔레그램 수신자 계좌 소유자 기준으로 변경
4) 프런트: 탐색/구독 UI 추가 및 목록 분리
5) 문서: WEBHOOK/전략관리 가이드 업데이트

롤백/가드
- 기능 플래그로 공개 전략 노출 제어
- 문제 시 구독 API 비활성화, 이벤트 수신자 기준은 토글 가능하게 설계

## 보안/성능/운영 고려
- 보안: 타 사용자 자원 비공개, 구독자 권한 최소화, 입력 검증 강화
- 성능: 대규모 구독자 전략 병렬 처리 시 스레드 제한 및 거래소 API 한도 고려(현행 max_workers<=4 유지/조정)
- 운영: 공개 전략 삭제는 모든 구독자 연결 해제 후 가능, 포지션 보유 계좌 해제 금지 유지

## 작업 항목(분류)
- 신규
  - `Strategy.is_public` 추가 및 인덱스
  - 공개 전략 목록/상세 API
  - 구독/해제 API
  - 접근 가능한 전략 합산 API
  - 프런트 공개 전략 탐색/구독 UI
- 수정
  - 이벤트/알림 수신자: `account.user_id`
  - 조회/리스트: 내 전략 + 구독 전략 혼합 뷰
  - 연결 로직: public 전략일 때 구독자 경로 허용
  - 문서: WEBHOOK/전략관리 가이드 정리(문서-구현 차이 주석 포함)
