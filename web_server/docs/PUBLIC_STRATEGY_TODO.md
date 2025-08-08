# Public Strategy ToDo & Progress

상태 키: [ ] 예정, [~] 진행중, [x] 완료

## P0 — 보안/호환성
- [x] 공개 API에서 `group_name` 제거/비공개 처리
- [x] 사용자 고유 토큰 컬럼 추가: `users.webhook_token` (재발행 가능)
- [x] 프로필 페이지에 토큰 표시/재발행 UI 및 처리 추가
- [x] 웹훅 요청에 토큰 필드 추가 및 정규화
- [x] 웹훅 처리에서 전략 소유자 토큰 검증 (미일치/누락 거부)
- [x] 문서 업데이트: `WEBHOOK_GUIDE.md`에 토큰 필수화 및 예제 반영

## P1 — 조회/화면/알림 정합화
- [x] 조회/리포트 서비스에 구독 전략의 내 계좌만 노출 일관 적용 (positions/dashboard 등)
- [x] 프런트: "내 전략/구독 전략/공개 전략 탐색" 탭 추가 및 데이터 로드 (구독/공개)
- [x] 프런트: 공개 전략 상세 모달/구독 플로우, 구독 해제 버튼 추가
- [ ] 텔레그램/알림: 사용자(계좌 소유자) 기준 알림 분배 정책 보완

### 신규 이슈: 전략 공개/비공개 설정 UI/API 미비
- 현황 점검
  - 생성 API: is_public 지원 (strategy_service.create_strategy에서 처리)
  - 수정 API: is_public 미반영 (routes/strategies.py의 PUT 경로가 is_public을 무시)
  - 조회 API(단일/리스트): is_public 필드 누락 (get_strategies_by_user 결과에 없음)
  - 프런트 UI: `strategies.html`의 전략 추가/수정 모달에 공개/비공개 토글 없음

- 작업 항목 (P1)
  - [x] UI: 전략 추가/수정 모달에 "공개 전략" 토글 추가, 저장 시 is_public 포함 전송
  - [x] UI: 편집 시 is_public 값 채우기 (GET /api/strategies/<id> 응답에 포함 필요)
  - [ ] 목록 카드에 공개 배지(예: "공개") 표시(선택)
  - [x] API(조회): get_strategies_by_user 출력에 is_public 포함, GET /api/strategies/<id> 응답 반영
  - [x] API(수정): PUT /api/strategies/<id>에서 is_public 업데이트 반영 (소유자만)

## P2 — 마이그레이션/성능/운영
- [ ] Alembic 마이그레이션 정식화 (`strategies.is_public`, `users.webhook_token` + 인덱스)
- [ ] 레이트리밋/감사 강화: `/api/webhook` 요청 방어(토큰 기반이라도)
- [ ] 테스트: 토큰 검증/비공개 응답/에러 케이스 단위·통합 테스트

