# FastAPI Trading Bot Server

FastAPI 기반 비동기 암호화폐 거래 시스템 (Flask 리팩토링 버전)

## 프로젝트 개요

이 프로젝트는 기존 Flask 기반 거래 시스템을 FastAPI로 리팩토링한 버전입니다.
모든 I/O 작업을 async/await로 처리하여 높은 성능과 확장성을 제공합니다.

### 주요 개선사항

- ⚡ **비동기 I/O**: 모든 DB, HTTP, 거래소 API 호출을 비동기 처리
- 🚀 **최저 레이턴시**: MARKET/CANCEL 주문 처리 시간 <100ms 목표
- 🛡️ **고아 주문 방지**: Cancel Queue 시스템으로 주문 누락 완전 차단
- 📊 **전략별 격리**: 독립 트랜잭션으로 계정간 영향 차단
- 🔍 **무손실 보장**: 전략별 주문 로그로 감사 추적

## 기술 스택

- **FastAPI** 0.104+ - 비동기 웹 프레임워크
- **SQLAlchemy** 2.0 - 비동기 ORM
- **asyncpg** - PostgreSQL 비동기 드라이버
- **Alembic** - 데이터베이스 마이그레이션
- **Pydantic** 2.0 - 데이터 검증 및 설정
- **httpx** - 비동기 HTTP 클라이언트

## 빠른 시작

### 1. 의존성 설치

```bash
cd web_fastapi_server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 환경 설정

```bash
cp .env.example .env
# .env 파일을 열어 설정 값 수정
```

### 3. 데이터베이스 마이그레이션

```bash
# 마이그레이션 적용
alembic upgrade head
```

### 4. 서버 실행

```bash
# 개발 모드
uvicorn app.main:app --reload --port 8000

# 프로덕션 모드
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. API 문서 확인

브라우저에서 다음 URL 접속:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 엔드포인트

### 기본 엔드포인트

#### GET `/`
루트 엔드포인트 - 서버 상태 확인
```json
{
  "message": "Welcome to FastAPI Trading Bot API",
  "version": "1.0.0-alpha",
  "docs": "/docs",
  "status": "healthy",
  "environment": "development"
}
```

#### GET `/health`
헬스 체크 엔드포인트 - 서비스 상태 확인
```json
{
  "status": "healthy",
  "environment": "development",
  "database": "connected"
}
```

#### GET `/ping`
간단한 핑 엔드포인트 - 서버 응답 테스트
```json
{
  "message": "pong"
}
```

### Cancel Queue 엔드포인트 (Phase 2)

#### POST `/api/v1/cancel-queue/orders/{order_id}/cancel`
주문 취소 요청
- **PENDING** 주문: Cancel Queue에 추가 → 202 Accepted
- **OPEN** 주문: 즉시 거래소 취소 → 200 OK

**응답 예시 (PENDING)**:
```json
{
  "message": "Cancel request added to queue",
  "order_id": 123,
  "status": "queued",
  "cancel_queue_id": 45,
  "immediate": false
}
```

#### GET `/api/v1/cancel-queue`
Cancel Queue 목록 조회 (관리자용)
- 쿼리 파라미터: `status`, `limit`, `offset`

#### GET `/api/v1/cancel-queue/{cancel_id}`
Cancel Queue 개별 조회

#### DELETE `/api/v1/cancel-queue/{cancel_id}`
Cancel Queue 항목 삭제 (관리자용)

## 프로젝트 구조

```
web_fastapi_server/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 앱 진입점
│   ├── config.py            # 환경 설정 (Pydantic Settings)
│   ├── dependencies.py      # 의존성 주입
│   │
│   ├── core/                # 핵심 모듈
│   │   ├── exceptions.py    # 커스텀 예외 (AppException, DatabaseException 등)
│   │   └── middleware.py    # 미들웨어 (CORS, Logging, Exception Handling)
│   │
│   ├── db/                  # 데이터베이스
│   │   ├── base.py          # SQLAlchemy Base 클래스
│   │   └── session.py       # 비동기 세션 관리 (AsyncEngine, AsyncSession)
│   │
│   ├── models/              # SQLAlchemy 모델
│   │   ├── cancel_queue.py          # 취소 대기열 모델
│   │   └── strategy_order_log.py    # 전략별 주문 로그 모델
│   │
│   ├── api/                 # API 라우터 (Phase 2+)
│   │   └── v1/
│   │
│   ├── schemas/             # Pydantic 스키마 (Phase 2+)
│   ├── services/            # 비즈니스 로직 (Phase 2+)
│   ├── exchanges/           # 거래소 어댑터 (Phase 3+)
│   └── tasks/               # 백그라운드 작업 (Phase 6+)
│
├── alembic/                 # 마이그레이션 스크립트
│   ├── env.py               # 비동기 마이그레이션 설정
│   └── versions/            # 마이그레이션 파일
│       └── d35d6b140919_*.py
│
├── tests/                   # 테스트 코드
│   ├── conftest.py          # pytest 설정 및 fixtures
│   ├── test_config.py       # 설정 테스트
│   ├── test_models.py       # 모델 테스트
│   ├── test_db_connection.py   # DB 연결 테스트
│   └── test_app_startup.py     # 앱 시작 테스트
│
├── requirements.txt
├── .env.example
└── README.md
```

## 아키텍처

### 비동기 처리 흐름

```
HTTP Request → FastAPI App → Middleware (CORS, Logging)
                ↓
            Route Handler (async)
                ↓
            Service Layer (async)
                ↓
            Database (AsyncSession via asyncpg)
                ↓
            HTTP Response
```

### 데이터베이스 연결 관리

- **AsyncEngine**: 비동기 DB 엔진, 커넥션 풀 관리
- **AsyncSession**: 비동기 세션, 트랜잭션 관리
- **get_db()**: FastAPI 의존성 주입으로 세션 제공 및 자동 정리

### 설정 관리

- **Pydantic Settings**: 타입 안전한 환경 변수 로딩
- **Field Validators**: 설정 값 자동 검증 및 변환
- **Environment Isolation**: .env 파일로 환경별 설정 분리

## 새로운 테이블

### cancel_queue (취소 대기열)

PENDING 상태 주문의 취소 요청을 추적하여 고아 주문을 방지합니다.

**필드:**
- `order_id`: 취소할 주문 ID
- `strategy_id`: 전략 ID
- `account_id`: 계정 ID
- `retry_count`: 재시도 횟수
- `status`: PENDING, PROCESSING, SUCCESS, FAILED

### strategy_order_logs (전략별 주문 로그)

전략 단위로 주문 실행 결과를 추적하여 감사 로그를 제공합니다.

**필드:**
- `strategy_id`: 전략 ID
- `execution_results`: 계정별 실행 결과 (JSON)
- `total_accounts`: 전체 계정 수
- `successful_accounts`: 성공한 계정 수
- `failed_accounts`: 실패한 계정 수

## 개발 가이드

### 테스트 실행

```bash
# 모든 테스트 실행
pytest

# 커버리지 포함
pytest --cov=app --cov-report=html

# 특정 테스트만
pytest tests/test_models.py
```

### 코드 포맷팅

```bash
# Black으로 자동 포맷팅
black app/ tests/

# Flake8으로 린팅
flake8 app/ tests/

# MyPy로 타입 체크
mypy app/
```

### 마이그레이션 생성

```bash
# 자동 마이그레이션 생성
alembic revision --autogenerate -m "Add new table"

# 수동 마이그레이션 생성
alembic revision -m "Manual migration"

# 마이그레이션 적용
alembic upgrade head

# 마이그레이션 되돌리기
alembic downgrade -1
```

## Phase 구성

### Phase 1: 비동기 인프라 구축 ✅
- FastAPI 프로젝트 초기화
- SQLAlchemy 2.0 비동기 설정
- 새로운 테이블 (cancel_queue, strategy_order_logs)

### Phase 2: 취소 대기열 시스템 ✅
- PENDING 주문 취소 처리
- 재시도 메커니즘 (exponential backoff)
- 백그라운드 작업
- Cancel Queue API 엔드포인트
- Mock Exchange Service

### Phase 3: 비동기 거래소 어댑터 ✅ (현재)
- Binance, Bybit, Upbit 비동기 구현
- httpx 기반 HTTP 클라이언트
- 에러 처리 및 재시도 (500 에러 포함)
- Rate Limiting (거래소별)
- 통일된 데이터 형식

### Phase 4: 웹훅 처리 엔드포인트 (예정)
- MARKET/CANCEL vs Limit/Stop 분기
- 최저 레이턴시 최적화
- 백그라운드 DB 저장

### Phase 5: 전략별 무손실 주문 실행 (예정)
- 전략의 모든 계정에 독립 실행
- 격리된 트랜잭션
- 실행 결과 로그

### Phase 6: 백그라운드 작업 (예정)
- 주문 상태 동기화
- Cancel Queue 처리
- 고아 주문 정리

### Phase 7: WebUI 통합 (예정)
- 기존 React 앱 통합
- Jinja2 템플릿 지원
- 정적 파일 서빙

## 문서

- **[모델 문서](docs/MODELS.md)**: CancelQueue, StrategyOrderLog 상세 API
- **[설정 문서](docs/CONFIGURATION.md)**: 환경 변수 상세 설명 및 사용법
- **[Cancel Queue 문서](docs/CANCEL_QUEUE.md)**: Cancel Queue 시스템 상세 가이드 (Phase 2)
- **[거래소 어댑터 문서](docs/EXCHANGES.md)**: Binance, Bybit, Upbit 어댑터 가이드 (Phase 3)
- **[API 문서](http://localhost:8000/docs)**: Swagger UI (서버 실행 후)

## 환경 변수

주요 환경 변수 설명:

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 연결 URL | `postgresql+asyncpg://trader:password@localhost:5432/trading_system` |
| `REDIS_URL` | Redis 연결 URL | `redis://localhost:6379/0` |
| `DB_POOL_SIZE` | DB 커넥션 풀 크기 | `20` |
| `MARKET_ORDER_TIMEOUT` | MARKET 주문 타임아웃 (초) | `10` |
| `CANCEL_QUEUE_INTERVAL` | Cancel Queue 처리 간격 (초) | `10` |
| `MAX_CANCEL_RETRIES` | 최대 취소 재시도 횟수 | `5` |
| `BINANCE_API_KEY` | Binance API Key | (Phase 3) |
| `BINANCE_API_SECRET` | Binance API Secret | (Phase 3) |
| `BYBIT_API_KEY` | Bybit API Key | (Phase 3) |
| `BYBIT_API_SECRET` | Bybit API Secret | (Phase 3) |
| `UPBIT_API_KEY` | Upbit Access Key | (Phase 3) |
| `UPBIT_API_SECRET` | Upbit Secret Key | (Phase 3) |
| `EXCHANGE_TIMEOUT` | 거래소 API 타임아웃 (초) | `30` |
| `EXCHANGE_MAX_RETRIES` | 거래소 API 최대 재시도 | `3` |
| `USE_MOCK_EXCHANGE` | Mock Exchange 사용 여부 | `true` |

## 문제 해결

### DB 연결 실패
```bash
# PostgreSQL 실행 확인
docker-compose ps postgres

# DB URL 확인
echo $DATABASE_URL
```

### 마이그레이션 오류
```bash
# 현재 버전 확인
alembic current

# 마이그레이션 이력 확인
alembic history

# 강제 버전 설정 (주의)
alembic stamp head
```

### 포트 충돌
```bash
# 8000 포트 사용 프로세스 확인
lsof -i :8000

# 다른 포트로 실행
uvicorn app.main:app --port 8001
```

## 기여 가이드

1. 이 프로젝트는 `refactor/fastapi-main` 브랜치에서 관리됩니다
2. 각 Phase는 별도 feature 브랜치에서 작업 후 머지합니다
3. 모든 코드는 테스트와 문서화가 필수입니다
4. Black, Flake8, MyPy를 통과해야 합니다

## 라이선스

이 프로젝트는 교육 및 연구 목적으로 제공됩니다.

---

**최종 업데이트**: 2025-10-31
**버전**: 1.0.0-alpha (Phase 3)
**문의**: FastAPI 리팩토링 프로젝트
