# Worktree Service Conflict Detection & Auto-Resolution

## 개요

여러 git worktree 환경에서 작업 시, 다른 경로에서 실행 중인 서비스를 자동으로 감지하고 안전하게 종료한 후 현재 경로의 서비스를 시작하는 기능입니다.

## 배경

### 문제점
- 여러 worktree에서 동시에 `python run.py start` 실행 시 포트 충돌 발생
- 이미 실행 중인 서비스가 어느 경로에서 시작되었는지 알 수 없음
- 수동으로 다른 경로를 찾아가서 서비스를 종료해야 하는 불편함
- 포트 충돌로 인한 서비스 시작 실패

### 영향을 받는 포트
- **443**: HTTPS (Nginx)
- **5001**: HTTP Flask 앱
- **5432**: PostgreSQL

## 적용 범위

이 기능은 다음 명령어에서 자동으로 작동합니다:
- `python run.py start` - 시스템 시작
- `python run.py restart` - 시스템 재시작
- `python run.py clean` - 시스템 완전 정리

모든 명령어 실행 시 자동으로:
1. 다른 worktree 경로의 실행 중인 서비스 감지
2. 충돌하는 서비스 안전하게 종료
3. 현재 경로에서 명령어 실행

## 기능 설명

### 1. 실행 경로 추적
Docker Compose는 컨테이너에 다음 라벨을 자동으로 추가합니다:
```
com.docker.compose.project.working_dir=/path/to/worktree
com.docker.compose.project=webserver
```

이 라벨을 통해 각 컨테이너가 어느 경로에서 시작되었는지 추적할 수 있습니다.

### 2. 자동 충돌 감지
`check_running_services()` 메서드가 다음을 수행합니다:
1. 모든 실행 중인 Docker 컨테이너 조회
2. 트레이딩 시스템 관련 컨테이너 필터링 (postgres, nginx, app)
3. 현재 경로와 다른 경로의 컨테이너 분류

### 3. 포트 가용성 확인
`check_port_availability()` 메서드가 필수 포트의 사용 여부를 확인합니다:
- 소켓 연결 시도로 포트 사용 여부 테스트
- OS별로 포트 사용 프로세스 정보 제공:
  - Windows: `netstat -ano`
  - macOS: `lsof -i :{port}`
  - Linux: `ss -tulpn`

### 4. 자동 서비스 종료
`stop_other_services()` 메서드가 충돌하는 서비스를 정리합니다:
1. 워킹 디렉토리별로 컨테이너 그룹화
2. 각 디렉토리에서 `docker-compose down --remove-orphans` 실행
3. 디렉토리가 존재하지 않으면 컨테이너 개별 종료
4. 포트 해제를 위한 대기 시간 (3초)

## 사용 예시

### 시나리오 1: 다른 worktree에서 실행 중

```bash
# worktree1에서 서비스 실행
cd /Users/binee/Desktop/quant/webserver
python run.py start
# ✅ 서비스 시작 완료

# worktree2로 이동
cd /Users/binee/Desktop/quant/webserver/.worktree/feature-branch
python run.py start

# 출력:
# ============================================================
# ℹ️  다른 경로의 실행 중인 서비스 확인 중...
# ============================================================
# 
# ⚠️  다른 worktree 경로에서 실행 중인 서비스가 감지되었습니다!
# 
# ⚠️  다른 경로에서 실행 중인 서비스 발견:
#   📂 /Users/binee/Desktop/quant/webserver
#      - webserver-postgres-1
#      - webserver-app-1
#      - webserver-nginx-1
# 
# ℹ️  서비스 종료 중: /Users/binee/Desktop/quant/webserver
# ✅ 서비스 종료 완료: /Users/binee/Desktop/quant/webserver
# ℹ️  포트 해제 대기 중...
# ✅ 다른 경로의 서비스가 성공적으로 종료되었습니다
# 
# ============================================================
# ℹ️  현재 경로에서 서비스 시작: /Users/binee/Desktop/.../feature-branch
# ============================================================
# 
# ... (서비스 시작 계속)
```

### 시나리오 2: 포트 충돌 감지

```bash
python run.py start

# 포트가 이미 사용 중인 경우:
# ⚠️  다음 포트가 이미 사용 중입니다: 443, 5001
# ❌ 충돌하는 프로세스를 종료하거나 포트를 변경해주세요
# 
# 포트 443 사용 정보:
# COMMAND   PID  USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
# nginx   12345  user    6u  IPv4 0x1a2b3c4d      0t0  TCP *:https (LISTEN)
```

## 구현 세부사항

### 메서드 목록

#### 1. `check_port_availability(port: int) -> bool`
**목적**: 특정 포트의 사용 가능 여부 확인

**로직**:
```python
def check_port_availability(self, port):
    """Check if a port is available"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            return result != 0  # Port is available if connection fails
    except Exception:
        return True  # Assume available if check fails
```

**반환값**:
- `True`: 포트 사용 가능
- `False`: 포트 이미 사용 중

#### 2. `get_running_containers_info() -> List[Dict]`
**목적**: 실행 중인 트레이딩 시스템 컨테이너 정보 수집

**로직**:
```python
def get_running_containers_info(self):
    """Get information about running trading system containers"""
    result = subprocess.run([
        'docker', 'ps', '--format',
        '{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project.working_dir"}}|{{.Label "com.docker.compose.project"}}'
    ], capture_output=True, text=True, check=True)
    
    containers = []
    for line in result.stdout.strip().split('\n'):
        parts = line.split('|')
        if len(parts) >= 4:
            container_id, name, working_dir, project = parts
            if any(keyword in name.lower() for keyword in ['postgres', 'nginx', 'app', 'trading']):
                containers.append({
                    'id': container_id,
                    'name': name,
                    'working_dir': working_dir,
                    'project': project
                })
    return containers
```

**반환값**:
```python
[
    {
        'id': 'abc123',
        'name': 'webserver-postgres-1',
        'working_dir': '/Users/binee/Desktop/quant/webserver',
        'project': 'webserver'
    },
    ...
]
```

#### 3. `check_running_services() -> Dict`
**목적**: 현재 경로와 다른 경로의 서비스 분류

**반환값**:
```python
{
    'other_services': [...],      # 다른 경로의 컨테이너
    'current_services': [...]     # 현재 경로의 컨테이너
}
```

#### 4. `stop_other_services(other_services: List[Dict]) -> bool`
**목적**: 다른 경로의 서비스 안전하게 종료

**로직**:
1. 워킹 디렉토리별로 컨테이너 그룹화
2. 각 디렉토리에 대해:
   - `docker-compose.yml` 존재 시: `docker-compose down --remove-orphans`
   - 없으면: 각 컨테이너 개별 종료 (`docker stop {container_id}`)
3. 예외 발생 시 강제 종료 시도
4. 3초 대기 (포트 해제)

#### 5. `detect_and_stop_conflicts() -> bool`
**목적**: 충돌 감지 및 종료 로직을 통합한 고수준 메서드

**로직**:
```python
def detect_and_stop_conflicts(self):
    """Detect and stop services from other worktree directories"""
    # 1. 실행 중인 서비스 확인
    running_services = self.check_running_services()
    
    # 2. 다른 경로 서비스 종료
    if running_services and running_services['other_services']:
        if not self.stop_other_services(running_services['other_services']):
            return False
    
    return True
```

**사용 위치**:
- `start_system()`: 시작 전 충돌 감지
- `restart_system()`: 재시작 전 충돌 감지
- `clean_system()`: 정리 전 충돌 감지

### 명령어별 통합

#### start_system()
```python
def start_system(self):
    """시스템 시작"""
    self.print_banner()
    
    if not self.check_requirements():
        return False
    
    # 1. 다른 경로 서비스 확인 및 종료
    if not self.detect_and_stop_conflicts():
        return False
    
    # 2. 포트 가용성 확인
    unavailable_ports = [p for p in self.required_ports 
                        if not self.check_port_availability(p)]
    if unavailable_ports:
        return False
    
    # 3. 서비스 시작 (기존 로직)
    ...
```

#### restart_system()
```python
def restart_system(self):
    """시스템 재시작"""
    self.print_banner()
    
    # 1. 요구사항 확인
    if not self.check_requirements():
        return False
    
    # 2. 다른 경로 서비스 확인 및 종료
    if not self.detect_and_stop_conflicts():
        return False
    
    # 3. 현재 경로 서비스 종료
    self.stop_system()
    
    # 4. 대기 (포트 해제)
    time.sleep(5)
    
    # 5. 서비스 재시작
    # (start_system() 로직 인라인 - 중복 충돌 감지 방지)
    ...
```

#### clean_system()
```python
def clean_system(self):
    """시스템 완전 정리"""
    # 1. 경고 메시지 및 사용자 확인
    ...
    
    # 2. 요구사항 확인
    if not hasattr(self, 'compose_cmd'):
        self.check_requirements()
    
    # 3. 다른 경로 서비스 확인 및 종료
    if not self.detect_and_stop_conflicts():
        self.print_status("다른 경로 서비스 종료 실패", "warning")
        # 정리는 계속 진행
    
    # 4. 현재 경로 정리
    # - Docker 컨테이너, 볼륨, 이미지 삭제
    # - SSL 인증서 삭제
    # - 시스템 정리
    ...
```

## 장점

### 1. 사용자 편의성
- ✅ 수동으로 다른 worktree 찾아가서 종료할 필요 없음
- ✅ 자동으로 충돌 감지 및 해결
- ✅ 명확한 상태 메시지로 진행 상황 파악 가능

### 2. 안전성
- ✅ 포트 충돌 사전 확인
- ✅ 정상 종료 (docker-compose down) 시도
- ✅ 실패 시 강제 종료 백업 로직
- ✅ 포트 해제 대기 시간 확보

### 3. 개발 워크플로우 개선
- ✅ 여러 브랜치/기능을 빠르게 전환 가능
- ✅ worktree 경로 기억할 필요 없음
- ✅ 명령어 하나로 서비스 전환 완료

## 제한사항

### 1. Docker Labels 의존성
- Docker Compose V2+ 필요
- 수동으로 시작한 컨테이너는 감지 불가 (라벨 없음)

### 2. 동시 실행 불가
- 여러 worktree에서 동시에 서비스 실행 불가능
- 포트 충돌로 인한 기술적 제약

### 3. 타임아웃
- 서비스 종료 타임아웃: 30초
- 컨테이너 개별 종료 타임아웃: 10초
- 포트 확인 타임아웃: 5초

## 테스트 시나리오

### 테스트 1: start - 기본 충돌 해결
```bash
# Setup
cd /path/to/worktree1
python run.py start
# 확인: 서비스 정상 실행

# Test
cd /path/to/worktree2
python run.py start
# 기대 결과: worktree1 서비스 종료 → worktree2 서비스 시작
```

### 테스트 2: restart - 다른 경로에서 실행 중
```bash
# Setup
cd /path/to/worktree1
python run.py start
# 확인: 서비스 정상 실행

# Test
cd /path/to/worktree2
python run.py restart
# 기대 결과: 
# 1. worktree1 서비스 감지 및 종료
# 2. worktree2 현재 서비스 종료 (없음)
# 3. worktree2 서비스 시작
```

### 테스트 3: clean - 다른 경로 정리 후 현재 경로 정리
```bash
# Setup
cd /path/to/worktree1
python run.py start
# 확인: 서비스 정상 실행

# Test
cd /path/to/worktree2
python run.py clean
# 입력: yes
# 기대 결과:
# 1. worktree1 서비스 감지 및 종료
# 2. worktree2 모든 데이터/이미지/인증서 삭제
```

### 테스트 4: 존재하지 않는 경로
```bash
# Setup
cd /path/to/worktree1
python run.py start
rm -rf /path/to/worktree1  # 경로 삭제 (위험: 테스트 환경에서만)

# Test
cd /path/to/worktree2
python run.py start
# 기대 결과: 컨테이너 개별 종료 → worktree2 서비스 시작
```

### 테스트 5: 포트 충돌 (외부 프로세스)
```bash
# Setup
nginx  # 포트 443 점유

# Test
cd /path/to/worktree
python run.py start
# 기대 결과: 포트 충돌 오류 메시지, 종료
```

## 향후 개선 사항

### 1. 사용자 확인 옵션
```bash
python run.py start --no-auto-stop  # 자동 종료 비활성화
```

### 2. 병렬 실행 지원 (포트 분리)
각 worktree에 다른 포트 자동 할당:
```
worktree1: 443, 5001, 5432
worktree2: 444, 5002, 5433
```

### 3. 상태 저장
마지막 실행 경로 추적:
```bash
python run.py start --resume  # 마지막 실행 경로로 복귀
```

## 관련 파일

### 주요 파일
- `run.py`: TradingSystemManager 클래스
  - Lines 412-416: `__init__` (required_ports 추가, 절대 경로 사용)
  - Lines 468-476: `check_port_availability()` - 포트 가용성 확인
  - Lines 478-505: `get_running_containers_info()` - 컨테이너 정보 수집
  - Lines 507-528: `check_running_services()` - 실행 중인 서비스 분류
  - Lines 530-585: `stop_other_services()` - 다른 경로 서비스 종료
  - Lines 587-610: `detect_and_stop_conflicts()` - 충돌 감지 및 종료 통합
  - Lines 833-904: `start_system()` - 충돌 감지 로직 통합
  - Lines 987-1077: `restart_system()` - 충돌 감지 및 재시작
  - Lines 1164-1247: `clean_system()` - 충돌 감지 및 정리

### 문서
- `README.md`: Lines 70-91 (사용자 가이드)
- `docs/FEATURE_CATALOG.md`: 기능 카탈로그 엔트리

## 태그

```python
# @FEAT:worktree-conflict-resolution
# @COMP:util
# @TYPE:core
```

## 검색 명령어

```bash
# 관련 메서드 찾기
grep -n "check_running_services\|stop_other_services\|check_port_availability" run.py

# 기능 사용 위치 찾기
grep -n "worktree-conflict-resolution" docs/

# Docker 라벨 확인
docker ps --format '{{.Names}}|{{.Label "com.docker.compose.project.working_dir"}}'
```

