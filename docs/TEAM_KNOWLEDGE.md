# Team Knowledge Base

> **목적**: 팀원 간 지식을 공유하고, 신규 개발자 온보딩을 가속화하며, "금지 코드 영역"을 방지합니다.
> AI가 코드를 생성할 때도 이 지식을 참조하여 팀 컨텍스트를 유지해야 합니다.

**문제 방지**: Team Collaboration Collapse (Problem #5) - 코드 리뷰 불가, 온보딩 지연, 기술 부채 폭발

---

## 📋 목차

1. [Critical Code Areas](#critical-code-areas)
2. [Onboarding Guide](#onboarding-guide)
3. [Common Gotchas](#common-gotchas)
4. [Development Workflow](#development-workflow)
5. [Troubleshooting Guide](#troubleshooting-guide)
6. [Team Contacts](#team-contacts)

---

## 🔥 Critical Code Areas

> 수정 전 반드시 팀과 논의가 필요한 코드 영역

### 1. Trading Execution Core (core.py)

**파일**: `web_server/app/services/trading/core.py`  
**Owner**: @team (전체 팀 공유)  
**Complexity**: ⭐⭐⭐⭐⭐ (매우 높음)  
**Touch Carefully**: ⚠️ YES - 실제 돈이 오가는 핵심 로직

**Description**:
- 거래소에 실제 주문을 전송하는 핵심 엔진
- 멀티 계좌 동시 주문 처리
- 자본 배분 및 수량 계산

**Before Modifying**:
1. 변경 내용을 팀 전체와 공유
2. 로컬 환경에서 충분히 테스트
3. Staging 환경에 24시간 soak test
4. 거래 금액을 소액으로 제한하고 Production 배포
5. 실시간 모니터링하며 1시간 관찰

**Common Gotchas**:
- 동시성 문제: 같은 심볼에 대한 여러 주문이 동시에 들어올 수 있음
- 거래소 API 제한: Rate limit 초과 시 계정 일시 정지
- 수량 소수점 처리: 거래소마다 소수점 자릿수 제한이 다름
- 잔고 부족 처리: 일부 계좌는 성공, 일부는 실패할 수 있음

**Refactoring Safety**: `@REFACTOR-SAFE:caution,mission-critical`

---

### 2. Order Queue System (order_queue_manager.py)

**파일**: `web_server/app/services/trading/order_queue_manager.py`  
**Owner**: @team  
**Complexity**: ⭐⭐⭐⭐ (높음)  
**Touch Carefully**: ⚠️ YES - 주문 손실 위험

**Description**:
- OpenOrder / PendingOrder 간 동적 전환
- 우선순위 기반 재정렬 알고리즘
- 거래소 최대 심볼 수 제한 대응 (Binance: 200개)

**Before Modifying**:
1. `docs/features/order-queue-system.md` 완독
2. 재정렬 알고리즘 이해 (priority → sort_price → created_at)
3. 테스트: 200개 이상의 주문으로 스트레스 테스트
4. 주문 손실이 없는지 확인 (OpenOrder + PendingOrder 총합 불변)

**Common Gotchas**:
- 재정렬 중 새 주문 추가: Race condition 가능
- 우선순위 중복: sort_price와 created_at으로 안정적 정렬 보장
- 거래소 제한 변경: Binance는 200개, Bybit는 500개 등 거래소마다 다름
- 큐 비우기: 재정렬 중 모든 주문 취소 시 상태 불일치 가능

**Refactoring Safety**: `@REFACTOR-SAFE:caution,complex-algorithm`

---

### 3. Webhook Processing (webhook.py, webhook_service.py)

**파일**: 
- `web_server/app/routes/webhook.py`
- `web_server/app/services/webhook_service.py`

**Owner**: @team  
**Complexity**: ⭐⭐⭐ (중간)  
**Touch Carefully**: 🟡 MODERATE - 외부 의존성 높음

**Description**:
- TradingView 웹훅 수신 및 파싱
- 전략 토큰 검증
- 주문 파라미터 정규화

**Before Modifying**:
1. TradingView 웹훅 메시지 포맷 확인 (`docs/webhook_message_format.md`)
2. 테스트 전략 (`test1`) 사용하여 검증
3. WebhookLog 테이블에서 최근 웹훅 샘플 확인

**Common Gotchas**:
- TradingView는 재시도하지 않음: 실패 시 주문 손실
- 토큰 검증 실패 시 로그 남기지만 알림 없음: 조용히 실패
- 배치 주문 파싱: JSON 배열 vs 단일 객체 혼동 주의
- 타임아웃: 5초 내 응답 필수 (TradingView 제한)

**Refactoring Safety**: `@REFACTOR-SAFE:safe,well-tested`

---

### 4. Exchange Integration (exchanges/)

**파일**: `web_server/app/exchanges/`  
**Owner**: @team  
**Complexity**: ⭐⭐⭐⭐ (높음)  
**Touch Carefully**: ⚠️ YES - 실제 API 호출

**Description**:
- Binance, Bybit, 한국투자증권 어댑터
- Unified Exchange Interface 구현
- API 에러 처리 및 재시도 로직

**Before Modifying**:
1. 각 거래소 API 문서 읽기 (`docs/` 디렉토리)
2. Testnet 계정으로 먼저 테스트
3. API 키 권한 확인 (주문 생성, 조회, 취소 권한 필요)
4. Rate Limit 확인 (거래소마다 다름)

**Common Gotchas**:
- ccxt 라이브러리 버전: 업데이트 시 API 변경 가능
- 한국투자증권 토큰 갱신: 2시간마다 자동 갱신 필요 (스케줄러에서 처리)
- Symbol 포맷: Binance "BTC/USDT", 한투 "005930" (삼성전자)
- 주문 상태: 거래소마다 상태 이름이 다름 (Filled, Closed, Executed 등)

**Refactoring Safety**: `@REFACTOR-SAFE:caution,external-dependencies`

---

### 5. Database Schema (models.py)

**파일**: `web_server/app/models.py`  
**Owner**: @team  
**Complexity**: ⭐⭐⭐ (중간)  
**Touch Carefully**: ⚠️ YES - 스키마 변경 위험

**Description**:
- SQLAlchemy ORM 모델 정의
- Strategy, Account, OpenOrder, PendingOrder, Trade, Position 등

**Before Modifying**:
1. Alembic 마이그레이션 생성 필수
2. 기존 데이터 마이그레이션 스크립트 작성
3. Staging 환경에서 마이그레이션 테스트
4. 롤백 계획 준비

**Common Gotchas**:
- Foreign Key 제약: 삭제 시 연쇄 삭제 주의 (CASCADE 설정 확인)
- 인덱스: 쿼리 성능을 위해 적절한 인덱스 필수
- Nullable 필드: 기존 데이터가 있는 상태에서 NOT NULL 추가 시 실패
- Relationship 양방향: backref 설정 시 순환 참조 주의

**Refactoring Safety**: `@REFACTOR-SAFE:breaking-change-risk`

---

## 🎓 Onboarding Guide

> 신규 개발자를 위한 Week-by-Week 가이드

### Week 1: Understanding the System

**목표**: 시스템 전체 구조 파악

**Day 1-2: 문서 읽기**
- [ ] `README.md` 읽기
- [ ] `docs/ARCHITECTURE.md` 읽기
- [ ] `CLAUDE.md` 개발 가이드라인 읽기
- [ ] 이 파일 (TEAM_KNOWLEDGE.md) 읽기

**Day 3-4: 로컬 환경 설정**
- [ ] Python 가상환경 생성
- [ ] 의존성 설치 (`pip install -r requirements.txt`)
- [ ] PostgreSQL Docker 컨테이너 실행
- [ ] 데이터베이스 마이그레이션 (`flask db upgrade`)
- [ ] 개발 서버 실행 (`python run.py restart`)

**Day 5: 코드 탐색**
- [ ] `web_server/app/__init__.py` - Flask 앱 초기화
- [ ] `web_server/app/models.py` - 데이터베이스 모델
- [ ] `web_server/app/routes/webhook.py` - 웹훅 엔드포인트
- [ ] `web_server/app/services/trading/core.py` - 거래 실행 엔진

**Check Point**: 개발 서버를 실행하고 웹훅 테스트를 성공적으로 완료

---

### Week 2: First Contribution

**목표**: 첫 Pull Request 제출

**Day 1-2: Good First Issue 찾기**
- GitHub Issues에서 "good-first-issue" 라벨 찾기
- 없으면 문서 개선, 테스트 추가 등 선택

**Day 3-4: 구현**
- [ ] 브랜치 생성 (`git checkout -b feature/your-feature`)
- [ ] 코드 작성
- [ ] 태그 추가 (`@FEAT:`, `@COMP:`, `@TYPE:` 등)
- [ ] Docstring 작성
- [ ] 테스트 작성

**Day 5: Pull Request**
- [ ] Code Review Checklist 자가 점검 (`docs/CODE_REVIEW_TEMPLATE.md`)
- [ ] PR 제출
- [ ] 팀원과 Pair Programming으로 리뷰

**Check Point**: PR이 승인되고 머지됨

---

### Week 3-4: Domain Expertise

**목표**: 특정 도메인 전문가 되기

**선택 가능한 도메인**:
1. **Trading Execution**: 주문 실행 엔진
2. **Order Queue System**: 주문 대기열 관리
3. **Exchange Integration**: 거래소 API 통합
4. **Webhook Processing**: 외부 시그널 수신

**학습 방법**:
- 해당 도메인 코드 정독
- `docs/features/` 디렉토리에서 상세 문서 읽기
- 기존 버그 수정하며 동작 방식 이해
- 팀원에게 질문하며 도메인 지식 습득

**Check Point**: 해당 도메인 코드 리뷰 가능한 수준

---

## 💡 Common Gotchas

> 자주 실수하는 부분과 해결 방법

### 1. APScheduler 중복 실행

**문제**: 개발 환경에서 백그라운드 작업이 2번씩 실행됨

**원인**: Flask Reloader가 프로세스를 2번 시작 (main + reloader)

**해결**:
```python
# app/__init__.py
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    # 스케줄러 시작 (1회만 실행)
    scheduler.start()
```

**확인 방법**:
```bash
grep "APScheduler 시작됨" web_server/logs/app.log
# 한 번만 출력되어야 함
```

---

### 2. 거래소 Symbol 포맷 불일치

**문제**: Binance는 "BTC/USDT", 한투는 "005930" - Symbol 포맷이 다름

**원인**: 거래소마다 Symbol 표기 방식이 다름

**해결**:
```python
# Use exchange_format_symbol() in exchange adapters
binance_symbol = "BTC/USDT"  # Unified format
korea_investment_symbol = "005930"  # Specific format
```

**Tip**: 데이터베이스에는 Unified Format으로 저장, 거래소 API 호출 시 변환

---

### 3. 잔고 부족 시 일부 계좌만 실패

**문제**: 멀티 계좌 주문 시 일부는 성공, 일부는 실패

**원인**: 계좌별 잔고가 다름, 원자적 트랜잭션 아님

**해결**:
- 사전에 잔고 확인 (`fetch_balance()`)
- 실패한 계좌는 에러 로그에 기록
- 성공한 주문은 그대로 유지 (롤백하지 않음)
- 텔레그램 알림으로 실패 계좌 통지

---

### 4. 주문 체결 확인 지연

**문제**: 주문 생성 후 즉시 포지션 조회 시 반영 안 됨

**원인**: 거래소 API가 비동기적으로 체결 처리

**해결**:
- `monitor_order_fills` 백그라운드 작업이 10초마다 체결 확인
- 즉시 반영이 필요한 경우 WebSocket 사용 고려
- UI에서는 SSE 이벤트 수신하여 실시간 업데이트

---

### 5. 테스트 환경 vs Production 차이

**문제**: 로컬에서는 되는데 Production에서 안 됨

**원인**: 환경 변수, 네트워크, 데이터베이스 설정 차이

**해결 체크리스트**:
- [ ] `.env` 파일 설정 확인
- [ ] 거래소 API 키가 Production 계정인지 확인
- [ ] Nginx SSL 설정 확인 (HTTPS 필수)
- [ ] 방화벽 설정 확인 (거래소 IP 화이트리스트)
- [ ] 데이터베이스 마이그레이션 완료 확인

---

## 🔧 Development Workflow

### 일반적인 개발 사이클

```bash
# 1. 최신 코드 받기
git pull origin main

# 2. 브랜치 생성
git checkout -b feature/your-feature-name

# 3. 코드 작성
# - 파일 수정
# - 태그 추가 (@FEAT:, @COMP:, @TYPE: 등)
# - Docstring 작성

# 4. 로그 정리 (깨끗한 테스트를 위해)
rm -rf web_server/logs/*

# 5. 서버 재시작
python run.py restart

# 6. 테스트
sleep 3  # 서버 시작 대기
# 웹훅 테스트 또는 UI 테스트

# 7. 로그 확인
tail -f web_server/logs/app.log

# 8. 커밋
git add .
git commit -m "feat: your feature description"

# 9. Push
git push origin feature/your-feature-name

# 10. Pull Request 생성
# GitHub에서 PR 생성
```

### 코드 리뷰 요청 전 체크리스트

```bash
# 1. Linter 실행
flake8 web_server/app/

# 2. 서비스 의존성 검증
python scripts/check_service_dependencies.py

# 3. 태그 확인
grep -r "@FEAT:" your_modified_files.py
grep -r "@COMP:" your_modified_files.py
grep -r "@TYPE:" your_modified_files.py

# 4. 테스트 실행
pytest tests/

# 5. Code Review Template 자가 점검
# docs/CODE_REVIEW_TEMPLATE.md 참조
```

---

## 🆘 Troubleshooting Guide

### 문제: 주문이 실행되지 않음

**Debug Steps**:
1. 로그 확인:
   ```bash
   tail -f web_server/logs/app.log | grep ERROR
   ```

2. 전략 활성화 확인:
   ```sql
   SELECT id, name, is_active FROM strategy WHERE id = YOUR_STRATEGY_ID;
   ```

3. 계좌 연결 확인:
   ```sql
   SELECT * FROM strategy_account WHERE strategy_id = YOUR_STRATEGY_ID;
   ```

4. 웹훅 로그 확인:
   ```sql
   SELECT * FROM webhook_log ORDER BY created_at DESC LIMIT 10;
   ```

5. API 키 유효성 확인:
   - 거래소 웹사이트에서 API 키 권한 확인
   - Testnet vs Production 확인

---

### 문제: 스케줄러가 동작하지 않음

**Debug Steps**:
1. 스케줄러 시작 확인:
   ```bash
   grep "APScheduler 시작됨" web_server/logs/app.log
   # 1번만 출력되어야 함
   ```

2. 작업 등록 확인:
   ```bash
   grep "Job added" web_server/logs/app.log
   ```

3. 실행 로그 확인:
   ```bash
   grep "rebalance_order_queue" web_server/logs/app.log
   grep "monitor_order_fills" web_server/logs/app.log
   ```

4. 환경 변수 확인:
   ```bash
   echo $WERKZEUG_RUN_MAIN  # 'true'여야 함
   ```

---

### 문제: Database Connection 에러

**Debug Steps**:
1. PostgreSQL 상태 확인:
   ```bash
   docker-compose ps postgres
   ```

2. 연결 테스트:
   ```bash
   psql -h localhost -U trader -d trading_system
   ```

3. 환경 변수 확인:
   ```bash
   echo $DATABASE_URL
   # postgresql://trader:password123@localhost:5432/trading_system
   ```

4. 마이그레이션 상태 확인:
   ```bash
   cd web_server
   flask db current
   flask db upgrade
   ```

---

## 👥 Team Contacts

### Code Ownership

| Domain | Owner | Contact |
|--------|-------|---------|
| **Trading Core** | @team | team@example.com |
| **Order Queue** | @team | team@example.com |
| **Webhook** | @team | team@example.com |
| **Exchange Integration** | @team | team@example.com |
| **Frontend/UI** | @team | team@example.com |
| **DevOps/Infrastructure** | @team | team@example.com |

### Communication Channels

- **Slack**: #trading-system-dev
- **GitHub**: Issues & Pull Requests
- **Email**: team@example.com
- **Emergency**: [Contact CTO]

---

## 📚 Additional Resources

### Essential Documents
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 시스템 아키텍처
- [NAMING_DICTIONARY.md](./NAMING_DICTIONARY.md) - 네이밍 규칙
- [CODE_REVIEW_TEMPLATE.md](./CODE_REVIEW_TEMPLATE.md) - 코드 리뷰 체크리스트
- [CLAUDE.md](../CLAUDE.md) - 개발 가이드라인

### Feature Documentation
- [Webhook Order Processing](./features/webhook-order-processing.md)
- [Order Queue System](./features/order-queue-system.md)
- [Background Scheduler](./features/background-scheduler.md)
- [Exchange Integration](./features/exchange-integration.md)

---

## 🔄 Document Updates

이 문서는 팀 지식이 변경될 때마다 업데이트해야 합니다:

- 새로운 Critical Code Area 추가
- Gotcha 발견 시 즉시 기록
- Onboarding 과정에서 개선점 발견 시 반영
- 팀원 변경 시 Contact 정보 업데이트

**Last Updated**: 2025-10-10  
**Maintained by**: @team

---

*이 문서를 통해 "아무도 이 코드를 이해하지 못한다"는 상황을 방지하고, 팀 전체가 코드베이스에 대한 지식을 공유합니다.*

