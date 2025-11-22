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

## 🎛️ CLI 명령어 상세 가이드

### 시스템 시작

```bash
python run.py start
```

**기능:**
- SSL 인증서 확인 및 생성 (필요시)
- 환경 설정 파일 생성 (.env)
- Docker Compose 시작
- 헬스 체크 (최대 30초)
- 포트 가용성 확인 (443, 5001)

**워크트리 지원:**
자동으로 워크트리 이름을 프로젝트명에 포함:
```bash
cd .worktree/feature-test
python run.py start
# ✅ webserver-wt-feature-test 프로젝트로 자동 시작
```

### 시스템 중지

```bash
python run.py stop
```

**기능:**
- Docker Compose 중지
- 컨테이너 정상 종료

### 시스템 재시작

```bash
python run.py restart
```

**기능:**
- `stop` + `start` 조합 실행
- 다른 worktree 서비스 자동 정리

### 시스템 상태 확인

```bash
python run.py status
```

**표시 정보:**
- Docker 컨테이너 상태 (running, stopped)
- 포트 상태 (443, 5001, 5432)
- 헬스 체크 결과

### Docker 로그 조회

```bash
# 모든 서비스 로그 출력
python run.py logs

# 특정 컨테이너 로그만
python run.py logs app
python run.py logs postgres

# 실시간 추종
python run.py logs -f
python run.py logs -f app
```

**옵션:**
- `-f, --follow`: 실시간 로그 추종
- 컨테이너명: 특정 컨테이너만 표시 (기본: 모든 컨테이너)

### 시스템 정리

```bash
# 중지된 컨테이너만 제거
python run.py clean

# 모든 컨테이너 및 볼륨 제거 (위험)
python run.py clean --all
```

**기능:**
- Docker 정리 (stopped, dangling images)
- --all 옵션: 볼륨도 함께 제거
- 안전 확인 메시지 표시 후 실행

### 초기 환경 설정

```bash
# 기본값으로 설정
python run.py setup

# 프로덕션 환경으로 설정
python run.py setup --env production
```

**기능:**
- .env 파일 생성
- 데이터베이스 설정
- API 키 설정
- 환경 선택 (development/production)

---

## 🏗️ CLI 아키텍처

### 모듈 구조

```
run.py (진입점, 62줄)
│
├─ cli/manager.py (TradingSystemCLI 라우팅, 168줄)
│  │
│  ├─ cli/config.py (설정, 113줄)
│  │
│  ├─ cli/helpers/ (유틸리티, 1,245줄)
│  │  ├─ printer.py (출력 포맷팅, 98줄)
│  │  ├─ network.py (포트 확인, 105줄)
│  │  ├─ docker.py (Docker 관리, 431줄)
│  │  ├─ ssl.py (SSL 인증서, 161줄)
│  │  └─ env.py (환경 설정, 377줄)
│  │
│  └─ cli/commands/ (명령어, 1,252줄)
│     ├─ base.py (BaseCommand, 37줄)
│     ├─ start.py (시작, 381줄)
│     ├─ stop.py (중지, 89줄)
│     ├─ restart.py (재시작, 62줄)
│     ├─ logs.py (로그, 141줄)
│     ├─ status.py (상태, 177줄)
│     ├─ clean.py (정리, 232줄)
│     └─ setup.py (설정, 109줄)
```

### 설계 패턴

- **Command 패턴**: 각 CLI 명령어를 독립 클래스로 구현
- **의존성 주입**: Helper → Command → Manager 구조
- **Template Method**: BaseCommand 추상 클래스
- **Strategy 패턴**: RestartCommand = Stop + Start 조합

### 마이그레이션 성과

| 지표 | 개선 |
|------|------|
| 파일 크기 | 1,946줄 → 78줄 평균 (96% 감소) |
| 모듈 수 | 1개 → 36개 (책임 분리) |
| 테스트 가능성 | 0% → 100% (의존성 주입) |
| 유지보수성 | 현저히 향상 |

**상세 정보:** [`docs/CLI_MIGRATION.md`](docs/CLI_MIGRATION.md)

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
| `qty_per` | 수량 (크립토: %, 증권: 주) | `10`, `-100` (청산), `200` (레버리지 활용) |
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

### 🏷️ 주문 상태 표준화

거래소별 상이한 주문 상태를 표준 형식으로 통합하여 일관된 처리를 제공합니다.

#### 지원 거래소 및 상태 매핑
| 거래소 | 원본 상태 | 표준 상태 |
|--------|----------|----------|
| **BINANCE** | NEW, PARTIALLY_FILLED, FILLED, CANCELED | NEW, PARTIALLY_FILLED, FILLED, CANCELLED |
| **UPBIT** | wait, done, cancel | OPEN, FILLED, CANCELLED |
| **BITHUMB** | bid, fill, cancel | OPEN, FILLED, CANCELLED |
| **BYBIT** | Created, PartiallyFilled, Filled | NEW, PARTIALLY_FILLED, FILLED |

#### 사용 방법
```python
from web_server.app.exchanges.transformers.order_status_transformer import OrderStatusTransformer
from web_server.app.constants import StandardOrderStatus

# 거래소별 상태를 표준 상태로 변환
transformer = OrderStatusTransformer()
standard_status = transformer.transform('wait', 'UPBIT')  # 'OPEN' 반환

# 상태 유효성 및 분류 확인
is_valid = StandardOrderStatus.is_valid(standard_status)
is_terminal = StandardOrderStatus.is_terminal(standard_status)
```

#### 장점
- **일관성**: 모든 거래소의 상태를 통합된 형식으로 관리
- **확장성**: 새로운 거래소 추가 시 상태 매핑만 등록
- **하위 호환성**: 기존 시스템과의 호환성 유지
- **검증 기능**: 상태 유효성, 활성/최종 상태 분류 지원

자세한 내용은 [거래소 주문 상태 표준화 문서](docs/features/exchange-order-status-standardization.md)를 참조하세요.

### 🌐 WebSocket 통합 강화

거래소 중립적 통합 WebSocket 관리 시스템으로 실시간 데이터 처리를 강화합니다.

#### 핵심 기능
- **UnifiedWebSocketManager**: Public/Private WebSocket 연결 통합 관리
- **WebSocketConnectorFactory**: 팩토리 패턴으로 거래소별 커넥터 생성
- **PublicWebSocketHandler**: 실시간 가격 데이터 정규화 및 캐싱
- **연결 풀링**: 리소스 효율화를 위한 커넥터 재사용
- **자동 재연결**: 연결 끊김 시 자동 복구

#### 지원 거래소
- **Binance**: Public/Private WebSocket 지원
- **Bybit**: Public/Private WebSocket 지원
- **Upbit**: Public WebSocket 지원 (향후 Private 확장 예정)
- **Bithumb**: Public WebSocket 지원 (향후 Private 확장 예정)

#### 사용 방법
```python
from app.services.unified_websocket_manager import UnifiedWebSocketManager

# 매니저 초기화
ws_manager = UnifiedWebSocketManager(app)

# Public 연결 생성 (실시간 가격 데이터)
connection = await ws_manager.create_public_connection(
    exchange="binance",
    symbols=["BTCUSDT", "ETHUSDT"],
    connection_type=ConnectionType.PUBLIC_PRICE_FEED
)

# Private 연결 생성 (주문 실행 알림)
private_connection = await ws_manager.create_private_connection(
    account=trading_account,
    connection_type=ConnectionType.PRIVATE_ORDER_EXECUTION
)
```

#### 연결 유형
- `PUBLIC_PRICE_FEED`: 실시간 가격 데이터 구독
- `PRIVATE_ORDER_EXECUTION`: 주문 실행 상태 실시간 알림
- `PUBLIC_ORDER_BOOK`: 실시간 오더북 데이터 (향후 지원)
- `PRIVATE_POSITION_UPDATE`: 포지션 변경 실시간 알림 (향후 지원)

#### 데이터 정규화
거래소별 다양한 가격 데이터 형식을 표준 `PriceQuote`로 통합:
```python
# Binance/Bybit 데이터 → PriceQuote
PriceQuote(
    exchange="binance",
    symbol="BTCUSDT",
    price=50000.00,
    timestamp=1640995200000,
    volume=1000.0,
    change_24h=2.5
)
```

#### 장점
- **통합 관리**: 단일 인터페이스로 모든 WebSocket 연결 관리
- **거래소 중립성**: 새로운 거래소 쉽게 추가 가능
- **성능 최적화**: 연결 풀링과 캐싱으로 효율적인 리소스 사용
- **안정성**: 자동 재연결과 에러 처리로 높은 안정성
- **표준화**: 일관된 데이터 형식으로 애플리케이션 단순화

자세한 내용은 [WebSocket 통합 강화 문서](docs/features/websocket-integration-enhancement.md)를 참조하세요.

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
