# 시스템 아키텍처

## 개요

암호화폐 자동 거래 시스템은 Flask 웹 프레임워크를 기반으로 한 모놀리식 아키텍처로 구성되어 있습니다. 시스템은 MVC 패턴을 따르며, 서비스 레이어를 통해 비즈니스 로직을 분리하여 유지보수성과 확장성을 높였습니다.

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Client Layer                              │
├─────────────────────────────────────────────────────────────────────┤
│  Web Browser  │  WebSocket Client  │  Webhook Client  │  Telegram  │
└───────┬───────┴─────────┬──────────┴────────┬─────────┴─────┬──────┘
        │                 │                   │               │
        ▼                 ▼                   ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Application Layer                            │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │   Routes    │  │  WebSocket   │  │   Webhook    │  │ Telegram│ │
│  │(Blueprints) │  │   Manager    │  │   Handler    │  │   Bot   │ │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘  └────┬────┘ │
│         │                │                  │                │      │
│         ▼                ▼                  ▼                ▼      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     Service Layer                            │  │
│  ├──────────────────────────────────────────────────────────────┤  │
│  │ Exchange │ Trading │ Position │ Strategy │ Analytics │ Event │  │
│  │ Service  │ Service │ Service  │ Service  │  Service  │Service│  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────┬────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Data Layer                                   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │  SQLAlchemy  │  │     Cache      │  │   Background Jobs    │ │
│  │   (Models)   │  │  (In-Memory)   │  │   (APScheduler)      │ │
│  └──────┬───────┘  └────────────────┘  └────────────────────────┘ │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────┐                                                  │
│  │   Database   │                                                  │
│  │   (SQLite/   │                                                  │
│  │  PostgreSQL) │                                                  │
│  └──────────────┘                                                  │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     External Services                               │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│  │   Binance   │  │    Bybit    │  │     OKX     │  │ Telegram  │ │
│  │     API     │  │     API     │  │     API     │  │    API    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## 레이어별 상세 설명

### 1. Client Layer (클라이언트 레이어)

#### Web Browser
- **역할**: 사용자 인터페이스 제공
- **기술**: HTML5, CSS3, JavaScript
- **특징**: 
  - Bootstrap 5 기반 반응형 디자인
  - 실시간 WebSocket 연결
  - Light/Dark 테마 지원

#### WebSocket Client
- **역할**: 실시간 가격 업데이트
- **구현**: 
  - `websocket-manager.js`: WebSocket 연결 관리
  - `position-realtime-manager.js`: 포지션 실시간 업데이트
  - 거래소별 WebSocket 핸들러 (binance, bybit, okx)

#### Webhook Client
- **역할**: 외부 시스템에서 거래 시그널 전송
- **형식**: HTTP POST 요청
- **인증**: Strategy-specific token

#### Telegram
- **역할**: 알림 및 리포트 수신
- **기능**: 거래 알림, 일일 리포트, 오류 알림

### 2. Application Layer (애플리케이션 레이어)

#### Routes (Blueprint 구조)
```
routes/
├── auth.py      # 인증 관련 라우트
├── admin.py     # 관리자 기능
├── accounts.py  # 거래소 계정 관리
├── strategies.py # 전략 관리
├── positions.py # 포지션 관리
├── capital.py   # 자본 관리
├── dashboard.py # 대시보드 API
├── webhook.py   # 웹훅 처리
└── system.py    # 시스템 관리
```

각 Blueprint는 관련 기능을 모듈화하여 관리합니다:
- **인증 체크**: `@login_required` 데코레이터
- **권한 관리**: `@admin_required` 데코레이터
- **CSRF 보호**: 자동 적용

#### WebSocket Manager
- **실시간 가격 스트리밍**: 거래소 WebSocket API 연결
- **자동 재연결**: 연결 실패 시 자동 복구
- **멀티플렉싱**: 여러 심볼 동시 구독

#### Webhook Handler
- **시그널 수신**: POST `/webhook/<strategy_key>`
- **검증**: Strategy key 확인
- **처리**: Trading Service로 전달

### 3. Service Layer (서비스 레이어)

비즈니스 로직을 캡슐화하여 재사용성과 테스트 용이성을 높입니다.

#### Exchange Service (`exchange_service.py`)
```python
class ExchangeService:
    - initialize_exchange()  # 거래소 연결 초기화
    - get_balance()         # 잔고 조회
    - get_positions()       # 포지션 조회
    - get_open_orders()     # 미체결 주문 조회
    - get_precision()       # 거래 정밀도 조회
```

#### Trading Service (`trading_service.py`)
```python
class TradingService:
    - process_webhook_signal()  # 웹훅 시그널 처리
    - execute_order()          # 주문 실행
    - calculate_order_size()   # 주문 수량 계산
    - manage_risk()           # 리스크 관리
```

#### Position Service (`position_service.py`)
```python
class PositionService:
    - get_all_positions()      # 전체 포지션 조회
    - update_position()        # 포지션 업데이트
    - close_position()         # 포지션 청산
    - calculate_pnl()          # 손익 계산
```

#### Strategy Service (`strategy_service.py`)
```python
class StrategyService:
    - create_strategy()        # 전략 생성
    - update_strategy()        # 전략 수정
    - get_active_strategies()  # 활성 전략 조회
    - validate_signal()        # 시그널 검증
```

### 4. Data Layer (데이터 레이어)

#### Models (SQLAlchemy ORM)
```python
# 주요 모델 구조
User                # 사용자 정보
Account             # 거래소 계정
Strategy            # 거래 전략
StrategyAccount     # 전략-계정 연결
StrategyCapital     # 자본 배분
StrategyPosition    # 가상 포지션
Trade               # 거래 내역
OpenOrder           # 미체결 주문
WebhookLog          # 웹훅 로그
DailyAccountSummary # 일일 요약
```

#### Cache Layer
- **용도**: 거래소 정밀도 정보 캐싱
- **구현**: In-memory dictionary
- **관리**: APScheduler로 주기적 정리

#### Background Jobs (APScheduler)
```python
# 스케줄된 작업
1. update_order_statuses()     # 30초마다
2. update_unrealized_pnl()     # 5분마다
3. send_daily_summary()        # 매일 21:00
4. clean_precision_cache()     # 1시간마다
```

### 5. External Services (외부 서비스)

#### 거래소 API (CCXT)
- **Binance**: Spot/Futures 거래
- **Bybit**: Derivatives 거래
- **OKX**: 다양한 거래 상품
- **통합**: CCXT 라이브러리로 API 통합

#### Telegram Bot API
- **알림**: 거래 실행, 오류 발생
- **리포트**: 일일 거래 요약
- **명령**: 봇 명령어 처리

## 데이터 흐름

### 1. 웹훅 시그널 처리 흐름
```
Webhook Client → Webhook Route → Trading Service → Exchange Service → Exchange API
                                        ↓
                                 Position Service
                                        ↓
                                  Database Update
                                        ↓
                                 Telegram Notification
```

### 2. 실시간 가격 업데이트 흐름
```
Exchange WebSocket → WebSocket Manager → Browser WebSocket Client → UI Update
```

### 3. 포지션 조회 흐름
```
Browser → Position Route → Position Service → Exchange Service → Exchange API
                                    ↓
                              Database Cache
                                    ↓
                              Response to Browser
```

## 보안 아키텍처

### 인증 및 권한
- **사용자 인증**: Flask-Login 세션 기반
- **비밀번호**: bcrypt 해싱
- **권한 레벨**: 일반 사용자, 관리자

### API 보안
- **CSRF 보호**: Flask-WTF CSRF 토큰
- **API 키 암호화**: 데이터베이스 저장 시 암호화
- **웹훅 인증**: Strategy-specific key

### 네트워크 보안
- **HTTPS**: 프로덕션 환경 필수
- **CORS**: 필요시 설정
- **Rate Limiting**: 거래소 API 제한 준수

## 확장성 고려사항

### 수평 확장
- **무상태 설계**: 세션 외부 저장 가능
- **로드 밸런싱**: 여러 인스턴스 실행 가능
- **데이터베이스**: PostgreSQL/MySQL로 확장

### 수직 확장
- **비동기 처리**: Celery 추가 가능
- **캐싱**: Redis 도입 가능
- **모니터링**: Prometheus/Grafana 연동

### 마이크로서비스 전환
- **서비스 분리**: Service Layer 기반 분리 용이
- **API Gateway**: 별도 구현 가능
- **메시지 큐**: RabbitMQ/Kafka 도입 가능

## 모니터링 및 로깅

### 로깅 시스템
```python
# 환경별 로깅 레벨
- 개발 환경: DEBUG (모든 로그 출력)
- 프로덕션 환경: INFO (사용자 액션), WARNING (백그라운드 작업)

# 로거 구분
- app.logger: 애플리케이션 메인 로거 (사용자 요청 처리)
- trading_system.background: 백그라운드 작업 전용 로거 (스케줄러)

# 로그 파일
- app.log: 통합 로그 파일 (RotatingFileHandler, 10MB 단위)
```

### 백그라운드 작업 로깅 최적화
- **스케줄러 작업**: 일반적인 완료 메시지는 DEBUG 레벨
- **오류 상황**: ERROR/WARNING 레벨로 중요 이벤트만 기록
- **사용자 액션**: INFO 레벨로 거래 실행 등 중요 액션 기록

### 모니터링 포인트
- **시스템 상태**: 백그라운드 작업 상태
- **거래 모니터링**: 주문 실행, 포지션 변화
- **오류 추적**: 예외 발생, API 오류
- **성능 지표**: 응답 시간, 처리량

## 개발 및 배포

### 개발 환경
- **로컬 개발**: SQLite, Flask 개발 서버
- **테스트**: pytest, 격리된 테스트 DB
- **디버깅**: Flask 디버그 모드

### 프로덕션 배포
- **웹 서버**: Gunicorn/uWSGI
- **리버스 프록시**: Nginx
- **데이터베이스**: PostgreSQL/MySQL
- **프로세스 관리**: systemd/supervisor

### CI/CD 파이프라인 (권장)
```
Git Push → GitHub Actions → 테스트 실행 → Docker 빌드 → 배포
```

## 성능 최적화

### 데이터베이스 최적화
- **인덱스**: 자주 조회하는 컬럼
- **쿼리 최적화**: N+1 문제 해결
- **연결 풀링**: SQLAlchemy 설정

### 캐싱 전략
- **정밀도 캐시**: 거래소 정보 캐싱
- **세션 캐시**: Redis 도입 고려
- **정적 파일**: CDN 활용

### 비동기 처리
- **백그라운드 작업**: APScheduler 활용
- **웹훅 처리**: 큐 시스템 도입 고려
- **대량 데이터**: 배치 처리