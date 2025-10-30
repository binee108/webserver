# Worktree Service Conflict Resolution

@FEAT:worktree-conflict-resolution @COMP:service @TYPE:core

## 개요

여러 git worktree 환경에서 작업 시, 포트 충돌을 **동적 포트 재할당**으로 자동 해결하여 각 워크트리가 독립적으로 실행되도록 합니다.
메인 프로젝트와 워크트리는 동시에 실행 가능하며, 각각 자신의 포트 범위를 할당받습니다.

## 배경

### 이전 방식의 문제점
- 여러 worktree에서 동시에 `python run.py start` 실행 불가능
- 포트 충돌 시 다른 경로의 서비스 강제 종료 필요
- 사용자가 어느 워크트리의 서비스가 실행 중인지 추적하기 어려움

### 현재 해결책: 동적 포트 할당
- 메인 프로젝트: 표준 포트 사용 (443, 5001, 5432)
- 각 워크트리: 고유한 포트 범위 할당 (프로젝트명 해시 기반)
- 동시 실행 가능: 메인 + 최대 98개 워크트리

### 포트 할당 범위
- **HTTPS**: 4431-4529 (worktree 환경)
- **HTTP**: 5002-5100 (worktree 환경)
- **PostgreSQL**: 5433-5531 (worktree 환경)

## 적용 범위

이 기능은 다음 명령어에서 자동으로 작동합니다:
- `python run.py start` - 시스템 시작 (동적 포트 할당)
- `python run.py restart` - 시스템 재시작 (포트 재확인)

워크트리 감지 및 포트 할당 프로세스:
1. 현재 경로 확인 (`.worktree/` 패턴 감지)
2. 워크트리면 동적 포트 할당, 메인이면 표준 포트 사용
3. 할당된 포트를 `.env.local`에 저장 (재시작 시 일관성 유지)
4. 모든 필수 포트 가용성 확인
5. 서비스 시작

## 기능 설명

### 1. 워크트리 환경 감지
`_detect_worktree_environment()` 메서드 (StartCommand):
- 현재 경로에서 `.worktree/` 문자열 감지
- 워크트리 환경이면 True, 메인 프로젝트면 False 반환
- 경로: `cli/commands/start.py:61-72`

### 2. 동적 포트 할당
`_allocate_ports_dynamically()` 메서드:

**우선순위**:
1. `.env.local`에 저장된 이전 할당 포트 (존재하고 사용 가능하면 재사용)
2. 프로젝트명 해시 기반 포트 (`_calculate_hash_port()`)
3. 포트 범위 내 순차 검색 (충돌 시 다음 가용 포트)
4. 범위 소진 → `PortAllocationError` 발생

**해시 기반 포트 계산**:
```python
def _calculate_hash_port(project_name, start_port, end_port):
    port_range = end_port - start_port
    hash_offset = abs(hash(project_name)) % port_range
    return start_port + hash_offset
```
- 같은 프로젝트명은 항상 동일 포트 할당
- 예: `webserver_feature-x` → 항상 5042 (hash 기반)

**경로**: `cli/commands/start.py:251-320`

### 3. 메인 프로젝트 DB 복사 (Worktree 환경)
`copy_main_db_to_worktree()` 메서드 (DockerHelper):

@FEAT:worktree-db-copy @COMP:service @TYPE:core

워크트리에서 `python run.py start` 실행 시:
1. 메인 프로젝트의 `postgres_data/` 디렉토리 위치 파악
2. 기존 워크트리 DB 제거 (매번 최신 상태 유지)
3. 메인 DB를 워크트리로 Bind Mount 방식으로 복사

**복사 전략**:
- `shutil.copytree()`: 디렉토리 전체 복사 (Named Volume 방식에서 변경)
- `symlinks=False`: 심볼릭 링크 공격 방지
- `copy_function=shutil.copy2`: 메타데이터 보존
- 복사 시간: ~30초 (5GB DB 기준)

**경로**: `cli/helpers/docker.py:325-494`

## 사용 예시

### 시나리오 1: 메인 프로젝트에서 시작

```bash
cd /Users/binee/Desktop/quant/webserver
python run.py start

# 출력:
# ============================================================
# 암호화폐 트레이딩 시스템 CLI
# ============================================================
#
# ℹ️  시스템 요구사항 확인 중...
# ✅ Docker 확인: Docker version 24.0.0
# ✅ Docker Compose 확인: Docker Compose version v2.20.0
# ✅ Docker 서비스 실행 중
#
# ============================================================
# ℹ️  현재 경로에서 서비스 시작: /Users/binee/Desktop/quant/webserver
# ============================================================
#
# ℹ️  PostgreSQL 데이터베이스 시작 중...
# ℹ️  PostgreSQL 준비 대기 중...
# ✅ PostgreSQL 준비 완료!
#
# ℹ️  Flask 애플리케이션 시작 중...
# ✅ 데이터베이스 테이블 자동 생성 준비 완료
#
# ℹ️  Nginx 리버스 프록시 시작 중...
# ✅ 서비스 시작 완료!
```

### 시나리오 2: 워크트리 환경에서 동적 포트 할당

```bash
cd /Users/binee/Desktop/quant/webserver/.worktree/feature-x
python run.py start

# 출력:
# ℹ️  워크트리 환경 감지: feature-x
# ℹ️  동적 포트 할당 중...
# ✅ HTTPS_PORT 할당: 4453
# ✅ APP_PORT 할당: 5025
# ✅ POSTGRES_PORT 할당: 5456
#
# ℹ️  현재 경로에서 서비스 시작: .../webserver/.worktree/feature-x
# ℹ️  메인 프로젝트 DB 복사 중...
# ✅ DB 복사 완료!
#
# ... (서비스 시작)
# ✅ 서비스 시작 완료!
#
# 접속 정보:
#   HTTP: http://localhost:5025
#   HTTPS: https://localhost:4453
```

### 시나리오 3: 메인 + 워크트리 동시 실행

```bash
# Terminal 1: 메인 프로젝트
cd /Users/binee/Desktop/quant/webserver
python run.py start
# → 포트: 443, 5001, 5432 사용

# Terminal 2: 워크트리 (별도 터미널)
cd /Users/binee/Desktop/quant/webserver/.worktree/feature-y
python run.py start
# → 포트: 4442, 5012, 5445 할당 (동시 실행 가능!)

# 두 서비스가 독립적으로 실행되며, 서로 영향을 주지 않음
```

## 구현 세부사항

### StartCommand 메서드 목록

#### 1. `_detect_worktree_environment() -> bool`
**경로**: `cli/commands/start.py:61-72`

워크트리 환경 여부를 `.worktree/` 패턴으로 감지합니다.

```python
def _detect_worktree_environment(self) -> bool:
    try:
        current_path = str(self.root_dir.resolve())
        return '.worktree' in current_path
    except Exception:
        return False
```

#### 2. `_calculate_hash_port(project_name, start_port, end_port) -> int`
**경로**: `cli/commands/start.py:227-249`

프로젝트명의 해시값으로 포트 범위 내 일관된 포트를 계산합니다.

```python
port_range = end_port - start_port
hash_offset = abs(hash(project_name)) % port_range
return start_port + hash_offset
```

#### 3. `_allocate_ports_dynamically(project_name) -> dict`
**경로**: `cli/commands/start.py:251-320`

동적 포트 할당 메서드로, 다음 우선순위로 포트를 결정합니다:

**우선순위**:
1. `.env.local`에 저장된 포트 (존재 + 가용)
2. 해시 기반 포트 (`_calculate_hash_port()`)
3. 범위 내 순차 검색 (충돌 시 다음 포트)
4. 범위 소진 → `PortAllocationError`

**반환값**:
```python
{
    "HTTPS_PORT": 4453,
    "APP_PORT": 5025,
    "POSTGRES_PORT": 5456
}
```

#### 4. `_detect_and_stop_conflicts() -> bool` (DEPRECATED)
**경로**: `cli/commands/start.py:179-225`

**현재 상태**: 하위 호환성을 위해 유지, 실제로는 종료하지 않음.

다른 webserver 프로젝트만 감지하고 정보를 출력하며, 실제 종료는 하지 않습니다.
동적 포트 할당으로 인해 충돌 해결이 자동화되었습니다.

### DockerHelper 메서드

#### 1. `_find_main_project_root() -> Optional[Path]`
**경로**: `cli/helpers/docker.py:325-387`

워크트리에서 메인 프로젝트 루트를 찾습니다.

```
입력: /Users/binee/Desktop/quant/webserver/.worktree/feature-x/
출력: /Users/binee/Desktop/quant/webserver/
```

#### 2. `copy_main_db_to_worktree(worktree_project_name) -> bool`
**경로**: `cli/helpers/docker.py:389-494`

워크트리에서 메인 프로젝트의 `postgres_data/`를 복사합니다.

**복사 전략**:
- `shutil.copytree()`: 디렉토리 전체 복사
- `symlinks=False`: 심볼릭 링크 공격 방지
- `copy_function=shutil.copy2`: 메타데이터 보존

**반환값**:
- `True`: 복사 성공, 메인 DB 없음, 워크트리 아님 (정상 흐름)
- `False`: 권한 오류, 파일 삭제/복사 실패

### 명령어 통합

#### execute() (StartCommand)
**경로**: `cli/commands/start.py:99-177`

1. 배너 및 요구사항 확인
2. 충돌 감지 (`_detect_and_stop_conflicts()`) - 정보 출력만
3. 포트 확인 (`_check_required_ports()`)
4. 워크트리 환경 변수 설정
5. 기존 컨테이너 정리
6. **워크트리면 DB 복사** (`copy_main_db_to_worktree()`)
7. PostgreSQL, Flask, Nginx 시작

## 장점

### 1. 동시 실행 지원
- ✅ 메인 + 최대 98개 워크트리 동시 실행 가능
- ✅ 포트 자동 재할당으로 충돌 방지
- ✅ 프로젝트명 해시 기반 포트로 일관성 보장

### 2. 사용자 편의성
- ✅ 자동 포트 할당 - 명령어 하나로 완료
- ✅ `.env.local`에 저장 - 재시작 시 동일 포트 사용
- ✅ 워크트리 인식 - 자동 DB 복사로 같은 데이터 환경

### 3. 개발 워크플로우 개선
- ✅ 다중 브랜치 동시 개발 가능
- ✅ 브랜치 전환 시 별도 터미널만 열면 됨
- ✅ 각 워크트리가 독립적으로 실행 (서로 영향 없음)

### 4. 안정성
- ✅ 해시 기반 포트로 예측 가능한 할당
- ✅ 심볼릭 링크 공격 방지 (DB 복사 시)
- ✅ 메타데이터 보존으로 권한/타임스탬프 유지

## 제한사항

### 1. 포트 범위 한계
- 워크트리당 약 100개 포트 (HTTPS, APP, PostgreSQL)
- 범위 소진 시 `PortAllocationError` 발생
- 실제로는 최대 98개 워크트리만 동시 실행 가능

### 2. 해시 충돌 가능성 (낮음)
- 프로젝트명이 같으면 동일 포트 할당
- 해시 함수로 인한 충돌 가능 (매우 낮음)
- 순차 검색으로 대체 포트 자동 탐색

### 3. DB 복사 시간
- 첫 시작: ~30초 (5GB DB 기준)
- 매번 메인 DB 복사 (최신 상태 유지)
- 대용량 DB 환경에서 시간 소요 가능

### 4. 메인 프로젝트 DB 의존성
- 워크트리는 메인 프로젝트 DB를 복사하여 사용
- 메인 프로젝트 DB 없으면 초기화된 DB로 시작
- 메인과 워크트리 DB는 독립적 (복사 후 변경사항 미동기)

## 테스트 시나리오

### 테스트 1: 워크트리 포트 할당
```bash
# Setup
cd /Users/binee/Desktop/quant/webserver/.worktree/feature-a
python run.py start
# 확인: 포트 4453, 5025, 5456 할당

# Test: 동일 워크트리에서 재시작
python run.py restart
# 기대 결과: 동일 포트 재할당 (일관성 보장)
```

### 테스트 2: 메인 + 워크트리 동시 실행
```bash
# Terminal 1: 메인 프로젝트
cd /Users/binee/Desktop/quant/webserver
python run.py start
# → 포트: 443, 5001, 5432

# Terminal 2: 워크트리
cd /Users/binee/Desktop/quant/webserver/.worktree/feature-b
python run.py start
# → 포트: 4442, 5012, 5445

# 기대 결과: 두 서비스 동시 실행, 포트 충돌 없음
```

### 테스트 3: 다중 워크트리 동시 실행
```bash
# Terminal 1
cd .worktree/feature-x && python run.py start  # 포트 A

# Terminal 2
cd .worktree/feature-y && python run.py start  # 포트 B

# Terminal 3
cd .worktree/feature-z && python run.py start  # 포트 C

# 기대 결과: 세 워크트리 모두 독립적 포트로 실행
```

### 테스트 4: 메인 DB 복사
```bash
# Setup: 메인 프로젝트 DB 생성
cd /Users/binee/Desktop/quant/webserver
python run.py start
# → DB 초기화, 전략/거래소 설정 추가

# Test: 워크트리에서 시작
cd .worktree/new-feature
python run.py start
# 기대 결과:
# 1. 메인 DB 자동 감지
# 2. postgres_data/ 복사
# 3. 동일한 DB 상태로 시작
```

### 테스트 5: 포트 범위 소진 (극한)
```bash
# 범위: APP_PORT 5002-5100 (99개)
# 최대 99개 워크트리 동시 실행

# 100번째 워크트리 시작
cd .worktree/worktree-100
python run.py start
# 기대 결과: PortAllocationError 발생 및 명확한 오류 메시지
```

### 테스트 6: 권한 오류 (DB 복사 실패)
```bash
# Setup
chmod 000 /Users/binee/Desktop/quant/webserver/postgres_data

# Test
cd .worktree/feature-x
python run.py start
# 기대 결과:
# ❌ 권한 오류 메시지
# ℹ️ 해결 방법: sudo chmod -R 755 postgres_data/
```

## 향후 개선 사항

### 1. 포트 범위 확장
- 현재: 최대 98개 워크트리
- 개선: 포트 범위를 더 많은 값으로 확장 (예: 4400-4999)

### 2. DB 동기화 옵션
```bash
python run.py start --keep-db  # 기존 워크트리 DB 유지
python run.py start --sync-db  # 매 시작 시 메인 DB 동기화
```

### 3. 포트 할당 UI 개선
- 할당된 포트를 파일로 저장 (`.env.worktree`)
- CLI에서 포트 정보 조회 명령어 추가

## 관련 파일 및 라인 번호

### CLI 명령어 체계
- `cli/commands/start.py:61-72` - 워크트리 환경 감지
- `cli/commands/start.py:99-177` - execute() 메인 로직
- `cli/commands/start.py:179-225` - _detect_and_stop_conflicts() (deprecated)
- `cli/commands/start.py:227-249` - _calculate_hash_port()
- `cli/commands/start.py:251-320` - _allocate_ports_dynamically()

### 헬퍼 모듈
- `cli/helpers/docker.py:325-387` - _find_main_project_root()
- `cli/helpers/docker.py:389-494` - copy_main_db_to_worktree()

### 문서
- `docs/FEATURE_CATALOG.md` - 기능 카탈로그 (업데이트 필요)
- `README.md` - 사용자 가이드

## 태그 및 검색

### 기능 태그
```python
# @FEAT:worktree-conflict-resolution @COMP:service @TYPE:core
# @FEAT:worktree-db-copy @COMP:service @TYPE:core
# @FEAT:dynamic-port-allocation @COMP:service @TYPE:core
```

### 검색 명령어
```bash
# 동적 포트 할당 로직
grep -n "_allocate_ports_dynamically\|_calculate_hash_port" cli/commands/start.py

# DB 복사 로직
grep -n "copy_main_db_to_worktree\|_find_main_project_root" cli/helpers/docker.py

# 워크트리 환경 감지
grep -n "_detect_worktree_environment" cli/commands/start.py

# 충돌 감지 (deprecated)
grep -n "_detect_and_stop_conflicts" cli/commands/start.py
```

