# 암호화폐/증권 자동 거래 시스템

Flask 기반의 통합 거래 시스템으로, 다수의 거래소 계정을 통합 관리하고 웹훅 시그널을 통한 자동 거래를 지원합니다.

## 주요 기능

- 🌐 **멀티 Exchange**: Binance, Bybit, Upbit 통합 지원
- 🤖 **웹훅 자동 거래**: TradingView 등 외부 시그널 기반 주문 실행
- 📦 **배치 주문**: 하나의 웹훅으로 여러 주문 동시 실행 (우선순위 자동 정렬)
- 💰 **전략별 자본 관리**: 독립적인 전략 격리 및 리스크 관리
- 📊 **실시간 모니터링**: WebSocket 기반 가격/포지션 업데이트
- 📈 **성과 분석**: ROI, 샤프/소르티노 비율, 일일/누적 PnL
- 📱 **Telegram 알림**: 거래 실행 및 일일 리포트
- 🔒 **보안**: API 키 암호화, HTTPS, CSRF 보호

---

## 🚀 빠른 시작 (Docker 권장)

### 1. 사전 준비
- [Docker Desktop](https://www.docker.com/products/docker-desktop) 설치
- Git 설치

### 2. 프로젝트 다운로드
```bash
git clone https://github.com/binee108/crypto-trading-web-service.git
cd webserver
```

### 3. 환경 설정
```bash
# 자동 설정 마법사 실행
python run.py setup

# 또는 수동 설정
cp env.example .env
# .env 파일 편집 (SECRET_KEY, DATABASE_URL 등)
```

### 4. 시스템 시작
```bash
# Docker Compose로 전체 시스템 시작
docker-compose up -d

# 또는 통합 스크립트 사용
python run.py start
```

### 5. 웹 접속
- **URL**: `https://localhost`
- **기본 계정**:
  - Username: `admin`
  - Password: `admin_test_0623`
- ⚠️ 첫 로그인 후 즉시 비밀번호 변경 필수!

---

## 📋 통합 실행 스크립트 (run.py)

```bash
python run.py start       # 시스템 시작
python run.py stop        # 중지
python run.py restart     # 재시작
python run.py status      # 상태 확인
python run.py setup       # 환경 설정 마법사
python run.py logs        # 로그 확인
python run.py clean       # 완전 초기화
```

### 🌳 Git Worktree 자동 충돌 해결

여러 worktree에서 작업 시, 다른 경로에서 실행 중인 서비스를 자동으로 감지하고 정리합니다:

```bash
# worktree1에서 서비스 실행 중
cd /path/to/worktree1
python run.py start  # ✅ 정상 실행

# worktree2에서 start
cd /path/to/worktree2
python run.py start  # ⚠️ worktree1 서비스 감지 → 종료 → 시작

# worktree2에서 restart
python run.py restart  # ⚠️ 다른 경로 서비스 감지 → 종료 → 재시작

# worktree3에서 clean
cd /path/to/worktree3
python run.py clean  # ⚠️ 모든 경로 서비스 감지 → 종료 → 정리
```

**적용 명령어**: `start`, `restart`, `clean`

**자동 처리 내용:**
- ✅ 다른 worktree의 실행 중인 컨테이너 자동 감지
- ✅ 포트 충돌 (443, 5001, 5432) 사전 확인
- ✅ 충돌 서비스 자동 정리 (docker-compose down)
- ✅ 포트 해제 대기 후 현재 경로 서비스 시작/재시작
- ✅ 안전한 전환을 위한 상태 확인
- ✅ 모든 명령어에서 일관된 동작

---

## 📖 사용 방법

### 1. 거래소 계정 등록
1. 로그인 후 "계정 관리" → "새 계정 추가"
2. 거래소 선택 및 API 키 입력
   - ⚠️ **출금 권한 비활성화 필수**
   - 거래 + 읽기 권한만 부여
   - IP 화이트리스트 설정 권장

### 2. 전략 생성
1. "전략 관리" → "새 전략 추가"
2. 전략 정보 입력:
   - 전략 이름, 그룹명
   - 시장 타입 (SPOT/FUTURES)
   - 웹훅 토큰 자동 생성 (복사 보관)

### 3. 전략-계정 연결
1. 전략 "계정 연결" 클릭
2. 거래소 계정 선택
3. 거래 설정:
   - 레버리지 (Futures만)
   - 가중치 (자본 배분 비율)
   - 최대 포지션 수

### 4. 웹훅 설정

#### 웹훅 URL
```
https://your-domain.com/api/webhook
```

#### 필수 필드

| 필드 | 설명 | 예시 |
|------|------|------|
| `group_name` | 전략 식별자 | `"my_strategy"` |
| `symbol` | 거래 심볼 | `"BTC/USDT"`, `"005930"` |
| `order_type` | 주문 타입 | `"MARKET"`, `"LIMIT"` |
| `side` | 거래 방향 | `"buy"`, `"sell"` |
| `qty_per` | 수량 (크립토: %, 증권: 주) | `10`, `-100` (청산) |
| `token` | 웹훅 인증 토큰 | 전략에서 생성된 토큰 |

#### 주문 타입별 추가 필드

| order_type | 추가 필수 필드 |
|------------|---------------|
| `LIMIT` | `price` |
| `STOP_MARKET` | `stop_price` |
| `STOP_LIMIT` | `price`, `stop_price` |
| `CANCEL_ALL_ORDER` | `symbol` (side 선택적) |

#### 심볼 포맷
- **크립토**: `COIN/CURRENCY` (슬래시 필수)
  - 예: `"BTC/USDT"`, `"ETH/KRW"`
- **증권**: 종목코드
  - 국내: `"005930"` (삼성전자)
  - 해외: `"AAPL"`, `"TSLA"`

---

## 📝 웹훅 예시

### 시장가 매수
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "MARKET",
  "side": "buy",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```

### 지정가 매도
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "LIMIT",
  "side": "sell",
  "price": "130000",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```

### 손절 주문 (STOP_LIMIT)
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "STOP_LIMIT",
  "side": "sell",
  "price": "94000",
  "stop_price": "95000",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```
**설명**: BTC 가격이 $95,000 이하로 떨어지면 $94,000에 매도

### 포지션 100% 청산
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "MARKET",
  "side": "sell",
  "qty_per": -100,
  "token": "your_webhook_token"
}
```
**qty_per=-100**: 전체 포지션 청산 (롱/숏 자동 판단)

### 심볼별 주문 취소
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "CANCEL_ALL_ORDER",
  "token": "your_webhook_token"
}
```

### 특정 방향만 취소
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "CANCEL_ALL_ORDER",
  "token": "your_webhook_token"
}
```
**side 지정**: 매수 주문만 취소, 매도 주문은 유지

---

## 📦 배치 주문

### 구조
```json
{
  "group_name": "strategy_name",
  "symbol": "BTC/USDT",
  "token": "your_token",
  "orders": [
    {"order_type": "주문1"},
    {"order_type": "주문2"}
  ]
}
```

### 폴백 정책
- **상위 레벨 폴백**: `symbol`만 (각 주문에서 생략 가능)
- **각 주문 필수**: `order_type`, `side`, `qty_per`, `price` (타입별)

### 자동 우선순위 정렬
1. MARKET (시장가)
2. CANCEL_ALL_ORDER (취소)
3. LIMIT (지정가)
4. STOP_MARKET, STOP_LIMIT

### 예시: 기존 주문 취소 후 재생성
```json
{
  "group_name": "ladder_strategy",
  "symbol": "BTC/USDT",
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
**처리 순서**: CANCEL → LIMIT(105000) → LIMIT(104000)

---

## 🌐 멀티 Exchange 지원

### 동작 방식
웹훅에서 `exchange`를 지정하지 않습니다.
**전략에 연동된 모든 계좌**에서 자동으로 주문이 실행됩니다.

```
Strategy (전략)
  ├─ Binance 계좌 → Binance 주문 실행
  ├─ Bybit 계좌 → Bybit 주문 실행
  └─ Upbit 계좌 → Upbit 주문 실행
```

**예시**:
- 전략에 3개 거래소 계좌 연동
- 웹훅 1개 전송 → 3개 거래소에 동시 주문 ✅

**중복 주문 감지**:
- 동일 거래소 계좌 중복 연동 시 WARNING 로그 발행
- 로그 확인하여 중복 제거 권장

---

## 🐳 Docker 환경

### 아키텍처
```
[외부 클라이언트]
       ↓
[Nginx (443/80)] ← HTTPS/리다이렉트
       ↓
[Flask App (5001)] ← 내부 HTTP
       ↓
[PostgreSQL (5432)]
```

### 주요 명령어
```bash
# 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 중지
docker-compose stop

# 재시작
docker-compose restart

# 완전 제거
docker-compose down

# 데이터까지 삭제
docker-compose down -v
```

### 컨테이너 접속
```bash
# Flask 앱 컨테이너
docker-compose exec app bash

# PostgreSQL 컨테이너
docker-compose exec postgres psql -U trader trading_system
```

---

## 📂 프로젝트 구조

```
webserver/
├── run.py                 # 통합 실행 스크립트
├── docker-compose.yml     # Docker 구성
├── config/                # 설정 파일
│   ├── Dockerfile
│   └── nginx-ssl.conf
├── web_server/            # 메인 코드
│   ├── app/
│   │   ├── models.py     # 데이터베이스 모델
│   │   ├── routes/       # API 엔드포인트
│   │   ├── services/     # 비즈니스 로직
│   │   │   ├── trading/  # 거래 서비스 (모듈화)
│   │   │   ├── webhook_service.py
│   │   │   ├── exchange.py
│   │   │   └── ...
│   │   └── exchanges/    # 거래소 어댑터
│   ├── docs/             # 문서
│   └── logs/             # 로그 파일
└── scripts/              # 실행 스크립트
```

---

## 📚 문서

- [웹훅 메시지 포맷 가이드](docs/webhook_message_format.md) - API 전체 스펙
- [웹훅 테스트 시나리오](CLAUDE.md#웹훅-기능-테스트-시나리오) - 실전 테스트 가이드
- [개발 가이드라인](CLAUDE.md) - 프로젝트 개발 원칙

---

## 🔧 문제 해결

### Docker 서비스 미실행
```bash
# Docker 상태 확인
docker version

# Docker Desktop 재시작 (Windows/Mac)
# Linux: Docker 서비스 시작
sudo systemctl start docker
```

### 포트 충돌
```bash
# 사용 중인 포트 확인
sudo lsof -i :443
sudo lsof -i :5432

# docker-compose.yml에서 포트 변경
# 예: 443:443 → 8443:443
```

### 데이터베이스 연결 실패
```bash
# PostgreSQL 상태 확인
docker-compose ps postgres
docker-compose logs postgres

# 데이터베이스 재시작
docker-compose restart postgres
```

### SSL 인증서 경고
브라우저별 해결 방법:

**Chrome**: 경고 화면에서 `thisisunsafe` 타이핑
**Firefox**: "고급" → "위험을 감수하고 계속"
**Safari**: "자세한 정보 보기" → "웹사이트 방문"

---

## 🔒 보안 주의사항

### API 키 보안
- ⚠️ **출금 권한 비활성화 필수**
- IP 화이트리스트 설정
- 읽기 + 거래 권한만 부여

### 시스템 보안
- 강력한 비밀번호 사용 (12자 이상)
- 프로덕션 환경 HTTPS 필수
- 정기적인 보안 업데이트

### 웹훅 토큰 보호
- GitHub, Slack 등에 토큰 공유 금지
- 환경 변수 사용 권장
- TradingView 알림 설정 시 주의

---

## 면책 조항

이 소프트웨어는 교육 및 연구 목적으로 제공됩니다. 실제 거래에 사용할 경우 발생하는 모든 손실에 대해 개발자는 책임지지 않습니다. 암호화폐 거래는 높은 위험을 수반하므로 신중하게 사용하시기 바랍니다.

---

**최종 업데이트**: 2025-10-08
**버전**: 2.0 (통합 웹훅 시스템)
