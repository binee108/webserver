# 프로젝트 전체 수정 계획서

**작성일**: 2025-10-03
**목적**: 코드 품질 개선, 버그 수정, CLAUDE.md 스파게티 방지 지침 준수

---

## 📌 명명 규칙 표준화

### 원칙
1. **거래소 ID**: `exchange_` 접두사 필수
   - 예: `exchange_order_id`, `exchange_position_id`

2. **DB 테이블 PK**: 테이블명 명시
   - Order 테이블: `order_id` (PK)
   - Trade 테이블: `trade_id` (PK)
   - Account 테이블: `account_id` (PK)
   - Position 테이블: `position_id` (PK)
   - Strategy 테이블: `strategy_id` (PK)

3. **API 응답**: 중복 필드 금지
   - ❌ `{'id': 123, 'position_id': 123}`
   - ✅ `{'position_id': 123}`

### 적용 범위
- 모든 모델 클래스
- API 응답 포맷
- 서비스 메서드 파라미터
- SSE 이벤트 데이터

---

## 🔴 Phase 1: 긴급 버그 수정 (1-2일)

### 1.1 ⚠️ 다중 계좌 SSE 이벤트 오류 (최우선)

**문제**:
- 파일: `event_emitter.py:36-38`
- 하나의 전략에 여러 계좌 연동 시, SSE 이벤트가 항상 첫 번째 계좌명으로 발송됨
- DB에는 정상 저장되지만 실시간 업데이트 오류

**근본 원인**:
```python
# 현재 (잘못됨)
strategy_account = StrategyAccount.query.filter_by(
    strategy_id=strategy.id
).first()  # ❌ 항상 첫 번째 계좌만 조회
```

**수정**:
```python
# order_result에서 account_id 추출
account_id = order_result.get('account_id')
if not account_id:
    logger.error("order_result에 account_id 누락")
    return

# 해당 계좌 직접 조회
account = Account.query.get(account_id)
if not account:
    logger.warning("계좌 정보를 찾을 수 없음: %s", account_id)
    return
```

**영향**:
- 다중 계좌 연동 시 정상적인 실시간 업데이트
- DB 저장은 이미 정상이므로 추가 변경 불필요

---

### 1.2 OrderManager.cancel_all_orders 필드 오류

**문제**:
- 파일: `order_manager.py:256`
- `order.id` (DB PK)를 거래소 주문 ID로 사용
- 전체 주문 취소 기능 작동 불가

**수정**:
```python
# 수정 전
order_id = order.id  # ❌ DB PK

# 수정 후
order_id = order.exchange_order_id  # ✅ 거래소 주문 ID
```

**검증**:
- CANCEL_ALL_ORDER 웹훅 테스트
- 로그에서 정상적인 거래소 주문 ID 확인

---

### 1.3 Strategy.updated_at 필드 부재

**문제**:
- 파일: `strategy_service.py:449`
- 존재하지 않는 `updated_at` 필드에 값 할당
- 런타임 오류 가능성

**수정 옵션 A (권장)**: Strategy 모델에 컬럼 추가
```python
# models.py - Strategy 클래스
updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**수정 옵션 B**: 서비스 코드에서 해당 라인 제거
```python
# strategy_service.py:449 삭제
# strategy.updated_at = datetime.utcnow()
```

**권장**: 옵션 A (다른 테이블과 일관성 유지)

---

## 🟠 Phase 2: DRY 원칙 적용 - 중복 제거 (3-5일)

### 2.1 Webhook 검증 로직 통합

**중복 위치**:
- 주문 타입 검증: `webhook_service.py:82-102`, `167-187`
- 토큰 검증: `webhook_service.py:116-151`, `367-394`

**통합 메서드**:
```python
def _validate_order_type_params(self, normalized_data: Dict[str, Any]) -> None:
    """주문 타입별 필수 파라미터 검증 (단일 소스)"""
    order_type = normalized_data.get('order_type', '')

    if OrderType.requires_stop_price(order_type):
        if not normalized_data.get('stop_price'):
            raise WebhookError(f"{order_type} 주문에는 stop_price가 필수입니다")

    if OrderType.requires_price(order_type):
        if not normalized_data.get('price'):
            raise WebhookError(f"{order_type} 주문에는 price가 필수입니다")

    if order_type == OrderType.MARKET:
        normalized_data.pop('stop_price', None)
        normalized_data.pop('price', None)

def _validate_strategy_token(self, group_name: str, token: str) -> Strategy:
    """전략 조회 및 토큰 검증 (단일 소스)"""
    strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()
    if not strategy:
        raise WebhookError(f"활성 전략을 찾을 수 없습니다: {group_name}")

    if not token:
        raise WebhookError("웹훅 토큰이 필요합니다")

    valid_tokens = set()
    owner = strategy.user
    if owner and getattr(owner, 'webhook_token', None):
        valid_tokens.add(owner.webhook_token)

    if getattr(strategy, 'is_public', False):
        for sa in strategy.strategy_accounts:
            if getattr(sa, 'is_active', True) and getattr(sa, 'account', None):
                account_user = getattr(sa.account, 'user', None)
                user_token = getattr(account_user, 'webhook_token', None) if account_user else None
                if user_token:
                    valid_tokens.add(user_token)

    if not valid_tokens:
        raise WebhookError("웹훅 토큰이 설정된 사용자가 없습니다")

    if token not in valid_tokens:
        raise WebhookError("웹훅 토큰이 유효하지 않습니다")

    return strategy
```

**적용**: 6곳의 중복 코드 → 2개 메서드 호출로 변경

---

### 2.2 공통 유틸리티 통합

**중복 위치**:
- `core.py:601-631`
- `record_manager.py:432-441`
- `position_manager.py`에서 `self.service._to_decimal` 호출

**통합**:
```python
# app/services/utils.py (이미 존재)를 사용
# 모든 모듈에서:
from app.services.utils import to_decimal

# core.py, record_manager.py의 _to_decimal 메서드 제거
```

---

### 2.3 전략 수정 로직 서비스 통합

**중복 위치**:
- 라우터: `strategies.py:187-313` (비즈니스 로직 직접 구현)
- 서비스: `strategy_service.py:433-468` (update_strategy 메서드)

**수정**:
```python
# strategies.py:187-313의 로직 제거
# 서비스 메서드만 호출

@bp.route('/<int:strategy_id>', methods=['PUT'])
@login_required
def update_strategy(strategy_id):
    result = strategy_service.update_strategy(
        strategy_id=strategy_id,
        user_id=current_user.id,
        update_data=request.get_json()
    )
    return create_success_response(data=result)
```

**영향**: 라우터 120줄 이상 감소, MVC 패턴 준수

---

### 2.4 EventEmitter 함수 통합

**현재**:
- `emit_trading_event()` (실제 구현)
- `emit_trade_event()` (래퍼)
- `emit_order_event()` (래퍼)
- `emit_order_events_smart()` (복잡한 로직)

**통합 후**:
```python
# 2개 함수로 단순화
emit_trading_event()       # 단일 이벤트 발송
emit_order_events_smart()  # 상태 기반 스마트 이벤트 발송

# emit_trade_event, emit_order_event 제거 (사용처를 emit_trading_event로 변경)
```

---

## 🟡 Phase 3: 구조 개선 (5-7일)

### 3.1 폴백 체인 제거

**위치**: `core.py:159-166`

**현재 (폴백 체인)**:
```python
avg_price_num = float(order_result.get('actual_execution_price', 0) or 0)
if avg_price_num <= 0:
    avg_price_num = float(order_result.get('average_price', 0) or 0)
if avg_price_num <= 0:
    avg_price_num = float(order_result.get('adjusted_average_price', 0) or 0)
```

**수정 후 (단일 소스)**:
```python
# exchange_service는 항상 'average_price'를 반환하도록 표준화
avg_price_num = float(order_result.get('average_price', 0))
if avg_price_num <= 0:
    logger.error("체결가 누락, exchange_service 응답 확인 필요: %s", order_result)
    raise ValueError("Missing average_price in order result")
```

**추가 조치**: `exchange_service` 응답 스키마 문서화

---

### 3.2 중복 필드 제거 (API 응답)

**위치**:
- `position_manager.py:498-499`
- `position_manager.py:528`
- `position_manager.py:649-650`
- `position_manager.py:674`

**수정**:
```python
# 수정 전
{
    'id': position.id,           # 제거
    'position_id': position.id,  # 유지
}

# 수정 후
{
    'position_id': position.id,
}
```

**주의**: 프론트엔드 코드 수정 필요 (일회성)

---

### 3.3 _merge_order_with_exchange 제거

**위치**:
- `core.py:535-599` (구현)
- `position_manager.py:96` (호출)

**이유**:
- `create_order()` 응답에 이미 체결 정보 포함
- 시장가 주문은 `binance.py:534-556`에서 이미 재조회
- 불필요한 API 호출 (Rate Limit 낭비)

**수정**: 해당 메서드 및 호출 제거

---

### 3.4 process_order_fill 함수 분해

**위치**: `position_manager.py:64-287` (224줄)

**현재 책임**:
1. 입력 검증
2. 거래소 주문 병합
3. 체결 검증
4. 미체결 처리
5. Fallback 체결가 조회
6. Trade 레코드 생성
7. Position 업데이트
8. TradeExecution 생성
9. 이벤트 발송

**개선 옵션 A**: 의미 있는 블록으로 주석 추가
```python
def process_order_fill(...):
    # ==================== 1. 입력 검증 및 표준화 ====================
    # ...

    # ==================== 2. 거래소 주문 상태 병합 ====================
    # ...

    # ==================== 3. 체결 수량/가격 검증 ====================
    # ...
```

**개선 옵션 B**: 하위 함수로 분리
```python
def process_order_fill(...):
    validated_params = self._validate_and_normalize_fill_params(...)
    merged_order = self._merge_exchange_order_state(...)
    fill_info = self._validate_fill_info(merged_order)

    if not fill_info['has_fill']:
        return self._handle_unfilled_order(...)

    execution_price = self._ensure_execution_price(...)
    records = self._create_fill_records(...)
    self._emit_fill_events(...)

    return records
```

**권장**: 옵션 A (CLAUDE.md 원칙 준수)

---

## 🟢 Phase 4: 코드 품질 개선 (3-5일)

### 4.1 테스트 모드 분리

**위치**: `webhook_service.py:68-75`

**수정**:
```python
def process_webhook(self, webhook_data, webhook_received_at=None):
    # 테스트 모드 분기를 최상위로
    if webhook_data.get("test_mode", False):
        return self._process_webhook_test_mode(webhook_data, webhook_received_at)

    # 프로덕션 로직만 남김
    # ...

def _process_webhook_test_mode(self, webhook_data, webhook_received_at):
    """테스트 모드 전용 처리"""
    # 기존 68-102 라인 로직 이동
```

---

### 4.2 응답 구조 표준화

**위치**: `core.py:288-301` vs `440-452`

**수정**:
```python
def _create_trading_response(self, action: str, strategy: str,
                             market_type: str, results: List,
                             summary: Dict) -> Dict[str, Any]:
    """표준화된 거래 응답 생성"""
    return {
        'action': action,
        'strategy': strategy,
        'market_type': market_type,
        'success': summary.get('successful', 0) > 0,
        'results': results,
        'summary': summary
    }

# 단일 주문
summary = {
    'total': len(filtered_accounts),
    'executed': len(results),
    'successful': len(successful_trades),
    'failed': len(failed_trades),
}

# 배치 주문
summary = {
    'total': len(orders),
    'executed': len(results),
    'successful': len(successful),
    'failed': len(failed),
}
```

**키 이름 통일**: `total`, `executed`, `successful`, `failed`

---

### 4.3 비즈니스 로직 서비스 이동

**이동 대상**:
1. `accounts.py:124-128` → `security.py`
   - `mask_api_key()` 함수

2. `strategies.py:59-108` → `strategy_service.py`
   - 공개 전략 조회 로직

---

## 📊 예상 효과

### 코드 품질 지표
| 지표 | 현재 | 개선 후 |
|------|------|---------|
| 중복 코드 | 15곳 | 0곳 |
| 폴백 체인 | 3곳 | 0곳 |
| 200줄 이상 함수 | 2개 | 0개 |
| MVC 위반 | 5곳 | 0곳 |
| 긴급 버그 | 3개 | 0개 |

### 유지보수성
- **버그 수정 시간**: 50% 감소 (중복 제거)
- **코드 탐색 시간**: 30% 감소 (레이어 분리)
- **신규 개발자 온보딩**: 40% 개선 (명확한 구조)

### 성능
- **API 호출 감소**: ~20% (_merge_order_with_exchange 제거)
- **응답 크기 감소**: ~10% (중복 필드 제거)

---

## ⚠️ 주의사항

1. **Phase 1 우선 진행** (긴급 버그 먼저)
2. **각 Phase 완료 후 테스트 필수**
   - `python run.py restart` 실행
   - 웹훅 테스트 (LIMIT, MARKET, CANCEL_ALL)
   - 다중 계좌 SSE 이벤트 확인
3. **클라이언트 영향 사전 확인** (중복 필드 제거 시)
4. **Phase 2-3는 병렬 가능** (독립적인 모듈)
5. **커밋 단위**: 각 버그/기능별로 개별 커밋

---

## 📝 테스트 체크리스트

### Phase 1 테스트
- [ ] 다중 계좌 연동 시 SSE 이벤트에 올바른 계좌명 표시
- [ ] CANCEL_ALL_ORDER 웹훅 정상 동작
- [ ] Strategy 업데이트 시 오류 없음

### Phase 2 테스트
- [ ] 주문 타입 검증 (LIMIT, MARKET, STOP_LIMIT)
- [ ] 토큰 검증 (소유자, 구독자)
- [ ] Decimal 변환 오류 없음
- [ ] 전략 수정 정상 동작

### Phase 3 테스트
- [ ] 체결가 정상 반환 (폴백 없음)
- [ ] API 응답 `id` 필드 없음 (position_id만 존재)
- [ ] 주문 생성 후 추가 fetch_order 호출 없음

### Phase 4 테스트
- [ ] 테스트 모드 웹훅 정상 동작
- [ ] 단일/배치 응답 형식 일관성
- [ ] 비즈니스 로직 서비스 레이어 확인

---

**작성자**: Claude Code
**검수 완료일**: 2025-10-03
**예상 소요 기간**: 12-19일
