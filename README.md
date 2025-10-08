# 암호화폐 자동 거래 시스템

Flask 기반의 암호화폐 자동 거래 시스템으로, 다수의 거래소 계정을 통합 관리하고 웹훅 시그널을 통한 자동 거래를 지원합니다.

## 🆕 최근 업데이트 (2025-10-08)

### 코드 리뷰 반영 및 안정성 개선
- ✅ **Critical 이슈 3개 수정**: market_type 필드 오류, 멀티 Exchange 중복 주문 경고, 배치 주문 검증 강화
- ✅ **Important 이슈 3개 수정**: 공통 필드 폴백 로직 일관성, order_type 사전 검증
- ✅ **멀티 Exchange 중복 경고**: 동일 거래소 계좌 중복 연동 시 WARNING 로그 발행
- ✅ **배치 주문 개선**: 공통 필드 폴백 로직 일관성 확보 (side, price, stop_price, qty_per)

### 배치 주문 포맷 변경 (Breaking Change)
- ⚠️ **공통 필드 상위 레벨 이동**: `symbol`, `currency` 등을 상위로 추출
- 🔄 **우선순위 자동 정렬**: MARKET(1) > CANCEL(2) > LIMIT(3) > STOP(4-5)
- 📋 **폴백 로직**: order 레벨 우선 → 상위 레벨 폴백

### DRY 리팩토링 및 코드 품질 향상
- 🧹 **binance.py 리팩토링**: 120줄 중복 코드 제거 (`_prepare_order_params()` 메서드)
- 📚 **Docstring 향상**: constants.py 커버리지 21% → 94%
- 🔧 **로깅 최적화**: 상세 로그 INFO → DEBUG 레벨 변경

## 주요 기능

- 🏦 **거래소 지원**: Binance, Bybit, Upbit (국내 KRW 마켓)
- 🌐 **멀티 Exchange 지원**: 단일 웹훅으로 여러 거래소 동시 주문 실행
- 🤖 **자동 거래**: 웹훅 시그널 기반 자동 주문 실행
- 📦 **배치 주문**: 여러 주문을 하나의 웹훅으로 동시 실행 (우선순위 자동 정렬)
- 📊 **실시간 모니터링**: WebSocket을 통한 실시간 가격 및 포지션 업데이트
- 💰 **자본 관리**: 전략별 자본 할당 및 리스크 관리
- 📈 **성과 분석**: ROI, 샤프/소르티노 비율, 일일/누적 PnL 추적 및 API 제공
- 👥 **다중 사용자**: 사용자별 독립적인 계정 및 전략 관리
- 📱 **Telegram 알림**: 거래 실행 및 일일 리포트 알림
- 🔒 **보안**: API 키 암호화, CSRF 보호, 안전한 인증

## 🚀 처음 시작하기 (초보자 가이드)

### 📋 사전 준비사항

#### 1. 필수 소프트웨어 설치

##### 🐳 Docker 설치 (필수)
Docker는 이 시스템을 실행하는데 반드시 필요합니다. OS별로 아래 가이드를 따라 설치해주세요.

**Windows 사용자:**
1. [Docker Desktop for Windows](https://docs.docker.com/desktop/windows/install/) 다운로드
2. 시스템 요구사항:
   - Windows 10 64-bit: Pro, Enterprise, Education (Build 16299 이상)
   - Windows 11 64-bit
   - WSL2 Backend 사용 권장
3. 설치 과정:
   ```powershell
   # 1. 다운로드한 Docker Desktop Installer.exe 실행
   # 2. "Enable WSL 2 Features" 옵션 체크
   # 3. 설치 완료 후 시스템 재시작
   
   # 4. PowerShell에서 설치 확인
   docker --version
   docker-compose --version
   ```

**macOS 사용자:**
1. [Docker Desktop for Mac](https://docs.docker.com/desktop/mac/install/) 다운로드
2. 시스템 요구사항:
   - macOS 11 Big Sur 이상
   - Apple Silicon (M1/M2) 또는 Intel 칩 지원
3. 설치 과정:
   ```bash
   # 1. Docker.dmg 다운로드 후 실행
   # 2. Docker 아이콘을 Applications 폴더로 드래그
   # 3. Applications에서 Docker 실행
   
   # 4. 터미널에서 설치 확인
   docker --version
   docker-compose --version
   ```

**Linux 사용자 (Ubuntu/Debian):**
```bash
# 1. 이전 버전 제거
sudo apt-get remove docker docker-engine docker.io containerd runc

# 2. 필수 패키지 설치
sudo apt-get update
sudo apt-get install \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# 3. Docker GPG 키 추가
sudo mkdir -m 0755 -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 4. Docker 저장소 설정
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. Docker Engine 설치
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 6. Docker 서비스 시작
sudo systemctl start docker
sudo systemctl enable docker

# 7. 현재 사용자를 docker 그룹에 추가 (sudo 없이 실행)
sudo usermod -aG docker $USER
newgrp docker

# 8. 설치 확인
docker --version
docker compose version
```

**Linux 사용자 (CentOS/RHEL/Fedora):**
```bash
# 1. 이전 버전 제거
sudo yum remove docker \
                docker-client \
                docker-client-latest \
                docker-common \
                docker-latest \
                docker-latest-logrotate \
                docker-logrotate \
                docker-engine

# 2. 필수 패키지 설치
sudo yum install -y yum-utils

# 3. Docker 저장소 추가
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 4. Docker Engine 설치
sudo yum install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. Docker 서비스 시작
sudo systemctl start docker
sudo systemctl enable docker

# 6. 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER
newgrp docker

# 7. 설치 확인
docker --version
docker compose version
```

##### 🔍 Docker 설치 확인
모든 OS에서 다음 명령어로 Docker가 정상 설치되었는지 확인:
```bash
# Docker 버전 확인
docker --version
# 예상 출력: Docker version 24.0.x, build xxxxxxx

# Docker Compose 버전 확인
docker-compose --version
# 또는
docker compose version
# 예상 출력: Docker Compose version v2.x.x

# Docker 서비스 상태 확인
docker info

# 테스트 컨테이너 실행
docker run hello-world
```

문제가 있다면 아래 "Docker 설치 문제 해결" 섹션을 참조하세요.

##### 기타 필수 소프트웨어
- **Git**: [https://git-scm.com/downloads](https://git-scm.com/downloads)
- **Python 3.8+**: [https://www.python.org/downloads/](https://www.python.org/downloads/)

#### 2. Docker Desktop 설정 (Windows/Mac)
Docker Desktop 설치 후 다음과 같이 리소스를 설정하세요:

1. Docker Desktop 실행
2. Settings(⚙️) → Resources → Advanced
3. 권장 설정:
   - **Memory**: 최소 4GB, 권장 6GB 이상
   - **CPUs**: 최소 2개, 권장 4개 이상
   - **Swap**: 2GB
   - **Disk image size**: 20GB 이상
4. Apply & Restart 클릭

#### 3. Docker 설치 문제 해결

**Windows - WSL2 오류:**
```powershell
# WSL2 설치
wsl --install

# WSL2를 기본으로 설정
wsl --set-default-version 2

# 시스템 재시작 후 Docker Desktop 재실행
```

**Mac - 권한 오류:**
```bash
# Docker 소켓 권한 확인
ls -la /var/run/docker.sock

# 필요시 권한 수정
sudo chmod 666 /var/run/docker.sock
```

**Linux - Docker 데몬 시작 실패:**
```bash
# Docker 상태 확인
sudo systemctl status docker

# Docker 데몬 재시작
sudo systemctl restart docker

# 부팅 시 자동 시작 설정
sudo systemctl enable docker
```

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
# 환경 설정 마법사 실행 (권장)
python run.py setup

# 또는 수동 설정
# .env 파일 생성 및 편집
# Windows: notepad .env
# Mac/Linux: nano .env 또는 vi .env
```

**.env 파일 필수 설정 항목:**
```env
# 기본 설정
SECRET_KEY=your-secret-key-here-change-this  # run.py setup으로 자동 생성 가능

# 데이터베이스 (Docker 사용 시)
# 주의: 호스트명은 'postgres' 사용 (Docker 네트워크 내부)
DATABASE_URL=postgresql://trader:password123@postgres:5432/trading_system

# Telegram 설정 (선택사항)
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id

# 보안 설정
FLASK_ENV=production
DEBUG=False
ENABLE_SSL=true
FORCE_HTTPS=true
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
- **Password**: `admin_test_0623`
- ⚠️ **중요**: 첫 로그인 후 즉시 비밀번호 변경!

## 🐳 Docker Compose 상세 설명

### docker-compose.yml 구조
```yaml
version: '3.8'

services:
  # PostgreSQL 데이터베이스
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: trading_system
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: password123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  # Flask 웹 애플리케이션
  app:
    build:
      context: .
      dockerfile: config/Dockerfile
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql://trader:password123@postgres:5432/trading_system
    volumes:
      - ./web_server:/app/web_server
      - ./scripts:/app/scripts
      - ./migrations:/app/migrations
    ports:
      - "5001:5001"    # HTTP (Flask)
    networks:
      - trading-network

  # Nginx 리버스 프록시
  nginx:
    image: nginx:alpine
    depends_on:
      - app
    volumes:
      - ./config/nginx-ssl.conf:/etc/nginx/nginx.conf:ro
      - /dev/null:/etc/nginx/conf.d/default.conf:ro  # 기본 설정 비활성화
      - ./certs:/etc/nginx/certs:ro
      - nginx_logs:/var/log/nginx
    ports:
      - "443:443"      # HTTPS
      - "80:80"        # HTTP (HTTPS로 리다이렉트)
    networks:
      - trading-network

volumes:
  postgres_data:  # 데이터 영속성
  nginx_logs:     # Nginx 로그

networks:
  trading-network:
    driver: bridge
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

# 환경 설정
python run.py setup       # 환경 설정 마법사

# 로그 관리
python run.py logs        # 로그 확인
python run.py logs -f     # 실시간 로그

# 시스템 정리
python run.py clean       # 완전 초기화 (데이터, 이미지 삭제)
```

## 🌐 네트워크 아키텍처

### 3-Tier 구조
```
[외부 클라이언트]
       ↓
[Nginx (443/80)] ← HTTPS/리다이렉트
       ↓
[Flask App (5001)] ← 내부 HTTP
       ↓
[PostgreSQL (5432)]
```

### 포트 및 접근 경로

#### 외부 접근 (프로덕션)
- **HTTPS (권장)**: `https://your-domain` (포트 443)
  - Nginx가 SSL/TLS 종료 처리
  - HTTP 요청은 자동으로 HTTPS로 리다이렉트
- **웹훅 엔드포인트**: `https://your-domain/api/webhook`

#### 내부 접근 (개발/디버깅)
- **Flask 직접 접근**: `http://localhost:5001`
  - Docker 네트워크 외부에서 접근 가능
  - Nginx 우회, SSL 없음
- **PostgreSQL**: `localhost:5432`
  - Docker 컨테이너 간 통신: `postgres:5432`

### Docker 네트워크
- **네트워크 이름**: `trading-network` (bridge 드라이버)
- **컨테이너 간 통신**:
  - Flask → PostgreSQL: `postgres:5432`
  - Nginx → Flask: `app:5001`
- **호스트 → 컨테이너**:
  - 바인딩된 포트를 통해 `localhost:포트` 사용

### SSL/HTTPS 설정
- **자체 서명 인증서**: `./certs/` 디렉토리
  - `run.py start` 시 자동 생성 (cryptography 라이브러리)
  - 유효기간: 365일
- **브라우저 보안 경고**:
  - 자체 서명 인증서이므로 브라우저에서 경고 표시
  - 개발 환경에서는 안전하게 무시 가능
  - 프로덕션: Let's Encrypt 등 공인 인증서 사용 권장

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

# 서버 실행 (Flask만)
cd web_server
python -m app

# 또는 scripts/app.py 사용
cd scripts
python app.py
```

### 접속 방법 (수동 설치)
- **Flask 개발 서버**: `http://localhost:5001`
- **주의**: 수동 설치 시 Nginx를 별도로 설정해야 HTTPS 사용 가능
- **프로덕션**: Docker 환경 사용 권장 (Nginx + SSL 자동 설정)

### 기본 로그인 정보
- Username: `admin`
- Password: `admin_test_0623`
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

## 프로젝트 구조

```
webserver/                 # 프로젝트 루트
├── run.py                 # 🚀 통합 실행 스크립트 (크로스 플랫폼)
├── docker-compose.yml     # Docker 구성
├── README.md              # 메인 문서
├── .env                   # 환경 변수 (수동 생성)
├── config/                # ⚙️ 설정 파일들
│   ├── Dockerfile        # Docker 이미지 빌드
│   └── nginx-ssl.conf    # Nginx SSL 설정
├── certs/                 # 🔒 SSL 인증서
│   ├── cert.pem          # SSL 인증서
│   └── key.pem           # SSL 개인키
├── migrations/            # 📦 DB 마이그레이션
│   ├── versions/         # 마이그레이션 버전들
│   └── alembic.ini       # Alembic 설정
├── scripts/               # 📜 실행 스크립트들
│   ├── app.py            # Flask 앱 실행
│   ├── init_db.py        # DB 초기화
│   ├── check_service_dependencies.py  # 서비스 의존성 검증
│   ├── start.sh / start.bat           # 시작 스크립트
│   └── stop.sh / stop.bat             # 중지 스크립트
└── web_server/            # 🌐 메인 웹서버 코드
    ├── app/              # Flask 애플리케이션
    │   ├── __init__.py   # 앱 초기화
    │   ├── models.py     # 데이터베이스 모델
    │   ├── constants.py  # 상수 정의
    │   ├── routes/       # API 엔드포인트
    │   │   ├── webhook.py      # 웹훅 라우트
    │   │   ├── strategies.py   # 전략 관리
    │   │   ├── accounts.py     # 계정 관리
    │   │   └── ...
    │   ├── services/     # 비즈니스 로직
    │   │   ├── trading/  # 거래 서비스 (모듈화)
    │   │   │   ├── core.py              # 핵심 거래 실행
    │   │   │   ├── order_manager.py     # 주문 생명주기 관리
    │   │   │   ├── position_manager.py  # 포지션 및 PnL 관리
    │   │   │   ├── quantity_calculator.py # 수량 계산
    │   │   │   ├── record_manager.py    # 거래 기록
    │   │   │   └── event_emitter.py     # 이벤트 발행
    │   │   ├── webhook_service.py # 웹훅 처리
    │   │   ├── exchange.py        # 거래소 서비스
    │   │   ├── telegram.py        # Telegram 알림
    │   │   ├── analytics.py       # 성과 분석
    │   │   └── ...
    │   ├── exchanges/    # 거래소 어댑터
    │   │   ├── base.py         # 거래소 기본 클래스
    │   │   ├── binance.py      # Binance 어댑터
    │   │   ├── bybit.py        # Bybit 어댑터
    │   │   ├── upbit.py        # Upbit 어댑터
    │   │   ├── factory.py      # 거래소 팩토리
    │   │   └── metadata.py     # 거래소 메타데이터
    │   ├── static/       # CSS, JS, 이미지
    │   └── templates/    # HTML 템플릿
    ├── docs/             # 📚 프로젝트 문서
    ├── logs/             # 📝 로그 파일
    └── requirements.txt  # Python 의존성
```

### 구조의 장점
- 🎯 **명확한 분리**: 설정, 스크립트, 웹서버 코드 독립
- 🚀 **통합 관리**: 하나의 run.py로 모든 OS 지원
- 🔧 **유지보수 용이**: 기능별 디렉토리 분리
- 🔒 **보안**: SSL 인증서 분리 관리

## 문서

상세한 문서는 `web_server/docs/` 디렉토리에서 확인할 수 있습니다:

### 주요 문서
- [웹훅 메시지 포맷 가이드](docs/webhook_message_format.md) - 웹훅 API 전체 스펙 (배치 주문 포함)
- [웹훅 테스트 시나리오](CLAUDE.md#웹훅-기능-테스트-시나리오) - 실전 테스트 가이드
- [태스크 플랜](docs/task_plan.md) - 프로젝트 개발 계획 및 진행 상황

### 아키텍처 문서
- [전략 격리 수정 계획](web_server/docs/STRATEGY_ISOLATION_FIX_PLAN.md) - DB 기반 전략 격리 구현
- [요구사항](web_server/docs/REQUIREMENTS.md) - 시스템 요구사항

### API 문서
- **웹훅 API**: 위 "4. 웹훅 설정" 섹션 참조 (필수 파라미터, 배치 주문, 멀티 Exchange)
- **주문/포지션 API**: `/api` 엔드포인트 (인증 필요)
- **실시간 이벤트**: Server-Sent Events (SSE) 지원

### 변경 이력
- **2025-10-08**: 코드 리뷰 반영, 배치 주문 개선, 멀티 Exchange 중복 경고
- **2025-10-07**: 배치 주문 포맷 변경 (Breaking Change), 멀티 Exchange 지원
- **이전 변경사항**: [Git 커밋 로그](https://github.com/binee108/crypto-trading-web-service/commits/) 참조

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
**웹훅 URL:**
```
https://your-domain.com/api/webhook
```

**필수 파라미터:**
- `group_name`: 전략 그룹명 (전략 식별자)
  - 시장 타입 및 거래소는 전략 설정에서 자동 결정됨
  - **멀티 Exchange 지원**: Strategy 연동 모든 계좌에서 자동 주문 실행
- `currency`: 기준 통화 (크립토 거래 시)
  - 글로벌 거래소: `USDT`, `BTC`
  - Upbit: `KRW` (원화 마켓)
- `symbol`: 거래 심볼 (표준 형식: `BASE/QUOTE`)
  - 예시: `BTC/USDT`, `ETH/USDT`, `BTC/KRW`
  - 시스템이 자동으로 거래소별 형식으로 변환
- `side`: 거래 방향
  - `buy`: 매수 (롱 포지션 진입)
  - `sell`: 매도 (숏 포지션 진입 또는 청산)
- `order_type`: 주문 타입
  - `MARKET`: 시장가 주문
  - `LIMIT`: 지정가 주문 (price 필수)
  - `STOP_MARKET`: 스탑 마켓 주문 (stop_price 필수)
  - `STOP_LIMIT`: 스탑 리밋 주문 (price, stop_price 필수)
  - `CANCEL_ALL_ORDER`: 모든 주문 취소
- `qty_per`: 수량 비율 (%)
  - 양수: 계좌 자본의 N% 사용
  - `-100`: 현재 포지션 100% 청산
- `token`: 웹훅 인증 토큰 (사용자별 고유 토큰)

#### 멀티 Exchange 지원

웹훅은 `exchange`를 지정하지 않습니다.
**Strategy에 연동된 모든 계좌**에서 자동으로 주문이 실행됩니다.

**예시:**
- Strategy에 Binance, Bybit, Upbit 계좌 연동
- 웹훅 1개 전송 → 3개 거래소에 동시 주문 ✅

**동작 방식:**
```
Strategy (전략)
  ↓ 연동 계좌 (StrategyAccount)
  ├─ Binance 계좌 → Binance에서 주문 실행
  ├─ Bybit 계좌 → Bybit에서 주문 실행
  └─ Upbit 계좌 → Upbit에서 주문 실행
```

**중복 주문 감지:**
- 동일 거래소 계좌가 중복 연동된 경우 **WARNING 로그** 발행
- 예: Binance 계좌 2개 연동 시 → 로그에 경고 메시지 표시
- 의도하지 않은 중복 주문 방지를 위해 Strategy 계좌 설정 확인 권장

> ⚠️ **계좌 관리 주의**: Strategy에 같은 거래소 계좌가 중복 연동되면
> 의도하지 않은 중복 주문이 발생할 수 있습니다.
> 로그를 확인하여 중복 계좌 연동을 제거하세요.

**선택적 파라미터:**
- `price`: 지정가 (LIMIT, STOP_LIMIT 주문 시 필수)
- `stop_price`: 스탑 가격 (STOP_MARKET, STOP_LIMIT 주문 시 필수)

**웹훅 페이로드 예시:**

#### 시장가 주문
```json
{
    "group_name": "my_strategy",
    "currency": "USDT",
    "symbol": "BTC/USDT",
    "order_type": "MARKET",
    "side": "buy",
    "qty_per": 10,
    "token": "your_webhook_token"
}
```

#### 지정가 주문
```json
{
    "group_name": "my_strategy",
    "currency": "USDT",
    "symbol": "BTC/USDT",
    "order_type": "LIMIT",
    "side": "sell",
    "price": "130000",
    "qty_per": 10,
    "token": "your_webhook_token"
}
```

#### 스탑 마켓 주문
```json
{
    "group_name": "my_strategy",
    "currency": "USDT",
    "symbol": "BTC/USDT",
    "order_type": "STOP_MARKET",
    "side": "sell",
    "stop_price": "131000",
    "qty_per": 10,
    "token": "your_webhook_token"
}
```

#### 스탑 리밋 주문
```json
{
    "group_name": "my_strategy",
    "currency": "USDT",
    "symbol": "BTC/USDT",
    "order_type": "STOP_LIMIT",
    "side": "sell",
    "price": "132000",
    "stop_price": "131000",
    "qty_per": 10,
    "token": "your_webhook_token"
}
```

#### 포지션 100% 청산 (qty_per=-100)
```json
{
    "group_name": "my_strategy",
    "currency": "USDT",
    "symbol": "BTC/USDT",
    "order_type": "MARKET",
    "side": "sell",
    "qty_per": -100,
    "token": "your_webhook_token"
}
```

#### 모든 주문 취소
```json
{
    "group_name": "my_strategy",
    "currency": "USDT",
    "symbol": "BTC/USDT",
    "order_type": "CANCEL_ALL_ORDER",
    "token": "your_webhook_token"
}
```
**참고:** `symbol`은 선택적 (지정 시 해당 심볼만 취소)

#### 배치 주문 (여러 주문 동시 실행)

> ⚠️ **Breaking Change (2025-10-08)**: 배치 주문 폴백 정책이 간소화되었습니다.
> - **상위 레벨 공통 필드** (필수): `group_name`, `token`
> - **상위 레벨 공통 필드** (선택, 폴백 지원): `symbol`, `currency`
> - **각 주문 필수 필드**: `order_type`, `side`, `qty_per` (주문 타입에 따라 `price`, `stop_price` 필수)
> - **자동 우선순위 정렬**: MARKET > CANCEL > LIMIT > STOP

**폴백 정책 (간소화)**:
- **폴백 지원 O**: `symbol`, `currency`만 상위 레벨에서 폴백 가능
- **폴백 지원 X**: `side`, `price`, `stop_price`, `qty_per`는 각 주문에 명시 필수
- **명확한 계약**: 각 주문이 완전한 정보를 가져야 함

**기본 예시 (기존 주문 취소 + 2개 매수 주문):**
```json
{
    "group_name": "multi_order_strategy",
    "symbol": "BTC/USDT",
    "currency": "USDT",
    "token": "your_webhook_token",
    "orders": [
        {
            "order_type": "CANCEL_ALL_ORDER"
        },
        {
            "side": "buy",
            "order_type": "LIMIT",
            "price": "105000",
            "qty_per": 5
        },
        {
            "side": "buy",
            "order_type": "LIMIT",
            "price": "104000",
            "qty_per": 10
        }
    ]
}
```

**폴백 지원 예시 (symbol, currency만)**:
```json
{
    "group_name": "multi_strategy",
    "symbol": "BTC/USDT",     // ✅ 폴백 지원 - 개별 주문에서 생략 가능
    "currency": "USDT",       // ✅ 폴백 지원 - 개별 주문에서 생략 가능
    "token": "your_webhook_token",
    "orders": [
        {
            "order_type": "LIMIT",
            "side": "buy",        // ❌ 폴백 없음 - 각 주문에 필수
            "price": "90000",     // ❌ 폴백 없음 - 각 주문에 필수
            "qty_per": 10         // ❌ 폴백 없음 - 각 주문에 필수
            // symbol, currency는 상위 레벨 사용 (BTC/USDT, USDT)
        },
        {
            "order_type": "MARKET",
            "side": "sell",       // ❌ 각 주문에 명시 필수
            "qty_per": 5          // ❌ 각 주문에 명시 필수
            // symbol, currency는 상위 레벨 사용
        }
    ]
}
```

**우선순위 자동 정렬:**
배치 주문은 다음 순서로 자동 정렬되어 실행됩니다:
1. **MARKET** - 시장가 주문 (최우선)
2. **CANCEL, CANCEL_ALL_ORDER** - 주문 취소
3. **LIMIT** - 지정가 주문
4. **STOP_MARKET, STOP_LIMIT** - 스탑 주문

**사용 사례:**
- 사다리 주문 (ladder order): 여러 가격대에 분할 매수/매도
- OCO 주문: 익절과 손절을 동시 설정
- 포트폴리오 리밸런싱: 기존 주문 취소 후 새 주문 생성

**상세 문서:**
- [웹훅 메시지 포맷 가이드](docs/webhook_message_format.md#10-배치-주문-예시-orders-배열)
- [웹훅 테스트 시나리오](CLAUDE.md#웹훅-기능-테스트-시나리오)

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