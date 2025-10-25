"""Docker 관리 헬퍼 모듈

@FEAT:cli-migration @COMP:util @TYPE:helper
"""
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, List


class DockerHelper:
    """Docker 컨테이너 관리 헬퍼

    TradingSystemManager의 Docker 관련 메서드들을 독립 모듈로 분리:
    - detect_compose_command()
    - run_command()
    - start_postgres()
    - wait_for_postgres()
    - start_flask()
    - start_nginx_if_needed()
    - stop_containers()
    - cleanup_containers()
    - check_requirements()
    """

    def __init__(self, printer, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            root_dir: 프로젝트 루트 디렉토리
        """
        self.printer = printer
        self.root_dir = root_dir
        self.compose_cmd = self._detect_compose_command()

    def _detect_compose_command(self) -> List[str]:
        """Docker Compose 명령어 감지

        Returns:
            List[str]: ['docker', 'compose'] 또는 ['docker-compose']
        """
        # 먼저 'docker compose' (V2) 시도
        try:
            result = subprocess.run(
                ['docker', 'compose', 'version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return ['docker', 'compose']
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # 'docker compose'가 없으면 'docker-compose' (V1) 시도
        try:
            result = subprocess.run(
                ['docker-compose', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return ['docker-compose']
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # 둘 다 없으면 기본값 반환
        return ['docker', 'compose']

    def run_command(self, cmd: List[str], cwd: Optional[Path] = None,
                   check: bool = True, capture_output: bool = False, show_output: bool = False):
        """명령어 실행 헬퍼

        Args:
            cmd: 실행할 명령어 리스트
            cwd: 작업 디렉토리
            check: 오류 시 예외 발생 여부
            capture_output: 출력 캡처 여부
            show_output: 출력 직접 표시 여부

        Returns:
            subprocess.CompletedProcess

        Raises:
            subprocess.CalledProcessError: check=True이고 명령어 실패 시
        """
        try:
            if show_output:
                result = subprocess.run(cmd, cwd=cwd, check=check)
            else:
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=check
                )
            return result
        except subprocess.CalledProcessError as e:
            if not show_output and hasattr(e, 'stderr') and e.stderr:
                cmd_str = ' '.join(cmd)
                self.printer.print_status(f"명령어 실행 오류: {cmd_str}", "error")
                self.printer.print_status(f"오류 메시지: {e.stderr.strip()}", "error")
            raise e

    def check_requirements(self) -> bool:
        """시스템 요구사항 확인

        Returns:
            bool: 모든 요구사항 충족 시 True
        """
        self.printer.print_status("시스템 요구사항 확인 중...", "info")

        # Docker 설치 확인
        try:
            result = subprocess.run(
                ['docker', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, 'docker')
            self.printer.print_status(f"Docker 확인: {result.stdout.strip()}", "success")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.printer.print_status("Docker가 설치되지 않았습니다.", "error")
            self.printer.print_status("Docker Desktop을 설치해주세요: https://www.docker.com/get-started", "info")
            return False

        # Docker Compose 설치 확인
        compose_version = None

        # 먼저 'docker compose' (V2) 시도
        try:
            result = subprocess.run(
                ['docker', 'compose', 'version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                compose_version = result.stdout.strip()
                self.compose_cmd = ['docker', 'compose']
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # 'docker compose'가 없으면 'docker-compose' (V1) 시도
        if not compose_version:
            try:
                result = subprocess.run(
                    ['docker-compose', '--version'],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    compose_version = result.stdout.strip()
                    self.compose_cmd = ['docker-compose']
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

        if compose_version:
            self.printer.print_status(f"Docker Compose 확인: {compose_version}", "success")
        else:
            self.printer.print_status("Docker Compose가 설치되지 않았습니다.", "error")
            self.printer.print_status("Docker Desktop 최신 버전을 설치하거나 docker-compose-plugin을 설치해주세요.", "info")
            return False

        # Docker 실행 상태 확인
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, 'docker info')
            self.printer.print_status("Docker 서비스 실행 중", "success")
        except subprocess.CalledProcessError:
            self.printer.print_status("Docker 서비스가 실행되고 있지 않습니다.", "error")
            self.printer.print_status("Docker Desktop을 시작해주세요.", "info")
            return False

        return True

    def start_postgres(self, project_name: str) -> bool:
        """PostgreSQL 컨테이너 시작

        Args:
            project_name (str): Docker Compose 프로젝트 이름

        Returns:
            bool: 성공 시 True
        """
        self.printer.print_status("PostgreSQL 데이터베이스 시작 중...", "info")
        self.run_command(
            self.compose_cmd + ['-p', project_name, 'up', '-d', 'postgres'],
            cwd=self.root_dir
        )
        return self.wait_for_postgres(project_name)

    def wait_for_postgres(self, project_name: str, max_attempts: int = 30) -> bool:
        """PostgreSQL 준비 대기

        Args:
            project_name (str): Docker Compose 프로젝트 이름
            max_attempts (int, optional): 최대 재시도 횟수

        Returns:
            bool: 성공 시 True
        """
        self.printer.print_status("PostgreSQL 데이터베이스 준비 대기 중...", "info")

        for attempt in range(max_attempts):
            try:
                cmd = self.compose_cmd + [
                    '-p', project_name,
                    'exec', '-T', 'postgres',
                    'pg_isready', '-U', 'trader', '-d', 'trading_system'
                ]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=self.root_dir
                )

                if result.returncode == 0:
                    self.printer.print_status("PostgreSQL 준비 완료!", "success")
                    return True

            except subprocess.CalledProcessError:
                pass

            if attempt < max_attempts - 1:
                from cli.helpers.printer import Colors
                print(f"{Colors.YELLOW}  대기 중... ({attempt + 1}/{max_attempts}){Colors.RESET}")
                time.sleep(2)

        self.printer.print_status("PostgreSQL 시작 시간 초과", "error")
        return False

    def start_flask(self, project_name: str, wait_time: int = 5) -> bool:
        """Flask 앱 컨테이너 시작

        Args:
            project_name (str): Docker Compose 프로젝트 이름
            wait_time (int): Flask 앱 준비 대기 시간 (초)

        Returns:
            bool: 성공 시 True
        """
        self.printer.print_status("Flask 애플리케이션 시작 중...", "info")
        self.run_command(
            self.compose_cmd + ['-p', project_name, 'up', '-d', 'app'],
            cwd=self.root_dir
        )

        # 앱 준비 대기
        self.printer.print_status("Flask 애플리케이션 준비 대기 중...", "info")
        time.sleep(wait_time)

        self.printer.print_status("데이터베이스 테이블 자동 생성 준비 완료", "success")
        return True

    def start_nginx_if_needed(self, project_name: str, services_to_start: List[str]) -> bool:
        """Nginx 시작 (필요 시)

        Args:
            project_name (str): Docker Compose 프로젝트 이름
            services_to_start (list): 시작할 서비스 목록

        Returns:
            bool: 성공 시 True
        """
        if 'nginx' in services_to_start:
            self.printer.print_status("Nginx 리버스 프록시 시작 중...", "info")
            self.run_command(
                self.compose_cmd + ['-p', project_name, 'up', '-d', 'nginx'],
                cwd=self.root_dir
            )
        else:
            self.printer.print_status("개발 모드: Nginx 제외, HTTP만 사용", "info")

        return True

    def stop_containers(self, project_name: str):
        """컨테이너 중지

        Args:
            project_name (str): Docker Compose 프로젝트 이름
        """
        self.printer.print_status(f"프로젝트 중지 중: {project_name}", "info")

        try:
            self.run_command(
                self.compose_cmd + ['-p', project_name, 'down'],
                cwd=self.root_dir
            )
            self.printer.print_status(f"{project_name} 프로젝트가 중지되었습니다.", "success")
        except subprocess.CalledProcessError as e:
            self.printer.print_status(f"시스템 중지 실패: {e}", "error")
            raise

    def cleanup_containers(self, project_name: str, remove_volumes: bool = True):
        """컨테이너 정리 (볼륨 포함)

        Args:
            project_name (str): Docker Compose 프로젝트 이름
            remove_volumes (bool): 볼륨 삭제 여부
        """
        self.printer.print_status("컨테이너 및 데이터 정리 중...", "info")

        try:
            cmd = self.compose_cmd + ['-p', project_name, 'down']
            if remove_volumes:
                cmd.extend(['-v', '--remove-orphans'])

            self.run_command(cmd, cwd=self.root_dir)
            self.printer.print_status("정리가 완료되었습니다.", "success")
        except subprocess.CalledProcessError as e:
            self.printer.print_status(f"정리 중 오류 발생: {e}", "error")
            raise

    def copy_main_db_to_worktree(self, worktree_project_name: str) -> bool:
        """메인 프로젝트 DB 볼륨을 워크트리 볼륨으로 복사

        Args:
            worktree_project_name (str): 워크트리 프로젝트 이름

        Returns:
            bool: 복사 성공 여부
        """
        main_volume = 'webserver_postgres_data'
        worktree_volume = f"{worktree_project_name}_postgres_data"

        self.printer.print_status(
            f"메인 DB 볼륨 복사 중... ({main_volume} → {worktree_volume})",
            "info"
        )

        # 1. 메인 DB 볼륨 존재 확인
        try:
            result = subprocess.run(
                ['docker', 'volume', 'inspect', main_volume],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                self.printer.print_status("메인 프로젝트 DB 볼륨이 존재하지 않습니다.", "warning")
                self.printer.print_status("초기화된 DB로 시작합니다.", "info")
                return True
        except Exception:
            return True

        try:
            # 2. 임시 백업 파일 생성
            timestamp = int(time.time())
            backup_file = f"/tmp/db_backup_{timestamp}.tar.gz"

            # 3. 메인 볼륨에서 백업
            self.printer.print_status("메인 DB 백업 생성 중...", "info")
            subprocess.run(
                ['docker', 'run', '--rm',
                 '-v', f'{main_volume}:/source',
                 '-v', '/tmp:/backup',
                 'alpine',
                 'tar', 'czf', f'/backup/db_backup_{timestamp}.tar.gz', '-C', '/source', '.'],
                check=True,
                capture_output=True
            )

            # 4. 워크트리 볼륨 생성 (이미 존재하면 무시)
            subprocess.run(
                ['docker', 'volume', 'create', worktree_volume],
                capture_output=True  # 에러 무시 (이미 존재할 수 있음)
            )

            # 5. 워크트리 볼륨으로 복원
            self.printer.print_status("워크트리 DB 볼륨으로 복원 중...", "info")
            subprocess.run(
                ['docker', 'run', '--rm',
                 '-v', f'{worktree_volume}:/target',
                 '-v', '/tmp:/backup',
                 'alpine',
                 'tar', 'xzf', f'/backup/db_backup_{timestamp}.tar.gz', '-C', '/target'],
                check=True,
                capture_output=True
            )

            # 6. 백업 파일 정리
            try:
                os.remove(backup_file)
            except Exception:
                pass

            self.printer.print_status(f"DB 볼륨 복사 완료! ({worktree_volume})", "success")
            return True

        except subprocess.CalledProcessError as e:
            self.printer.print_status(f"DB 볼륨 복사 실패: {e}", "error")
            return False
        except Exception as e:
            self.printer.print_status(f"DB 볼륨 복사 중 오류: {e}", "error")
            return False

    def get_services_to_start(self) -> List[str]:
        """환경 모드에 따라 시작할 서비스 목록 반환

        Returns:
            list: 시작할 서비스 이름 리스트
        """
        # .env 파일에서 FLASK_ENV 읽기
        env_file = self.root_dir / '.env'
        flask_env = 'development'  # 기본값

        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        if line.startswith('FLASK_ENV='):
                            flask_env = line.split('=')[1].strip()
                            break
            except Exception:
                pass

        # 환경 모드에 따라 서비스 선택
        if flask_env == 'production':
            # 프로덕션 모드: postgres + app + nginx (HTTPS)
            return ['postgres', 'app', 'nginx']
        else:
            # 개발 모드: postgres + app만 (HTTP)
            return ['postgres', 'app']
