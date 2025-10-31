# 설정 문서

FastAPI Trading Bot의 환경 설정 상세 문서입니다.

---

## 개요

이 프로젝트는 **Pydantic Settings**를 사용하여 환경 변수를 타입 안전하게 관리합니다.

**파일**: `app/config.py`

---

## 환경 변수

### 데이터베이스 설정

#### `DATABASE_URL` (필수)
PostgreSQL 연결 URL (asyncpg 드라이버 사용)

**형식**: `postgresql+asyncpg://user:password@host:port/database`

**예시**:
```bash
DATABASE_URL=postgresql+asyncpg://trader:password@localhost:5432/trading_system
```

#### `REDIS_URL` (필수)
Redis 연결 URL

**형식**: `redis://host:port/db`

**예시**:
```bash
REDIS_URL=redis://localhost:6379/0
```

#### `DB_POOL_SIZE`
데이터베이스 커넥션 풀 크기

- **타입**: Integer
- **기본값**: 20
- **범위**: 5 ~ 100
- **설명**: 동시 DB 연결 수

**예시**:
```bash
DB_POOL_SIZE=20
```

#### `DB_MAX_OVERFLOW`
커넥션 풀 오버플로우 최대 개수

- **타입**: Integer
- **기본값**: 10
- **범위**: 0 ~ 50
- **설명**: 풀 크기 초과 시 추가로 생성할 수 있는 연결 수

**예시**:
```bash
DB_MAX_OVERFLOW=10
```

#### `DB_POOL_PRE_PING`
커넥션 사용 전 ping 테스트 여부

- **타입**: Boolean
- **기본값**: True
- **설명**: 연결이 살아있는지 확인

**예시**:
```bash
DB_POOL_PRE_PING=true
```

---

### 보안 설정

#### `SECRET_KEY` (필수)
JWT 토큰 서명용 비밀 키

- **타입**: String
- **설명**: 최소 32자 이상 권장

**예시**:
```bash
SECRET_KEY=your-super-secret-key-change-this-in-production-32-chars-minimum
```

**생성 방법**:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### `ALGORITHM`
JWT 알고리즘

- **타입**: String
- **기본값**: HS256
- **허용값**: HS256, HS384, HS512

**예시**:
```bash
ALGORITHM=HS256
```

#### `ACCESS_TOKEN_EXPIRE_MINUTES`
액세스 토큰 만료 시간 (분)

- **타입**: Integer
- **기본값**: 30
- **범위**: 5 ~ 1440 (1일)

**예시**:
```bash
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

---

### 주문 처리 설정

#### `MARKET_ORDER_TIMEOUT`
MARKET 주문 타임아웃 (초)

- **타입**: Integer
- **기본값**: 10
- **범위**: 1 ~ 60
- **설명**: MARKET 주문 실행 최대 대기 시간

**예시**:
```bash
MARKET_ORDER_TIMEOUT=10
```

#### `CANCEL_QUEUE_INTERVAL`
Cancel Queue 처리 간격 (초)

- **타입**: Integer
- **기본값**: 10
- **범위**: 5 ~ 60
- **설명**: 취소 대기열 백그라운드 작업 실행 주기

**예시**:
```bash
CANCEL_QUEUE_INTERVAL=10
```

#### `MAX_CANCEL_RETRIES`
최대 취소 재시도 횟수

- **타입**: Integer
- **기본값**: 5
- **범위**: 1 ~ 10
- **설명**: 취소 실패 시 재시도 최대 횟수

**예시**:
```bash
MAX_CANCEL_RETRIES=5
```

---

### 애플리케이션 설정

#### `ENV`
실행 환경

- **타입**: String
- **기본값**: development
- **허용값**: development, production, test

**예시**:
```bash
ENV=development
```

#### `DEBUG`
디버그 모드

- **타입**: Boolean
- **기본값**: True (development), False (production)
- **설명**: 상세 에러 메시지 및 자동 리로드

**예시**:
```bash
DEBUG=true
```

#### `APP_HOST`
앱 바인딩 호스트

- **타입**: String
- **기본값**: 0.0.0.0

**예시**:
```bash
APP_HOST=0.0.0.0
```

#### `APP_PORT`
앱 바인딩 포트

- **타입**: Integer
- **기본값**: 8000
- **범위**: 1024 ~ 65535

**예시**:
```bash
APP_PORT=8000
```

---

### CORS 설정

#### `CORS_ORIGINS`
허용할 오리진 목록 (쉼표로 구분)

- **타입**: String (자동으로 List로 변환)
- **기본값**: `http://localhost:3000,http://localhost:8000`

**예시**:
```bash
CORS_ORIGINS=http://localhost:3000,http://localhost:8000,https://trading.example.com
```

**Python에서 접근**:
```python
from app.config import settings
print(settings.CORS_ORIGINS)
# ['http://localhost:3000', 'http://localhost:8000', 'https://trading.example.com']
```

#### `CORS_ALLOW_CREDENTIALS`
인증 정보 허용 여부

- **타입**: Boolean
- **기본값**: True

**예시**:
```bash
CORS_ALLOW_CREDENTIALS=true
```

#### `CORS_ALLOW_METHODS`
허용할 HTTP 메서드 (쉼표로 구분)

- **타입**: String (자동으로 List로 변환)
- **기본값**: `*`

**예시**:
```bash
CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,OPTIONS
# 또는
CORS_ALLOW_METHODS=*
```

#### `CORS_ALLOW_HEADERS`
허용할 HTTP 헤더 (쉼표로 구분)

- **타입**: String (자동으로 List로 변환)
- **기본값**: `*`

**예시**:
```bash
CORS_ALLOW_HEADERS=Content-Type,Authorization,X-Requested-With
# 또는
CORS_ALLOW_HEADERS=*
```

---

### 로깅 설정

#### `LOG_LEVEL`
로그 레벨

- **타입**: String
- **기본값**: INFO
- **허용값**: DEBUG, INFO, WARNING, ERROR, CRITICAL

**예시**:
```bash
LOG_LEVEL=INFO
```

**레벨별 설명**:
- **DEBUG**: 상세 디버깅 정보
- **INFO**: 일반 정보
- **WARNING**: 경고 (잠재적 문제)
- **ERROR**: 에러 (작업 실패)
- **CRITICAL**: 심각한 에러 (시스템 장애)

---

## 설정 사용 방법

### Python 코드에서 접근

```python
from app.config import settings

# 데이터베이스 URL
print(settings.DATABASE_URL)

# DB 풀 크기
print(settings.DB_POOL_SIZE)

# 환경
if settings.ENV == "production":
    # 프로덕션 전용 로직
    pass

# CORS 오리진 (자동으로 리스트로 변환됨)
print(settings.CORS_ORIGINS)  # ['http://localhost:3000', ...]
```

### .env 파일 예시

```bash
# Database
DATABASE_URL=postgresql+asyncpg://trader:password@localhost:5432/trading_system
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-super-secret-key-change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Database Performance
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_PRE_PING=true

# Order Processing
MARKET_ORDER_TIMEOUT=10
CANCEL_QUEUE_INTERVAL=10
MAX_CANCEL_RETRIES=5

# Application
ENV=development
DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*

# Logging
LOG_LEVEL=INFO
```

---

## 환경별 설정

### 개발 환경 (.env)

```bash
ENV=development
DEBUG=true
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql+asyncpg://trader:password@localhost:5432/trading_system_dev
```

### 테스트 환경 (.env.test)

```bash
ENV=test
DEBUG=false
LOG_LEVEL=WARNING
DATABASE_URL=postgresql+asyncpg://trader:password@localhost:5432/trading_system_test
```

### 프로덕션 환경 (.env.production)

```bash
ENV=production
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=postgresql+asyncpg://prod_user:strong_password@prod-db:5432/trading_system
SECRET_KEY=<강력한 랜덤 키>
CORS_ORIGINS=https://trading.example.com
```

---

## 검증 (Validation)

Pydantic이 자동으로 다음을 검증합니다:

### 타입 검증
```python
# 올바른 설정
DB_POOL_SIZE=20  # Integer

# 잘못된 설정
DB_POOL_SIZE=abc  # ValidationError 발생
```

### 범위 검증
```python
# 올바른 설정
DB_POOL_SIZE=20  # 5~100 범위 내

# 잘못된 설정
DB_POOL_SIZE=200  # ValidationError: 최대값 100 초과
```

### Enum 검증
```python
# 올바른 설정
ENV=development  # 허용된 값

# 잘못된 설정
ENV=invalid_env  # ValidationError: 허용되지 않은 값
```

---

## 보안 주의사항

### 1. SECRET_KEY 관리
- ❌ 절대 소스 코드에 하드코딩하지 마세요
- ✅ 환경 변수나 비밀 관리 서비스 사용
- ✅ 프로덕션에서는 최소 32자 이상 랜덤 키 사용

### 2. DATABASE_URL 보안
- ❌ 공개 저장소에 커밋하지 마세요
- ✅ .env 파일을 .gitignore에 추가
- ✅ 프로덕션 DB 비밀번호는 강력하게 설정

### 3. CORS 설정
- ❌ 프로덕션에서 `CORS_ORIGINS=*` 사용 금지
- ✅ 특정 도메인만 허용
- ✅ 인증 정보가 필요한 경우에만 `CORS_ALLOW_CREDENTIALS=true`

---

**최종 업데이트**: 2025-10-31
**Phase**: Phase 1 - 비동기 인프라 구축
