# 데이터베이스 스키마 문서

## 개요

암호화폐 자동 거래 시스템의 데이터베이스는 SQLAlchemy ORM을 사용하여 구성되어 있습니다. 개발 환경에서는 SQLite를, 프로덕션 환경에서는 PostgreSQL 또는 MySQL을 사용할 수 있도록 설계되었습니다.

## 테이블 구조

### 1. User (사용자)
사용자 계정 정보를 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 사용자 고유 ID |
| username | String(80) | UNIQUE, NOT NULL | 사용자명 |
| password_hash | String(120) | NOT NULL | bcrypt로 해시된 비밀번호 |
| is_admin | Boolean | DEFAULT FALSE | 관리자 권한 여부 |
| telegram_id | String(50) | NULLABLE | Telegram 사용자 ID |
| last_login | DateTime | NULLABLE | 마지막 로그인 시간 |
| must_change_password | Boolean | DEFAULT FALSE | 비밀번호 변경 필요 여부 |
| created_at | DateTime | DEFAULT NOW | 계정 생성 시간 |

**인덱스**:
- `idx_user_username` on (username)
- `idx_user_telegram_id` on (telegram_id)

### 2. Account (거래소 계정)
거래소 API 연결 정보를 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 계정 고유 ID |
| user_id | Integer | FOREIGN KEY → User.id | 사용자 ID |
| name | String(100) | NOT NULL | 계정 이름 |
| exchange | String(50) | NOT NULL | 거래소 이름 (BINANCE, BYBIT, OKX) |
| api_key | String(255) | NOT NULL | 암호화된 API Key |
| api_secret | String(255) | NOT NULL | 암호화된 API Secret |
| passphrase | String(255) | NULLABLE | OKX용 Passphrase |
| is_active | Boolean | DEFAULT TRUE | 계정 활성화 상태 |
| created_at | DateTime | DEFAULT NOW | 계정 생성 시간 |

**인덱스**:
- `idx_account_user_id` on (user_id)
- `idx_account_exchange` on (exchange)

### 3. Strategy (전략)
거래 전략 정보를 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 전략 고유 ID |
| user_id | Integer | FOREIGN KEY → User.id | 사용자 ID |
| name | String(100) | NOT NULL | 전략 이름 |
| group_name | String(100) | NOT NULL | 전략 그룹명 |
| market_type | String(20) | NOT NULL | 시장 타입 (spot, futures) |
| max_positions | Integer | DEFAULT 5 | 최대 포지션 수 |
| webhook_key | String(100) | UNIQUE | 웹훅 인증 키 |
| is_active | Boolean | DEFAULT TRUE | 전략 활성화 상태 |
| created_at | DateTime | DEFAULT NOW | 전략 생성 시간 |

**인덱스**:
- `idx_strategy_user_id` on (user_id)
- `idx_strategy_webhook_key` on (webhook_key)
- `idx_strategy_group_name` on (group_name)

### 4. StrategyAccount (전략-계정 연결)
전략과 거래소 계정을 연결하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 연결 고유 ID |
| strategy_id | Integer | FOREIGN KEY → Strategy.id | 전략 ID |
| account_id | Integer | FOREIGN KEY → Account.id | 계정 ID |
| weight | Float | DEFAULT 1.0 | 가중치 (자본 배분 비율) |
| leverage | Float | DEFAULT 1.0 | 레버리지 |
| max_symbols | Integer | DEFAULT 10 | 최대 심볼 수 |
| is_active | Boolean | DEFAULT TRUE | 연결 활성화 상태 |

**유니크 제약조건**:
- UNIQUE (strategy_id, account_id)

### 5. StrategyCapital (전략 자본)
전략별 자본 할당 정보를 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 자본 고유 ID |
| strategy_id | Integer | FOREIGN KEY → Strategy.id | 전략 ID |
| total_capital | Float | NOT NULL | 총 할당 자본 |
| used_capital | Float | DEFAULT 0 | 사용 중인 자본 |
| reserved_capital | Float | DEFAULT 0 | 예약된 자본 |
| updated_at | DateTime | DEFAULT NOW | 마지막 업데이트 시간 |

**인덱스**:
- `idx_capital_strategy_id` on (strategy_id)

### 6. StrategyPosition (전략 포지션)
전략별 가상 포지션 정보를 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 포지션 고유 ID |
| strategy_id | Integer | FOREIGN KEY → Strategy.id | 전략 ID |
| symbol | String(50) | NOT NULL | 거래 심볼 |
| direction | String(10) | NOT NULL | 방향 (LONG, SHORT) |
| quantity | Float | NOT NULL | 수량 |
| entry_price | Float | NOT NULL | 진입 가격 |
| current_price | Float | NULLABLE | 현재 가격 |
| unrealized_pnl | Float | DEFAULT 0 | 미실현 손익 |
| realized_pnl | Float | DEFAULT 0 | 실현 손익 |
| is_open | Boolean | DEFAULT TRUE | 포지션 오픈 상태 |
| opened_at | DateTime | DEFAULT NOW | 포지션 오픈 시간 |
| closed_at | DateTime | NULLABLE | 포지션 종료 시간 |
| last_updated | DateTime | DEFAULT NOW | 마지막 업데이트 시간 |

**인덱스**:
- `idx_position_strategy_id` on (strategy_id)
- `idx_position_symbol` on (symbol)
- `idx_position_is_open` on (is_open)

### 7. Trade (거래 내역)
실제 체결된 거래 내역을 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 거래 고유 ID |
| strategy_account_id | Integer | FOREIGN KEY → StrategyAccount.id | 전략-계정 ID |
| strategy_position_id | Integer | FOREIGN KEY → StrategyPosition.id | 전략 포지션 ID |
| exchange_order_id | String(100) | NOT NULL | 거래소 주문 ID |
| symbol | String(50) | NOT NULL | 거래 심볼 |
| side | String(10) | NOT NULL | 매수/매도 (BUY, SELL) |
| quantity | Float | NOT NULL | 수량 |
| price | Float | NOT NULL | 체결 가격 |
| fee | Float | DEFAULT 0 | 수수료 |
| fee_currency | String(20) | NULLABLE | 수수료 통화 |
| realized_pnl | Float | DEFAULT 0 | 실현 손익 |
| market_type | String(20) | NOT NULL | 시장 타입 |
| executed_at | DateTime | DEFAULT NOW | 체결 시간 |

**인덱스**:
- `idx_trade_strategy_account_id` on (strategy_account_id)
- `idx_trade_symbol` on (symbol)
- `idx_trade_executed_at` on (executed_at)

### 8. OpenOrder (미체결 주문)
현재 미체결 상태의 주문을 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 주문 고유 ID |
| strategy_account_id | Integer | FOREIGN KEY → StrategyAccount.id | 전략-계정 ID |
| exchange_order_id | String(100) | UNIQUE, NOT NULL | 거래소 주문 ID |
| symbol | String(50) | NOT NULL | 거래 심볼 |
| side | String(10) | NOT NULL | 매수/매도 |
| order_type | String(20) | NOT NULL | 주문 타입 (LIMIT, MARKET) |
| quantity | Float | NOT NULL | 주문 수량 |
| price | Float | NULLABLE | 주문 가격 |
| filled_quantity | Float | DEFAULT 0 | 체결된 수량 |
| status | String(20) | NOT NULL | 주문 상태 |
| market_type | String(20) | NOT NULL | 시장 타입 |
| created_at | DateTime | DEFAULT NOW | 주문 생성 시간 |
| updated_at | DateTime | DEFAULT NOW | 마지막 업데이트 시간 |

**인덱스**:
- `idx_open_order_strategy_account_id` on (strategy_account_id)
- `idx_open_order_symbol` on (symbol)
- `idx_open_order_status` on (status)

### 9. WebhookLog (웹훅 로그)
웹훅 요청 로그를 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 로그 고유 ID |
| strategy_id | Integer | FOREIGN KEY → Strategy.id | 전략 ID |
| webhook_key | String(100) | NOT NULL | 웹훅 키 |
| request_data | Text | NOT NULL | 요청 데이터 (JSON) |
| response_data | Text | NULLABLE | 응답 데이터 (JSON) |
| status | String(20) | NOT NULL | 처리 상태 |
| error_message | Text | NULLABLE | 오류 메시지 |
| ip_address | String(50) | NULLABLE | 요청 IP 주소 |
| created_at | DateTime | DEFAULT NOW | 로그 생성 시간 |

**인덱스**:
- `idx_webhook_log_strategy_id` on (strategy_id)
- `idx_webhook_log_created_at` on (created_at)

### 10. DailyAccountSummary (일일 계정 요약)
일별 계정 성과를 저장하는 테이블입니다.

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | Integer | PRIMARY KEY | 요약 고유 ID |
| account_id | Integer | FOREIGN KEY → Account.id | 계정 ID |
| date | Date | NOT NULL | 날짜 |
| total_balance | Float | NOT NULL | 총 잔고 |
| available_balance | Float | NOT NULL | 사용 가능 잔고 |
| position_count | Integer | DEFAULT 0 | 포지션 수 |
| total_position_value | Float | DEFAULT 0 | 총 포지션 가치 |
| daily_pnl | Float | DEFAULT 0 | 일일 손익 |
| daily_pnl_percentage | Float | DEFAULT 0 | 일일 수익률 (%) |
| total_trades | Integer | DEFAULT 0 | 일일 거래 수 |
| winning_trades | Integer | DEFAULT 0 | 수익 거래 수 |
| losing_trades | Integer | DEFAULT 0 | 손실 거래 수 |
| created_at | DateTime | DEFAULT NOW | 생성 시간 |

**유니크 제약조건**:
- UNIQUE (account_id, date)

**인덱스**:
- `idx_daily_summary_account_id` on (account_id)
- `idx_daily_summary_date` on (date)

## 관계 다이어그램

```
User (1) ─────┬──── (*) Account
         │    └──── (*) Strategy
         │
         └──── (*) Strategy ────┬──── (*) StrategyAccount ──── (*) Account
                           │    │
                           │    ├──── (*) Trade
                           │    │
                           │    └──── (*) OpenOrder
                           │
                           ├──── (1) StrategyCapital
                           │
                           ├──── (*) StrategyPosition
                           │
                           └──── (*) WebhookLog

Account (1) ──── (*) DailyAccountSummary
```

## 인덱스 전략

### 1. 기본 인덱스
- 모든 Foreign Key에는 자동으로 인덱스 생성
- Primary Key는 기본적으로 클러스터드 인덱스

### 2. 성능 최적화 인덱스
- 자주 조회되는 컬럼에 인덱스 추가
- 복합 인덱스는 쿼리 패턴에 따라 생성

### 3. 인덱스 관리
```sql
-- 인덱스 통계 업데이트 (PostgreSQL)
ANALYZE table_name;

-- 인덱스 재구성 (PostgreSQL)
REINDEX TABLE table_name;
```

## 데이터 정합성

### 1. Foreign Key 제약
- CASCADE DELETE: User 삭제 시 관련 데이터 삭제
- RESTRICT: 참조 데이터가 있으면 삭제 불가

### 2. Check 제약
```sql
-- 예시: 수량은 양수여야 함
CHECK (quantity > 0)

-- 예시: 레버리지는 1 이상
CHECK (leverage >= 1)
```

### 3. 트리거
- `updated_at` 자동 업데이트
- 자본 사용량 자동 계산

## 마이그레이션

### 1. 마이그레이션 생성
```bash
flask db migrate -m "Add new column to User table"
```

### 2. 마이그레이션 적용
```bash
flask db upgrade
```

### 3. 마이그레이션 롤백
```bash
flask db downgrade
```

## 백업 및 복구

### 1. SQLite 백업
```bash
# 데이터베이스 파일 복사
cp instance/trading_system.db backup/trading_system_$(date +%Y%m%d).db
```

### 2. PostgreSQL 백업
```bash
# 전체 백업
pg_dump -U username -d database_name > backup.sql

# 특정 테이블만 백업
pg_dump -U username -d database_name -t table_name > table_backup.sql
```

### 3. 복구
```bash
# PostgreSQL 복구
psql -U username -d database_name < backup.sql
```

## 성능 고려사항

### 1. 쿼리 최적화
- N+1 문제 방지: eager loading 사용
- 불필요한 조인 최소화
- 적절한 인덱스 활용

### 2. 파티셔닝
대용량 데이터 테이블의 경우:
- `Trade`: 월별 파티셔닝
- `WebhookLog`: 월별 파티셔닝
- `DailyAccountSummary`: 연도별 파티셔닝

### 3. 아카이빙
- 오래된 거래 데이터는 별도 테이블로 이동
- 로그 데이터는 주기적으로 정리

## 보안 고려사항

### 1. 암호화
- API 키와 Secret은 암호화하여 저장
- 민감한 데이터는 application level에서 암호화

### 2. 접근 제어
- 데이터베이스 사용자별 권한 분리
- 읽기 전용 사용자 생성

### 3. 감사 로그
- 중요한 변경사항은 로그 테이블에 기록
- 정기적인 감사 로그 검토