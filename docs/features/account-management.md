# 계좌 관리 (Account Management)

> **목적**: 거래소 계좌의 CRUD, API 키 암호화 관리, 연결 테스트 및 잔고 조회 기능 제공

## 태그 검색
```bash
# 전체 코드
grep -r "@FEAT:account-management" --include="*.py" --include="*.js"

# 핵심 로직
grep -r "@FEAT:account-management.*@TYPE:core" --include="*.py" --include="*.js"

# API 엔드포인트
grep -r "@FEAT:account-management.*@COMP:route" --include="*.py" --include="*.js"

# 서비스 로직
grep -r "@FEAT:account-management.*@COMP:service" --include="*.py"
```

---

## 아키텍처

### 실행 플로우
```
User Request → Route (accounts.py) → Service (security.py) → DB (models.py)
                ↓ @login_required          ↓ 암호화/복호화       ↓ Account
                ↓ 권한 검증                 ↓ 거래소 연동         ↓ DailyAccountSummary
                ↓ Frontend (accounts.js)   ↓ 캐시 무효화
```

### 데이터 플로우
1. **생성**: API 키 암호화 → DB 저장 → 잔고 조회 → 스냅샷 저장
2. **조회**: DB 조회 → API 키 복호화(캐싱) → 마스킹 처리 → 응답
3. **수정**: 권한 검증 → 재암호화 → 캐시 무효화 → DB 업데이트
4. **삭제**: 권한 검증 → CASCADE 삭제 (연관 데이터 자동 삭제)

### 주요 컴포넌트
| 컴포넌트 | 파일 | 태그 | 역할 |
|---------|------|------|------|
| Frontend | `static/js/accounts.js` | `@COMP:route` | 계좌 폼 제출, UI 업데이트 |
| Route | `routes/accounts.py` | `@COMP:route` | HTTP 요청 처리, 인증/권한 검증 |
| Service | `services/security.py` | `@COMP:service` | 비즈니스 로직, 암호화 |
| Model | `models.py` | `@COMP:model` | Account, DailyAccountSummary |
| Exchange | `services/exchange.py` | `@DEPS:exchange-integration` | 거래소 API 통합 |
| Encryption | `security/encryption.py` | `@TYPE:helper` | Fernet 암호화/복호화 |

---

## 주요 기능

### 1. 계좌 CRUD
- **생성**: API 키 Fernet 암호화 저장, 잔고 조회 및 스냅샷 저장
- **조회**: 사용자 계좌 목록/상세, API 키 마스킹 처리 (앞뒤 4자리만 표시), KRW→USDT 변환 (Phase 2)
- **수정**: 계좌명, 활성화 상태, API 키 재등록 (캐시 무효화), 비활성화 시 SSE 종료 (Phase 4)
- **삭제**: CASCADE 물리 삭제 (연관 전략, 주문, 포지션 등 자동 삭제)
- **계좌 타입**: CRYPTO (암호화폐) / STOCK (증권) 구분 지원

### 2. 보안
- **암호화**: Fernet (AES-128-CTR + HMAC-SHA256), 클래스 레벨 캐시 (최대 1000개)
- **권한 검증**: 본인 계좌만 접근 (`user_id` 필터링)
- **레거시 감지**: Werkzeug 해시 방식 API 키 감지 및 재저장 유도

### 3. 거래소 연동
- **연결 테스트**: API 키 유효성 검증, 잔고 조회 성공 여부 확인
- **잔고 조회**: Spot/Futures 구분, 자산별 free/locked/total 조회, 환율 기반 KRW→USDT 변환 (Phase 2)
- **스냅샷 저장**: DailyAccountSummary 테이블에 일일 잔고 자동 저장 (Spot/Futures 분리)
- **환율 적용**: PriceCache에서 USDT/KRW 환율 조회, Graceful Degradation (환율 조회 실패 시 원화 표시)

### 4. 증권 계좌 지원 (신규)
- **OAuth 토큰**: 한국투자증권 등 OAuth 기반 인증 토큰 암호화 저장
- **증권 설정**: 계좌번호, 상품코드 등 증권사별 설정 JSON 암호화 저장
- **토큰 관리**: SecuritiesToken 테이블로 토큰 캐싱 및 자동 갱신

---

## API 엔드포인트

### 1. 계좌 목록 조회
```http
GET /api/accounts
Authorization: Required
```
**응답**: 계좌 목록 + 최신 잔고 (`latest_balance`, `latest_balance_date`)

**KRW → USDT 변환 (Phase 2 신규)**:
- 국내 거래소(UPBIT, BITHUMB) 계좌의 KRW 잔고 자동 변환
- 환율 조회 성공 시: `latest_balance` (USDT), `original_balance_krw`, `usdt_krw_rate` 포함
- 환율 조회 실패 시: KRW 원화 표시, `conversion_error: "환율 조회 실패"` 설정
- 환율 데이터 이상(0 이하) 시: `conversion_error: "환율 데이터 이상"` 설정
- 해외 거래소: 변환 없음, `currency_converted: false`

### 2. 계좌 생성
```http
POST /api/accounts
Content-Type: application/json

{
  "name": "Binance Futures",
  "exchange": "BINANCE",
  "public_api": "your_api_key",
  "secret_api": "your_secret_key",
  "passphrase": "",
  "is_testnet": false,
  "is_active": true
}
```
**응답**: `account_id`, `balance_snapshot` (total_balance, market_summaries)

### 3. 계좌 상세 조회
```http
GET /api/accounts/{account_id}
```
**응답**: 계좌 상세 정보, API 키 마스킹 (`abcd****wxyz`), 복호화된 전체 키 (`public_api_full`)

### 4. 계좌 수정
```http
PUT /api/accounts/{account_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "is_active": true,
  "public_api": "new_api_key",  // 선택 (빈 문자열이면 전송하지 않음 - Phase 2)
  "secret_api": "new_secret_key"  // 선택 (빈 문자열이면 전송하지 않음 - Phase 2)
}
```
**로직**: API 키 변경 시 재암호화 + 캐시 무효화 + ExchangeService 캐시 무효화

**Phase 2 개선 (2025-10-13)**:
- 프론트엔드에서 빈 문자열/null인 API 키 필드를 요청에서 제외
- 계좌 이름만 변경 시 불필요한 캐시 무효화 방지
- 백엔드 `update_account` 메서드의 Variable Shadowing 버그 수정 (Phase 1)

**Phase 4 신규 기능 (2025-10-30)**:
- 계좌 비활성화(`is_active=false`) 시 연결된 모든 활성 전략의 SSE 클라이언트 즉시 종료
- 이유: 사용자가 거래소 키를 수동 폐기하면 해당 계좌로 더 이상 주문 불가능하므로 실시간 스트림 연결 해제 필요
- 로직: `event_service.disconnect_client(user_id, strategy_id, reason='account_deactivated')` 호출

### 5. 계좌 삭제
```http
DELETE /api/accounts/{account_id}
```
**로직**: CASCADE 물리 삭제 (StrategyAccount, Trade, OpenOrder, DailyAccountSummary 등)

### 6. 연결 테스트
```http
POST /api/accounts/{account_id}/test
```
**응답**: 거래소 연결 상태, total_balance, market_summaries, snapshot_at

### 7. 잔고 조회
```http
GET /api/accounts/{account_id}/balance
```
**응답**: 실시간 Spot/Futures 잔고 (DB 저장 없음)

---

## 데이터 모델

### Account
```python
# @FEAT:account-management @COMP:model @TYPE:core
class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    exchange = db.Column(db.String(50), nullable=False)
    public_api = db.Column(db.Text, nullable=False)  # Fernet 암호화 (AES-128-CTR + HMAC)
    secret_api = db.Column(db.Text, nullable=False)  # Fernet 암호화 (AES-128-CTR + HMAC)
    passphrase = db.Column(db.Text, nullable=True)
    is_testnet = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 증권 전용 필드
    account_type = db.Column(db.String(20), default='CRYPTO', nullable=False)
    _securities_config = db.Column('securities_config', db.Text, nullable=True)  # 암호화된 JSON
    _access_token = db.Column('access_token', db.Text, nullable=True)  # OAuth 토큰 (암호화)
    token_expires_at = db.Column(db.DateTime, nullable=True)

    # 관계
    strategy_accounts = db.relationship('StrategyAccount', cascade='all, delete-orphan')
    daily_summaries = db.relationship('DailyAccountSummary', cascade='all, delete-orphan')

    # 복호화 프로퍼티 (캐싱 적용)
    @property
    def api_key(self) -> str:
        """거래소 클라이언트에 전달할 API 키 (캐싱 적용)"""
        return self._get_cached_decrypted_value("api_key", self.public_api)

    @property
    def api_secret(self) -> str:
        """거래소 클라이언트에 전달할 API 시크릿 (캐싱 적용)"""
        return self._get_cached_decrypted_value("api_secret", self.secret_api)

    @property
    def securities_config(self) -> dict:
        """복호화된 증권 설정 (딕셔너리)"""
        # 암호화된 JSON 문자열 복호화 및 파싱

    @property
    def access_token(self) -> str:
        """복호화된 OAuth 토큰"""
        # 암호화된 토큰 복호화
```

### DailyAccountSummary
```python
# @FEAT:account-management @COMP:model @TYPE:core
class DailyAccountSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    date = db.Column(db.Date, nullable=False)
    starting_balance = db.Column(db.Float, default=0.0)
    ending_balance = db.Column(db.Float, default=0.0)
    spot_balance = db.Column(db.Float, default=0.0)
    futures_balance = db.Column(db.Float, default=0.0)
    total_pnl = db.Column(db.Float, default=0.0)
    realized_pnl = db.Column(db.Float, default=0.0)
    unrealized_pnl = db.Column(db.Float, default=0.0)
    # 거래 통계: total_trades, winning_trades, losing_trades, win_rate
    # 리스크: max_drawdown, total_volume, total_fees
```

---

## 보안 세부사항

### 1. API 키 암호화
```python
# 저장 시
encrypted_api_key = encrypt_value(plain_api_key)  # Fernet (AES-128-CTR + HMAC-SHA256)
account.public_api = encrypted_api_key

# 조회 시 (캐싱)
decrypted_key = account.api_key  # @property로 자동 복호화 + 클래스 레벨 캐싱
```

### 2. 캐시 관리
- **구조**: 클래스 레벨 `_decrypted_api_cache` (커스텀 LRU 구현, 최대 1000개)
- **키 형식**: `{field_name}_{account_id}_{updated_at_timestamp}` (예: `api_key_1_1234567890.0`)
- **무효화**: API 키 변경 시 자동 무효화 (`Account.clear_cache(account_id)`)
- **스레드 안전**: `threading.Lock()` 사용
- **성능**: 반복 조회 시 복호화 연산 생략

### 3. 레거시 감지
```python
if is_likely_legacy_hash(account.public_api):
    return False, '이 계좌는 레거시 형식입니다. 계좌 정보를 다시 저장해 주세요.'
```
**배경**: 과거 Werkzeug 해시 방식 API 키 존재, 복호화 불가

---

## 의존성

### 1. exchange-integration (`@DEPS:exchange-integration`)
```python
# 잔고 조회
balance_result = exchange_service.fetch_balance(account, market_type)

# 캐시 무효화
exchange_service.invalidate_account_cache(account.id)
```

### 2. encryption
```python
from app.security.encryption import encrypt_value, decrypt_value, is_likely_legacy_hash
```

---

## 설계 결정

### 1. 물리 삭제 vs 소프트 삭제
**선택**: 물리 삭제 (CASCADE)
**이유**:
- 계좌 삭제는 드문 이벤트 (복구 필요성 낮음)
- 연관 데이터가 많아 소프트 삭제 시 쿼리 복잡도 증가
- 암호화된 API 키는 보안상 영구 보관 불필요

### 2. API 키 캐싱
**선택**: 클래스 레벨 커스텀 LRU 캐시
**이유**:
- 복호화 연산은 CPU 집약적 (Fernet 암호화)
- 주문 실행 시 반복 조회 발생 (성능 병목)
- 캐시 무효화 시점 명확 (API 키 변경 시만)
- `updated_at` 타임스탬프 기반 캐시 키로 자동 무효화

### 3. 잔고 스냅샷 자동 저장
**선택**: 계좌 생성/연결 테스트 시 자동 저장
**이유**:
- 일일 잔고 추이 분석 필요 (성과 추적)
- 거래소 API 호출 최소화 (이미 조회한 데이터 재활용)
- 사용자가 직접 요청한 시점 = 정확한 스냅샷 타이밍

---

## Known Issues

### 1. Variable Shadowing 방지 (security.py:634)
**이상한 점**: `update_account` 메서드에서 캐시 무효화 시 `Account.clear_cache()` 직접 호출
**이유**: 함수 내 조건부 `from app.models import Account` import 시 Python이 `Account`를 지역 변수로 인식하여 UnboundLocalError 발생. 모듈 레벨 import만 사용하여 회피.
**참고**: `docs/decisions/004-python-variable-shadowing-prevention.md`

### 2. Graceful Degradation - 환율 조회 실패 (Phase 2)
**처리 방식**: 환율 조회 실패 시 국내 계좌의 KRW 잔고를 그대로 표시
**이유**: USDT/KRW 환율은 보조 정보이므로, 환율 조회 실패가 전체 계좌 목록 조회를 실패하게 해서는 안 됨
**로직**:
- 환율 조회 실패 → `conversion_error: "환율 조회 실패"` 설정, KRW 원화 표시
- 환율이 0 이하 → `conversion_error: "환율 데이터 이상"` 설정, KRW 원화 표시
- 각 개별 계정 변환 실패해도 다른 계정 처리는 계속

---

## 관련 문서
- [거래소 통합](./exchange-integration.md)
- [전략 관리](./strategy-management.md)
- [아키텍처 개요](../ARCHITECTURE.md)
- [Variable Shadowing 예방 가이드](../decisions/004-python-variable-shadowing-prevention.md) (신규)

---

*Last Updated: 2025-10-30*
