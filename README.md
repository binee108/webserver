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

## 빠른 시작

### 요구사항
- Python 3.8+
- SQLite (개발) / PostgreSQL (프로덕션)

### 설치
```bash
# 프로젝트 클론
git clone https://github.com/binee108/crypto-trading-web-service.git
cd crypto-trading-system

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
- **HTTP (비활성화시)**: http://localhost:5001

### 기본 로그인 정보
- Username: `admin`
- Password: `admin123`
- ⚠️ **첫 로그인 후 반드시 비밀번호를 변경하세요!**

### SSL 인증서 관련
- 자체 서명 인증서를 자동으로 생성합니다
- 브라우저에서 보안 경고가 나타나면 "고급" → "안전하지 않음을 승인하고 계속 진행" 클릭
- 인증서는 `certs/` 디렉토리에 저장됩니다

## 프로젝트 구조

```
webserver/
├── app/                    # 애플리케이션 코드
│   ├── routes/            # API 엔드포인트
│   ├── services/          # 비즈니스 로직
│   ├── static/            # CSS, JS, 이미지
│   └── templates/         # HTML 템플릿
├── docs/                  # 프로젝트 문서
├── migrations/            # 데이터베이스 마이그레이션
├── requirements.txt       # Python 의존성
└── config.py             # 애플리케이션 설정
```

## 문서

상세한 문서는 `docs/` 디렉토리에서 확인할 수 있습니다:

- [프로젝트 개요](docs/PROJECT_OVERVIEW.md) - 시스템 전체 개요
- [아키텍처](docs/ARCHITECTURE.md) - 시스템 아키텍처 및 설계
- [설치 가이드](docs/SETUP_GUIDE.md) - 상세한 설치 및 설정 방법
- [API 문서](docs/POSITIONS_AND_ORDERS_API.md) - API 엔드포인트 문서
- [데이터베이스 스키마](docs/DATABASE_SCHEMA.md) - 데이터베이스 구조

## 주요 사용 방법

### 1. 거래소 계정 등록
1. 로그인 후 "계정 관리" 메뉴 접속
2. "새 계정 추가" 클릭
3. 거래소 선택 및 API 키 입력
4. 연결 테스트 확인

### 2. 전략 생성
1. "전략 관리" 메뉴 접속
2. "새 전략 추가" 클릭
3. 전략 이름, 그룹명, 시장 타입 설정
4. 웹훅 키 자동 생성 확인

### 3. 전략-계정 연결
1. 생성된 전략의 "계정 연결" 클릭
2. 사용할 거래소 계정 선택
3. 레버리지 및 가중치 설정
4. 저장

### 4. 웹훅 설정
웹훅 URL: `https://your-domain.com/webhook/{strategy_webhook_key}`

웹훅 페이로드 예시:
```json
{
    "symbol": "BTCUSDT",
    "action": "BUY",
    "quantity": 0.001,
    "price": "limit:45000"
}
```

### 5. 모니터링
- **대시보드**: 전체 계정 현황 및 수익률
- **포지션**: 실시간 포지션 및 미체결 주문
- **거래 내역**: 체결된 거래 기록

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