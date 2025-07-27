# 설치 및 설정 가이드

## 목차
1. [시스템 요구사항](#시스템-요구사항)
2. [프로젝트 설치](#프로젝트-설치)
3. [환경 설정](#환경-설정)
4. [데이터베이스 초기화](#데이터베이스-초기화)
5. [개발 서버 실행](#개발-서버-실행)
6. [프로덕션 배포](#프로덕션-배포)
7. [거래소 API 설정](#거래소-api-설정)
8. [Telegram 봇 설정](#telegram-봇-설정)
9. [문제 해결](#문제-해결)

## 시스템 요구사항

### 최소 요구사항
- Python 3.8 이상
- 2GB RAM
- 1GB 디스크 공간

### 권장 사양
- Python 3.10 이상
- 4GB RAM 이상
- SSD 스토리지
- 안정적인 인터넷 연결

### 운영체제
- Linux (Ubuntu 20.04+, CentOS 8+)
- macOS 10.15+
- Windows 10+ (WSL2 권장)

## 프로젝트 설치

### 1. 프로젝트 클론
```bash
git clone https://github.com/your-repo/crypto-trading-system.git
cd crypto-trading-system
```

### 2. Python 가상환경 생성
```bash
# Python 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
# Linux/macOS:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

### 3. 의존성 패키지 설치
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 환경 설정

### 1. 환경 변수 파일 생성
```bash
# env.example 파일을 복사하여 .env 파일 생성
cp env.example .env
```

### 2. .env 파일 편집
```bash
# 텍스트 에디터로 .env 파일 열기
nano .env  # 또는 vi, code 등 선호하는 에디터 사용
```

### 3. 필수 환경 변수 설정
```env
# Flask 설정
FLASK_APP=app.py
FLASK_ENV=development  # production으로 변경 시 프로덕션 모드
SECRET_KEY=your-secret-key-here  # 강력한 랜덤 키로 변경 필수!

# 데이터베이스 설정
DATABASE_URL=sqlite:///instance/trading_system.db  # 개발용
# DATABASE_URL=postgresql://user:password@localhost/dbname  # 프로덕션용

# Telegram 봇 설정 (선택사항)
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id

# 로깅 설정
LOG_LEVEL=INFO                    # 메인 애플리케이션 로깅 레벨
LOG_FILE=logs/app.log            # 로그 파일 경로
BACKGROUND_LOG_LEVEL=WARNING     # 백그라운드 작업 로깅 레벨 (스케줄러)
```

### 4. Secret Key 생성
```python
# Python에서 안전한 Secret Key 생성
python -c "import secrets; print(secrets.token_hex(32))"
```

## 데이터베이스 초기화

### 1. 데이터베이스 마이그레이션 초기화
```bash
# 마이그레이션 폴더가 없는 경우
flask db init

# 마이그레이션 적용
flask db upgrade
```

### 2. 초기 데이터 설정
```bash
# 기본 관리자 계정 생성
python init_db.py
```

초기 관리자 계정:
- **Username**: admin
- **Password**: admin123
- ⚠️ **중요**: 첫 로그인 시 반드시 비밀번호를 변경하세요!

## 개발 서버 실행

### 1. Flask 개발 서버 시작
```bash
# 기본 실행 (포트 5001)
python app.py

# 또는 Flask CLI 사용
flask run --host=0.0.0.0 --port=5001
```

### 2. 애플리케이션 접속
브라우저에서 다음 주소로 접속:
```
http://localhost:5001
```

### 3. 로그인
- Username: admin
- Password: admin123
- 첫 로그인 시 비밀번호 변경 필수

## 프로덕션 배포

### 1. 프로덕션 환경 설정
```bash
# .env 파일 수정
FLASK_ENV=production
DATABASE_URL=postgresql://user:password@localhost/trading_db
SECRET_KEY=your-production-secret-key
```

### 2. PostgreSQL 데이터베이스 설정
```bash
# PostgreSQL 설치 (Ubuntu)
sudo apt-get install postgresql postgresql-contrib

# 데이터베이스 생성
sudo -u postgres createdb trading_db
sudo -u postgres createuser trading_user -P

# 권한 부여
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE trading_db TO trading_user;"
```

### 3. Gunicorn 설치 및 설정
```bash
pip install gunicorn

# Gunicorn 실행
gunicorn -w 4 -b 0.0.0.0:5001 app:app
```

### 4. Nginx 리버스 프록시 설정
```nginx
# /etc/nginx/sites-available/trading-system
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /path/to/your/app/static;
        expires 30d;
    }
}
```

### 5. Systemd 서비스 생성
```ini
# /etc/systemd/system/trading-system.service
[Unit]
Description=Crypto Trading System
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/your/app
Environment="PATH=/path/to/your/app/venv/bin"
ExecStart=/path/to/your/app/venv/bin/gunicorn -w 4 -b 127.0.0.1:5001 app:app

[Install]
WantedBy=multi-user.target
```

### 6. 서비스 시작
```bash
sudo systemctl enable trading-system
sudo systemctl start trading-system
sudo systemctl status trading-system
```

## 거래소 API 설정

### 1. Binance API
1. [Binance](https://www.binance.com) 로그인
2. API Management 페이지 접속
3. Create API 클릭
4. API Key와 Secret Key 저장
5. IP 제한 설정 (권장)

### 2. Bybit API
1. [Bybit](https://www.bybit.com) 로그인
2. API 페이지 접속
3. Create New Key 클릭
4. 권한 설정 (거래, 포지션 읽기)
5. API Key와 Secret 저장

### 3. OKX API
1. [OKX](https://www.okx.com) 로그인
2. API 페이지 접속
3. Create V5 API Key
4. 권한 설정 및 Passphrase 설정
5. API Key, Secret, Passphrase 저장

### 4. 시스템에 API 키 등록
1. 웹 인터페이스 로그인
2. 계정 관리 → 새 계정 추가
3. 거래소 선택 및 API 정보 입력
4. 테스트 연결 확인

## Telegram 봇 설정

### 1. 봇 생성
1. Telegram에서 @BotFather 검색
2. `/newbot` 명령어 입력
3. 봇 이름과 username 설정
4. 생성된 Bot Token 저장

### 2. Chat ID 확인
1. 생성한 봇과 대화 시작
2. 브라우저에서 접속:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
3. "chat":{"id": 부분에서 Chat ID 확인

### 3. 환경 변수 설정
```env
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

## 문제 해결

### 1. 모듈 import 오류
```bash
# 의존성 재설치
pip install -r requirements.txt --force-reinstall
```

### 2. 데이터베이스 연결 오류
```bash
# SQLite 권한 확인
chmod 664 instance/trading_system.db
chmod 775 instance/

# PostgreSQL 연결 확인
psql -U trading_user -d trading_db -h localhost
```

### 3. 포트 충돌
```bash
# 사용 중인 포트 확인
lsof -i :5001

# 다른 포트로 실행
python app.py --port 5002
```

### 4. 로그 확인
```bash
# 애플리케이션 로그
tail -f logs/app.log

# 시스템 로그 (systemd)
sudo journalctl -u trading-system -f
```

### 5. 메모리 부족
```bash
# Swap 파일 생성 (Ubuntu)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

## 보안 권장사항

1. **강력한 비밀번호 사용**
   - 최소 12자 이상
   - 대소문자, 숫자, 특수문자 조합

2. **API 키 보안**
   - IP 화이트리스트 설정
   - 읽기/거래 권한만 부여
   - 출금 권한 비활성화

3. **HTTPS 사용**
   - Let's Encrypt 인증서 설치
   - SSL/TLS 설정

4. **정기적인 백업**
   - 데이터베이스 일일 백업
   - 설정 파일 백업

5. **모니터링**
   - 로그 모니터링
   - 비정상 거래 감지

## 다음 단계

1. **사용자 추가**: 관리자 페이지에서 새 사용자 생성
2. **전략 설정**: 거래 전략 생성 및 설정
3. **계정 연결**: 거래소 API 키 등록
4. **자본 할당**: 전략별 자본 배분
5. **모니터링**: 대시보드에서 실시간 모니터링

## 지원 및 문의

- 문서: `/docs` 디렉토리 참조
- 이슈: GitHub Issues 활용
- 로그: `/logs` 디렉토리 확인