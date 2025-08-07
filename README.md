# 암호화폐 자동 거래 시스템

Flask 기반의 암호화폐 자동 거래 시스템으로, 다수의 거래소 계정을 통합 관리하고 웹훅 시그널을 통한 자동 거래를 지원합니다.

## 주요 기능

- 🏦 **다중 거래소 지원**: Binance, Bybit, OKX
- 🤖 **자동 거래**: 웹훅 시그널 기반 자동 주문 실행
- 📊 **실시간 모니터링**: WebSocket을 통한 실시간 가격 및 포지션 업데이트
- 💰 **자본 관리**: 전략별 자본 할당 및 리스크 관리
- 👥 **다중 사용자**: 사용자별 독립적인 계정 및 전략 관리
- 📱 **Telegram 알림**: 거래 실행 및 일일 리포트 알림
- 🔒 **보안**: API 키 암호화, CSRF 보호, 안전한 인증

## 🚀 처음 시작하기 (초보자 가이드)

### 사전 준비사항

#### 1. 필수 소프트웨어 설치
- **Git**: [https://git-scm.com/downloads](https://git-scm.com/downloads)
- **Docker Desktop**: 
  - Windows: [Docker Desktop for Windows](https://docs.docker.com/desktop/windows/install/)
  - Mac: [Docker Desktop for Mac](https://docs.docker.com/desktop/mac/install/)
  - Linux: [Docker Engine](https://docs.docker.com/engine/install/)
- **Python 3.8+**: [https://www.python.org/downloads/](https://www.python.org/downloads/)

#### 2. Docker Desktop 설정 (Windows/Mac)
1. Docker Desktop 설치 후 실행
2. Settings → Resources → Advanced
3. Memory: 최소 4GB 할당
4. CPUs: 최소 2개 할당
5. Apply & Restart 클릭

### 📦 설치 단계별 가이드

#### Step 1: 프로젝트 다운로드
```bash
# 터미널(Mac/Linux) 또는 PowerShell(Windows) 열기
# 원하는 디렉토리로 이동 후 실행

git clone https://github.com/binee108/crypto-trading-web-service.git
cd webserver
```

#### Step 2: 환경 설정
```bash
# 환경별 설정 파일 선택
# 개발 환경
cp config/env.development.example .env
# 또는 스테이징 환경
cp config/env.staging.example .env
# 또는 프로덕션 환경
cp config/env.production.example .env

# .env 파일 편집 (필수 설정)
# Windows: notepad .env
# Mac/Linux: nano .env 또는 vi .env
```

**.env 파일 필수 설정 항목:**
```env
# 기본 설정
SECRET_KEY=your-secret-key-here-change-this
DATABASE_URL=postgresql://trader:password123@localhost:5432/trading_system

# Telegram 설정 (선택사항)
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id

# 보안 설정
FLASK_ENV=production
DEBUG=False
```

#### Step 3: Docker Compose로 시스템 시작
```bash
# Docker Compose로 전체 시스템 시작
docker-compose up -d

# 또는 통합 스크립트 사용 (권장)
python run.py start
```

#### Step 4: 초기 설정 확인
```bash
# 시스템 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs -f

# 데이터베이스 초기화 확인
docker-compose exec app flask db upgrade
docker-compose exec app python init_db.py
```

#### Step 5: 웹 브라우저로 접속
1. 브라우저 열기
2. `https://localhost` 접속 (HTTPS)
3. 보안 경고 표시 시:
   - Chrome: "고급" → "localhost(안전하지 않음)으로 이동" 클릭
   - Firefox: "고급" → "위험을 감수하고 계속" 클릭
   - Safari: "자세한 정보 보기" → "웹 사이트 방문" 클릭

#### Step 6: 첫 로그인
- **Username**: `admin`
- **Password**: `admin123`
- ⚠️ **중요**: 첫 로그인 후 즉시 비밀번호 변경!

## 🐳 Docker Compose 상세 설명

### docker-compose.yml 구조
```yaml
version: '3.8'

services:
  # PostgreSQL 데이터베이스
  postgres:
    image: postgres:13
    environment:
      POSTGRES_DB: trading_db
      POSTGRES_USER: trading
      POSTGRES_PASSWORD: trading123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  # Flask 웹 애플리케이션
  app:
    build: .
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql://trading:trading123@postgres:5432/trading_db
    volumes:
      - ./web_server:/app/web_server
      - ./logs:/app/logs
    ports:
      - "443:443"      # HTTPS
      - "5001:5001"    # HTTP
    command: python app.py

volumes:
  postgres_data:  # 데이터 영속성
```

### Docker 명령어 모음

#### 기본 관리
```bash
# 시작
docker-compose up -d

# 중지
docker-compose stop

# 재시작
docker-compose restart

# 완전 종료 및 제거
docker-compose down

# 데이터까지 완전 삭제
docker-compose down -v
```

#### 로그 및 모니터링
```bash
# 전체 로그
docker-compose logs

# 실시간 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f app
docker-compose logs -f postgres

# 컨테이너 상태
docker-compose ps

# 리소스 사용량
docker stats
```

#### 디버깅 및 관리
```bash
# 컨테이너 내부 접속
docker-compose exec app bash
docker-compose exec postgres psql -U trading -d trading_db

# 데이터베이스 백업
docker-compose exec postgres pg_dump -U trading trading_db > backup.sql

# 데이터베이스 복원
docker-compose exec -T postgres psql -U trading trading_db < backup.sql

# 이미지 다시 빌드
docker-compose build --no-cache

# 컨테이너 재생성
docker-compose up -d --force-recreate
```

## 📋 통합 실행 스크립트 (run.py)

### 모든 OS 지원 명령어
```bash
# 시스템 관리
python run.py start       # 시작
python run.py stop        # 중지  
python run.py restart     # 재시작
python run.py status      # 상태 확인

# 로그 관리
python run.py logs        # 로그 확인
python run.py logs -f     # 실시간 로그

# 데이터 관리
python run.py backup      # DB 백업
python run.py restore     # DB 복원
python run.py clean       # 완전 초기화

# 개발 도구
python run.py shell       # Python 쉘
python run.py db-shell    # DB 쉘
```

## 수동 설치 (Python 환경)

### 요구사항
- Python 3.8+
- PostgreSQL (필수)

### 설치
```bash
# 프로젝트 클론
git clone https://github.com/binee108/crypto-trading-web-service.git
cd webserver

# 가상환경 설정
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp env.example .env
# .env 파일을 편집하여 필요한 설정 입력

# 데이터베이스 초기화
flask db upgrade
python init_db.py

# 서버 실행
# HTTPS 서비스 (443 포트, 기본값)
python app.py

# HTTP 서비스로 실행하려면
ENABLE_SSL=false python app.py
```

### 접속 방법
- **HTTPS (기본)**: https://localhost (또는 https://서버IP)
- **HTTP (SSL 비활성화시)**: http://localhost:5001

### 기본 로그인 정보
- Username: `admin`
- Password: `admin123`
- ⚠️ **첫 로그인 후 반드시 비밀번호를 변경하세요!**

## 🎯 Docker 환경의 장점

### 간편한 설치 및 관리
- **원클릭 실행**: 복잡한 설정 없이 바로 시작
- **환경 일관성**: 개발/스테이징/프로덕션 환경 동일
- **의존성 자동 관리**: Python, PostgreSQL, 라이브러리 자동 설치
- **버전 관리**: 모든 컴포넌트 버전 고정

### 안정성 및 보안
- **격리된 환경**: 호스트 시스템과 완전 분리
- **데이터 영속성**: Docker 볼륨으로 안전한 데이터 보존
- **자동 복구**: 컨테이너 재시작 정책
- **네트워크 격리**: 내부 네트워크 통신 보안

### 확장성
- **수평 확장**: 컨테이너 복제로 쉬운 스케일링
- **로드 밸런싱**: 여러 인스턴스 실행 가능
- **마이크로서비스**: 서비스별 독립 배포

## 🔧 문제 해결 가이드

### Docker 관련 문제

#### 1. Docker 서비스가 실행되지 않음
```bash
# Docker 상태 확인
docker version

# Docker 서비스 시작 (Linux)
sudo systemctl start docker

# Docker Desktop 재시작 (Windows/Mac)
# Docker Desktop 앱 재시작
```

#### 2. 포트 충돌 오류
```bash
# 사용 중인 포트 확인
# Linux/Mac
sudo lsof -i :443
sudo lsof -i :5432

# Windows
netstat -ano | findstr :443
netstat -ano | findstr :5432

# 해결 방법: docker-compose.yml에서 포트 변경
# 예: 443:443 → 8443:443
```

#### 3. 메모리 부족 오류
- Docker Desktop → Settings → Resources
- Memory: 6GB 이상 할당
- Swap: 2GB 이상 할당

#### 4. 권한 오류 (Linux)
```bash
# Docker 그룹에 사용자 추가
sudo usermod -aG docker $USER

# 로그아웃 후 다시 로그인
# 또는
newgrp docker
```

### 데이터베이스 문제

#### 1. 연결 실패
```bash
# PostgreSQL 컨테이너 상태 확인
docker-compose ps postgres

# 로그 확인
docker-compose logs postgres

# 데이터베이스 재시작
docker-compose restart postgres
```

#### 2. 마이그레이션 오류
```bash
# 데이터베이스 초기화
docker-compose exec app flask db init
docker-compose exec app flask db migrate
docker-compose exec app flask db upgrade

# 완전 초기화
docker-compose down -v
docker-compose up -d
```

### SSL/HTTPS 문제

#### 브라우저 보안 경고
각 브라우저별 해결 방법:

**Chrome**
1. 경고 화면에서 아무 곳이나 클릭
2. `thisisunsafe` 타이핑 (화면에 표시 안됨)
3. 자동으로 페이지 접속

**Firefox**
1. "고급" 클릭
2. "위험을 감수하고 계속" 클릭

**Safari**
1. "자세한 정보 보기" 클릭
2. "이 웹사이트 방문" 클릭
3. 시스템 비밀번호 입력

### 일반적인 오류 메시지

#### "Cannot connect to Docker daemon"
```bash
# Docker 서비스 확인
docker info

# Docker Desktop 실행 확인 (Windows/Mac)
# Linux: Docker 서비스 시작
sudo systemctl start docker
```

#### "No space left on device"
```bash
# Docker 정리
docker system prune -a

# 볼륨 정리 (주의: 데이터 삭제)
docker volume prune
```

#### "Container name already in use"
```bash
# 기존 컨테이너 제거
docker-compose down
docker-compose up -d
```

## 프로젝트 구조 (새로운 깔끔한 구조)

```
webserver/                 # 프로젝트 루트
├── run.py                 # 🚀 통합 실행 스크립트 (크로스 플랫폼)
├── docker-compose.yml     # Docker 구성
├── README.md              # 메인 문서
├── config/                # ⚙️ 설정 파일들
│   ├── config.py         # 애플리케이션 설정
│   ├── env.example       # 환경 변수 템플릿
│   └── Dockerfile        # Docker 이미지 빌드
├── scripts/               # 📜 실행 스크립트들
│   ├── app.py            # Flask 앱 실행
│   ├── init_db.py        # DB 초기화
│   ├── start.sh          # Linux/Mac 시작 (레거시)
│   └── stop.sh           # Linux/Mac 중지 (레거시)
└── web_server/            # 🌐 메인 웹서버 코드
    ├── app/              # Flask 애플리케이션
    │   ├── routes/       # API 엔드포인트
    │   ├── services/     # 비즈니스 로직
    │   ├── static/       # CSS, JS, 이미지
    │   └── templates/    # HTML 템플릿
    ├── docs/             # 프로젝트 문서
    ├── migrations/       # DB 마이그레이션
    ├── requirements.txt  # Python 의존성
    ├── certs/           # SSL 인증서
    └── logs/            # 로그 파일
```

### 새로운 구조의 장점
- 🎯 **극도로 깔끔한 루트**: 실행 스크립트와 필수 파일만
- 📁 **논리적 분리**: 설정, 스크립트, 웹서버 코드 독립
- 🚀 **통합 관리**: 하나의 run.py로 모든 OS 지원
- 🔧 **유지보수 용이**: 기능별 디렉토리 분리

## 문서

상세한 문서는 `docs/` 디렉토리에서 확인할 수 있습니다:

- [프로젝트 개요](docs/PROJECT_OVERVIEW.md) - 시스템 전체 개요
- [아키텍처](docs/ARCHITECTURE.md) - 시스템 아키텍처 및 설계
- [설치 가이드](docs/SETUP_GUIDE.md) - 상세한 설치 및 설정 방법
- [API 문서](docs/POSITIONS_AND_ORDERS_API.md) - API 엔드포인트 문서
- [데이터베이스 스키마](docs/DATABASE_SCHEMA.md) - 데이터베이스 구조

## 📖 사용 방법 상세 가이드

### 1. 거래소 계정 등록
1. 로그인 후 "계정 관리" 메뉴 접속
2. "새 계정 추가" 클릭
3. 거래소 선택 및 API 키 입력
   - API 키 생성 시 **거래** 및 **읽기** 권한만 부여
   - **출금 권한은 절대 부여하지 않음**
   - IP 화이트리스트 설정 권장
4. 연결 테스트로 정상 작동 확인

### 2. 전략 생성 및 설정
1. "전략 관리" 메뉴 접속
2. "새 전략 추가" 클릭
3. 전략 정보 입력:
   - **전략 이름**: 식별 가능한 이름
   - **그룹명**: 전략 분류용
   - **시장 타입**: Spot/Futures 선택
   - **웹훅 키**: 자동 생성됨 (복사해두기)

### 3. 전략-계정 연결
1. 생성된 전략의 "계정 연결" 클릭
2. 연결할 거래소 계정 선택
3. 거래 설정:
   - **레버리지**: 1-125x (Futures만)
   - **가중치**: 자본 배분 비율
   - **최대 포지션**: 동시 보유 가능 포지션 수
4. 저장

### 4. 웹훅 설정 (TradingView 등)
**웹훅 URL 형식:**
```
https://your-domain.com/webhook/{strategy_webhook_key}
```

**웹훅 페이로드 예시:**

#### 시장가 주문
```json
{
    "symbol": "BTCUSDT",
    "action": "BUY",
    "quantity": 0.001
}
```

#### 지정가 주문
```json
{
    "symbol": "BTCUSDT",
    "action": "SELL",
    "quantity": 0.001,
    "price": "limit:45000"
}
```

#### 포지션 청산
```json
{
    "symbol": "BTCUSDT",
    "action": "CLOSE",
    "quantity": "all"
}
```

#### 비율 기반 주문
```json
{
    "symbol": "ETHUSDT",
    "action": "BUY",
    "quantity": "10%",  // 자본의 10%
    "leverage": 10
}
```

### 5. 실시간 모니터링
- **대시보드**: 전체 계정 현황, 총 자산, 일일 손익
- **포지션 관리**: 
  - 실시간 가격 업데이트 (WebSocket)
  - 미실현 손익 자동 계산
  - 원클릭 포지션 청산
- **주문 관리**:
  - 미체결 주문 실시간 추적
  - 일괄 주문 취소 기능
- **거래 내역**: 체결 내역 및 수수료 분석

## 🌍 환경별 설정

### 개발 환경
```bash
# .env.development
FLASK_ENV=development
DEBUG=True
DATABASE_URL=postgresql://trader:password123@localhost:5432/trading_dev
ENABLE_SSL=False
```

### 스테이징 환경
```bash
# .env.staging
FLASK_ENV=staging
DEBUG=False
DATABASE_URL=postgresql://user:pass@localhost/staging_db
ENABLE_SSL=True
```

### 프로덕션 환경
```bash
# .env.production
FLASK_ENV=production
DEBUG=False
DATABASE_URL=postgresql://user:pass@localhost/prod_db
ENABLE_SSL=True
SECRET_KEY=<강력한_랜덤_키>

# 추가 보안 설정
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Strict
PERMANENT_SESSION_LIFETIME=3600
```

### 환경별 Docker Compose
```bash
# 개발 환경
docker-compose -f docker-compose.dev.yml up

# 스테이징 환경
docker-compose -f docker-compose.staging.yml up

# 프로덕션 환경
docker-compose -f docker-compose.prod.yml up
```

## 보안 주의사항

1. **API 키 보안**
   - 거래소에서 출금 권한은 비활성화
   - IP 화이트리스트 설정 권장
   - 읽기/거래 권한만 부여

2. **시스템 보안**
   - 강력한 비밀번호 사용 (12자 이상)
   - 프로덕션에서는 HTTPS 필수
   - 정기적인 보안 업데이트

3. **백업**
   - 데이터베이스 정기 백업
   - 설정 파일 백업
   - API 키는 별도 안전한 곳에 보관

## 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 지원 및 문의

- 이슈: [GitHub Issues](https://github.com/your-repo/crypto-trading-system/issues)
- 문서: [프로젝트 Wiki](https://github.com/your-repo/crypto-trading-system/wiki)

## 면책 조항

이 소프트웨어는 교육 및 연구 목적으로 제공됩니다. 실제 거래에 사용할 경우 발생하는 모든 손실에 대해 개발자는 책임지지 않습니다. 암호화폐 거래는 높은 위험을 수반하므로 신중하게 사용하시기 바랍니다.