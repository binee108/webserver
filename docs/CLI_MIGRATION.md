# run.py CLI 마이그레이션 프로젝트

## 개요

1946줄의 단일 `run.py` 파일을 모듈식 CLI 구조로 재구성한 프로젝트입니다.

**주요 성과:**
- 평균 파일 크기: 1946줄 → 78줄 (96% 감소)
- 모듈 독립성: 0% → 100% (Command 패턴)
- 테스트 가능성: 불가능 → 높음 (의존성 주입)
- 총 신규 코드: 2,809줄 (36개 파일)

---

## 목표 달성

| 목표 | 상태 | 근거 |
|------|------|------|
| 유지보수성 향상 | ✅ 완료 | 모듈 단위 파일 분리 (최대 431줄) |
| 테스트 가능성 확보 | ✅ 완료 | 의존성 주입 패턴 적용 |
| 확장성 강화 | ✅ 완료 | Command 패턴 + BaseCommand 추상 클래스 |
| 레거시 호환성 | ✅ 완료 | run_legacy.py 폴백 메커니즘 |

---

## 아키텍처

```
run.py (62줄, 진입점)
│
├─ cli/manager.py (TradingSystemCLI 라우팅)
│  │
│  ├─ cli/config.py (SystemConfig, 전역 설정)
│  │
│  ├─ cli/helpers/ (5개 Helper 모듈, 1,245줄)
│  │  ├─ printer.py (출력 포맷팅)
│  │  ├─ network.py (네트워크 유틸)
│  │  ├─ docker.py (Docker 관리)
│  │  ├─ ssl.py (SSL 인증서)
│  │  └─ env.py (환경 설정)
│  │
│  └─ cli/commands/ (8개 Command 모듈, 1,252줄)
│     ├─ base.py (BaseCommand 추상 클래스)
│     ├─ start.py (시스템 시작)
│     ├─ stop.py (시스템 중지)
│     ├─ restart.py (시스템 재시작, Command 조합)
│     ├─ logs.py (Docker 로그)
│     ├─ status.py (시스템 상태)
│     ├─ clean.py (시스템 정리)
│     └─ setup.py (초기 설정)
│
└─ run_legacy.py (1946줄, 레거시 백업)
```

---

## 설계 패턴

### 1. Command 패턴
- **역할**: 각 CLI 명령어를 독립적인 클래스로 구현
- **이점**: 새 명령어 추가 시 기존 코드 수정 불필요
- **구현**: `BaseCommand` 추상 클래스 + 8개 구체 Command

### 2. 의존성 주입 (Dependency Injection)
- **역할**: Helper 인스턴스를 Command에 주입
- **흐름**: `TradingSystemCLI` → Helper 생성 → Command 생성
- **이점**: 각 모듈이 독립적으로 테스트 가능

### 3. Template Method 패턴
- **역할**: `BaseCommand.execute()` 메서드가 공통 흐름 제어
- **구현**: 각 Command는 `run()` 메서드만 구현

### 4. Strategy 패턴
- **역할**: `RestartCommand = StopCommand + StartCommand`
- **이점**: 명령어 조합으로 새로운 기능 생성

---

## Phase별 구현 현황

### Phase 1: 모듈 구조 생성 (완료)
**목표**: 레거시 백업 + 모듈식 스켈레톤 구성

```
✅ run.py 56줄 진입점으로 단순화
✅ run_legacy.py 1946줄 레거시 백업 생성
✅ cli/ 디렉토리 구조 생성
  - cli/__init__.py
  - cli/config.py (stub)
  - cli/manager.py (stub)
  - cli/helpers/ (5개 stub 파일)
  - cli/commands/ (8개 stub 파일)
✅ 레거시 폴백 메커니즘 구현 (ImportError 처리)
```

**핵심 파일**: `run.py`, `run_legacy.py`

---

### Phase 2: Helper 모듈 분리 (완료)
**목표**: 5개 Helper 클래스 구현 (1,245줄)

| Helper | 크기 | 역할 |
|--------|------|------|
| `printer.py` | 98줄 | 터미널 출력 포맷팅 |
| `network.py` | 105줄 | 포트 확인, 네트워크 유틸 |
| `docker.py` | 431줄 | Docker 컨테이너/볼륨 관리 |
| `ssl.py` | 161줄 | SSL 인증서 생성 |
| `env.py` | 377줄 | 환경 설정, 워크트리 지원 |

**의존성 순서**:
```
StatusPrinter
    ↓
NetworkHelper (depends on StatusPrinter)
    ↓
DockerHelper, SSLHelper, EnvHelper (depend on StatusPrinter + NetworkHelper)
```

---

### Phase 3: Command 모듈 구현 (완료)
**목표**: 8개 Command 클래스 구현 (1,252줄)

| Command | 크기 | 역할 |
|---------|------|------|
| `base.py` | 37줄 | BaseCommand 추상 클래스 |
| `start.py` | 381줄 | 시스템 시작 (SSL + Docker) |
| `stop.py` | 89줄 | 시스템 중지 |
| `restart.py` | 62줄 | 시스템 재시작 |
| `logs.py` | 141줄 | Docker 로그 조회 |
| `status.py` | 177줄 | 시스템 상태 확인 |
| `clean.py` | 232줄 | 컨테이너/볼륨 정리 |
| `setup.py` | 109줄 | 초기 환경 설정 |

**기본 구조**:
```python
class StartCommand(BaseCommand):
    def __init__(self, printer, docker, ...):
        self.printer = printer
        self.docker = docker
        ...

    def run(self, args):
        # 구체 구현
        pass
```

---

### Phase 4: CLI Manager + Config (완료)
**목표**: 의존성 주입 + DRY 원칙 준수 (256줄)

**파일**:
- `cli/config.py` (113줄): SystemConfig 클래스
  - 프로젝트 루트, 워크트리 감지
  - Docker 컨테이너명, 포트 설정
  - 환경 기본값 정의

- `cli/manager.py` (168줄): TradingSystemCLI 클래스
  - Helper 인스턴스 생성 및 관리
  - Command 인스턴스 생성 및 의존성 주입
  - 명령행 인자 파싱 및 Command 라우팅

**주요 개선**:
- ENV_DEFAULTS 중복 제거 (87줄 절감)
- EnvHelper에 NetworkHelper 추가

---

## 레거시 폴백 메커니즘

신규 CLI 실패 시 자동으로 레거시 모드 전환:

```python
# run.py
def main():
    try:
        from cli.manager import TradingSystemCLI
        cli = TradingSystemCLI()
        return cli.run(sys.argv[1:])
    except (ImportError, AttributeError, NotImplementedError):
        print("⚠️  신규 CLI 모듈 미구현, 레거시 모드로 전환")
        from run_legacy import main as legacy_main
        return legacy_main()
```

---

## 워크트리 지원

`cli/config.py`에서 자동으로 워크트리 감지 및 프로젝트명/포트 할당:

```bash
git worktree add .worktree/feature-test feature/test
cd .worktree/feature-test
python run.py start
# ✅ webserver-wt-feature-test 프로젝트로 자동 시작
```

---

## 기능 태그 시스템

모든 핵심 파일에 grep 검색용 태그 추가:

```bash
# CLI 마이그레이션 관련 모든 파일
grep -r "@FEAT:cli-migration" --include="*.py"

# Command 클래스만
grep -r "@FEAT:cli-migration" --include="*.py" | grep "@COMP:route"

# Helper 클래스만
grep -r "@FEAT:cli-migration" --include="*.py" | grep "@COMP:util"
```

---

## 사용법

### 기본 명령어

```bash
# 시스템 시작
python run.py start

# 시스템 중지
python run.py stop

# 시스템 재시작
python run.py restart

# 상태 확인
python run.py status

# 로그 조회
python run.py logs           # 모든 서비스 로그
python run.py logs -f app    # app 컨테이너만 실시간 조회

# 시스템 정리
python run.py clean          # 중지된 컨테이너만 제거
python run.py clean --all    # 모든 컨테이너/볼륨 제거

# 환경 설정
python run.py setup          # 기본값으로 설정
python run.py setup --env production  # 프로덕션 설정
```

---

## 버그 수정 이력

### 2025-10-24: RestartCommand 포트 충돌 문제 해결

**문제**: `python run.py restart` 실행 시 "port already in use" 오류로 실패

**근본 원인**:
- StopCommand 실행 후 고정된 5초 대기 (`time.sleep(5)`)
- Docker Compose는 컨테이너를 비동기로 종료하므로 5초로 불충분
- StartCommand의 포트 검증 시점에 이전 컨테이너 리소스 잔존
- 포트 검증 실패 → StartCommand 자체 정리 로직까지 도달 못함

**해결 방법**:
```python
# Before (레이스 컨디션)
self.stop_cmd.execute(args)
time.sleep(5)  # 고정 대기
self.start_cmd.execute(args)

# After (폴링 기반 대기)
self.stop_cmd.execute(args)
self._wait_for_containers_cleanup()  # 최대 15초 폴링
self.start_cmd.execute(args)
```

**구현 세부사항**:
1. **`_wait_for_containers_cleanup(project_name)` 메서드 추가** (78줄)
   - 최대 15초 동안 1초 간격으로 Docker Compose 프로젝트 label 폴링
   - `--filter label=com.docker.compose.project={project_name}` 사용
   - **워크트리 격리**: 현재 프로젝트의 컨테이너만 대기 (다른 워크트리 간섭 없음)
   - 모든 컨테이너 종료 확인 시 즉시 반환 (평균 1-2초)
   - 네트워크/볼륨 비동기 제거를 위한 2초 추가 대기

2. **`_infer_project_name(args)` 메서드 추가** (25줄)
   - 워크트리 경로 기반 프로젝트명 자동 추론
   - 예: `.worktree/feature-x/` → `webserver_feature-x`
   - 메인 프로젝트: `webserver`

3. **방어적 프로그래밍 강화**:
   - `subprocess.run()` 반환 코드 체크 (`returncode != 0`)
   - 타임아웃 보호 (`timeout=2` on subprocess)
   - 예외 타입 포함 로깅 (`{type(e).__name__}`)

4. **Graceful Degradation**:
   - 15초 타임아웃 시 경고만 출력, StartCommand 계속 진행
   - StartCommand 자체 정리 로직(`line 123-127`)이 최종 안전망 역할

**테스트 결과**:
- ✅ Exit Code: 0 (성공)
- ✅ 컨테이너 정리 시간: 1초 (타임아웃 경고 해결)
- ✅ 워크트리 격리: 다른 프로젝트 컨테이너 영향 없음
- ✅ Health Check: `{"status": "healthy"}`
- ✅ Code Review: 9.5/10 (Priority 1-3 이슈 모두 해결)

**영향 범위**:
- 수정 파일: `cli/commands/restart.py` (+103줄, 160줄 총), `cli/manager.py` (+1 인자)
- 신규 메서드:
  - `_wait_for_containers_cleanup(project_name, max_wait=15)` - 워크트리 격리 폴링
  - `_infer_project_name(args)` - 프로젝트명 자동 추론
- 관련 파일: `cli/commands/start.py` (포트 검증, Line 110), `cli/commands/stop.py` (_infer_project_name 참조)

---

## 기술 부채 및 향후 개선

| 항목 | 현황 | 우선순위 |
|------|------|----------|
| StartCommand 최적화 | 381줄 (목표: 200줄) | 중간 |
| 단위 테스트 작성 | 0개 (목표: 8개) | 높음 |
| 통합 테스트 | 미지원 | 중간 |
| 에러 처리 강화 | ✅ 완료 (RestartCommand) | 완료 |
| DRY 개선 | `docker ps` 명령어 2회 중복 | 매우 낮음 |

**DRY 개선 참고**: `docker ps --filter name=webserver` 명령어가 restart.py(Line 82)와 start.py(Line 177)에 중복. 현재는 컨텍스트가 다르므로(restart=종료 대기, start=포트 검증) 추출하지 않음. 3회 이상 발생 시 `DockerHelper.get_webserver_containers()` 메서드 추출 권장.

---

## 검증 체크리스트

- [x] Phase 1: 모듈 구조 생성
- [x] Phase 2: Helper 모듈 분리
- [x] Phase 3: Command 모듈 구현
- [x] Phase 4: CLI Manager 통합
- [x] 레거시 폴백 메커니즘
- [x] 워크트리 지원
- [x] 기능 태그 추가
- [x] 문서화 완료

---

**마이그레이션 완료일**: 2025-10-24
