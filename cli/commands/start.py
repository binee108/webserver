"""시스템 시작 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
"""
import os
import sys
import time
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional, List

from .base import BaseCommand
from cli.helpers.printer import Colors


class StartCommand(BaseCommand):
    """시스템 시작 명령어

    TradingSystemManager.start_system() 로직을 Command 패턴으로 구현
    """

    def __init__(self, printer, docker, network, ssl, env, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            docker: DockerHelper 인스턴스
            network: NetworkHelper 인스턴스
            ssl: SSLHelper 인스턴스
            env: EnvHelper 인스턴스
            root_dir: 프로젝트 루트 디렉토리
        """
        super().__init__(printer)
        self.docker = docker
        self.network = network
        self.ssl = ssl
        self.env = env
        self.root_dir = root_dir
        self.project_name = "webserver"  # 기본 프로젝트명

        # 필수 포트 목록 (메인 프로젝트)
        self.required_ports = [443, 5001, 5432]

        # 워크트리 환경 변수
        self.worktree_env = self._detect_worktree_environment()
        if self.worktree_env:
            self._setup_worktree_ports()

    def _detect_worktree_environment(self) -> bool:
        """워크트리 환경 감지

        Returns:
            bool: 워크트리 환경이면 True
        """
        # .worktree/ 경로 내에서 실행 중인지 확인
        try:
            current_path = str(self.root_dir.resolve())
            return '.worktree' in current_path
        except Exception:
            return False

    def _setup_worktree_ports(self):
        """워크트리 환경용 포트 설정"""
        # 워크트리별 고유 포트 할당 (5002~5100, 5433~5531, 4431~4529)
        # 간단히 디렉토리 이름 기반 해시로 포트 계산
        try:
            worktree_name = self.root_dir.name
            base_offset = abs(hash(worktree_name)) % 98  # 0~97 범위

            self.flask_port = 5002 + base_offset
            self.postgres_port = 5433 + base_offset
            self.https_port = 4431 + base_offset
            self.project_name = f"webserver_{worktree_name.replace('.', '_')}"

            # 필수 포트 업데이트
            self.required_ports = [self.https_port, self.flask_port, self.postgres_port]
        except Exception:
            # 폴백: 기본값 사용
            self.flask_port = 5001
            self.postgres_port = 5432
            self.https_port = 443

    def execute(self, args: list) -> int:
        """시스템 시작 실행

        Args:
            args (list): 명령행 인자 (예: ['project_name'])

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        # 프로젝트명 파싱 (인자가 있으면 사용)
        if args:
            self.project_name = args[0]

        try:
            # 배너 출력
            self.printer.print_banner()

            # 시스템 요구사항 확인
            if not self.docker.check_requirements():
                return 1

            # 충돌 감지 및 중지 (다른 경로에서 실행 중인 서비스)
            if not self._detect_and_stop_conflicts():
                return 1

            # 필수 포트 확인
            if not self._check_required_ports():
                return 1

            # 현재 경로 출력
            print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
            self.printer.print_status(f"현재 경로에서 서비스 시작: {self.root_dir}", "info")
            print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")

            # 워크트리 환경 변수 설정
            if self.worktree_env:
                self._setup_worktree_environment()

            # 기존 컨테이너 정리
            self.printer.print_status("기존 컨테이너 정리 중...", "info")
            self.docker.run_command(
                self.docker.compose_cmd + ['-p', self.project_name, 'down', '--remove-orphans'],
                cwd=self.root_dir
            )

            # 워크트리 환경에서 메인 DB 복사
            if self.worktree_env:
                if not self.docker.copy_main_db_to_worktree(self.project_name):
                    self.printer.print_status("DB 복사에 실패했지만 계속 진행합니다.", "warning")

            # 시작할 서비스 목록 결정
            services_to_start = self.docker.get_services_to_start()

            # SSL 인증서 생성/확인 (nginx 사용 시)
            if 'nginx' in services_to_start:
                if not self.ssl.generate_ssl_certificates():
                    return 1

            # PostgreSQL 시작
            if not self.docker.start_postgres(self.project_name):
                return 1

            # Flask 앱 시작
            if not self.docker.start_flask(self.project_name):
                return 1

            # Nginx 시작 (필요 시)
            self.docker.start_nginx_if_needed(self.project_name, services_to_start)

            # 시작 완료 메시지 및 접속 정보 출력
            self._print_success_message(services_to_start)

            # 브라우저 자동 열기
            self._open_browser(services_to_start)

            return 0

        except subprocess.CalledProcessError as e:
            self.printer.print_status(f"시스템 시작 실패: {e}", "error")
            return 1
        except Exception as e:
            self.printer.print_status(f"예기치 않은 오류 발생: {e}", "error")
            return 1

    def _detect_and_stop_conflicts(self) -> bool:
        """다른 경로에서 실행 중인 서비스 감지 및 중지

        Returns:
            bool: 성공 시 True
        """
        # 다른 경로의 webserver 프로젝트 감지
        try:
            result = subprocess.run(
                ['docker', 'ps', '--filter', 'name=webserver', '--format', '{{.Names}}'],
                capture_output=True,
                text=True
            )

            if result.returncode == 0 and result.stdout.strip():
                running_containers = result.stdout.strip().split('\n')
                other_projects = set()

                for container in running_containers:
                    # 현재 프로젝트가 아닌 다른 webserver 프로젝트 찾기
                    if 'webserver' in container and self.project_name not in container:
                        project = container.split('-')[0] if '-' in container else 'webserver'
                        other_projects.add(project)

                if other_projects:
                    self.printer.print_status(
                        f"다른 경로에서 실행 중인 프로젝트 발견: {', '.join(other_projects)}",
                        "warning"
                    )

                    # 자동으로 중지
                    for project in other_projects:
                        self.printer.print_status(f"{project} 프로젝트 중지 중...", "info")
                        try:
                            subprocess.run(
                                self.docker.compose_cmd + ['-p', project, 'down'],
                                capture_output=True,
                                timeout=30
                            )
                        except Exception:
                            pass

                    time.sleep(3)  # 컨테이너 정리 대기

            return True
        except Exception:
            # 충돌 감지 실패는 무시하고 계속 진행
            return True

    def _check_required_ports(self) -> bool:
        """필수 포트 사용 가능 여부 확인

        Returns:
            bool: 모든 포트 사용 가능하면 True
        """
        self.printer.print_status("필수 포트 확인 중...", "info")
        unavailable_ports = []

        for port in self.required_ports:
            if not self.network.check_port_availability(port):
                unavailable_ports.append(port)

        if unavailable_ports:
            self.printer.print_status(
                f"다음 포트가 이미 사용 중입니다: {', '.join(map(str, unavailable_ports))}",
                "warning"
            )
            self.printer.print_status("충돌하는 프로세스를 종료하거나 포트를 변경해주세요", "error")

            # 포트 사용 정보 출력 시도
            self._print_port_usage(unavailable_ports)
            return False

        self.printer.print_status("모든 필수 포트 사용 가능", "success")
        return True

    def _print_port_usage(self, ports: List[int]):
        """포트 사용 정보 출력

        Args:
            ports (list): 확인할 포트 목록
        """
        import platform

        for port in ports:
            try:
                if platform.system() == 'Darwin':  # macOS
                    result = subprocess.run(
                        ['lsof', '-i', f':{port}'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.stdout:
                        print(f"\n포트 {port} 사용 정보:")
                        print(result.stdout[:500])
                elif platform.system() == 'Linux':
                    result = subprocess.run(
                        ['ss', '-tulpn'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.stdout:
                        print(f"\n포트 {port} 사용 정보:")
                        print(result.stdout[:500])
            except Exception:
                pass

    def _setup_worktree_environment(self):
        """워크트리 환경 변수 설정"""
        self.printer.print_status("워크트리 환경 변수 설정 중...", "info")

        os.environ['APP_PORT'] = str(self.flask_port)
        os.environ['POSTGRES_PORT'] = str(self.postgres_port)
        os.environ['COMPOSE_PROJECT_NAME'] = self.project_name

        if hasattr(self, 'https_port'):
            os.environ['HTTPS_PORT'] = str(self.https_port)

        self.printer.print_status(
            f"포트 설정: Flask={self.flask_port}, PostgreSQL={self.postgres_port}",
            "success"
        )

    def _print_success_message(self, services_to_start: List[str]):
        """시작 완료 메시지 및 접속 정보 출력

        Args:
            services_to_start (list): 시작된 서비스 목록
        """
        # 네트워크 정보 수집
        local_ip = self.network.get_local_ip()
        external_ip = self.network.get_external_ip()

        # 포트 정보
        flask_port = getattr(self, 'flask_port', 5001)
        https_port = getattr(self, 'https_port', 443)
        postgres_port = getattr(self, 'postgres_port', 5432)

        # 시작 완료 메시지
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ 트레이딩 시스템이 성공적으로 시작되었습니다!{Colors.RESET}\n")

        # HTTPS 접근 정보 (nginx 사용 시)
        if 'nginx' in services_to_start:
            print(f"{Colors.CYAN}🌐 웹 인터페이스 접근 주소 (HTTPS):{Colors.RESET}")
            https_port_display = f":{https_port}" if https_port != 443 else ""
            print(f"   로컬: https://localhost{https_port_display}")
            if local_ip and local_ip != "127.0.0.1":
                print(f"   네트워크: https://{local_ip}{https_port_display}")
            if external_ip:
                print(f"   외부: https://{external_ip}{https_port_display}")
            print()

        # HTTP 접근 정보
        print(f"{Colors.BLUE}🔧 HTTP 접근:{Colors.RESET}")
        flask_port_display = f":{flask_port}" if flask_port != 5001 else ":5001"
        print(f"   로컬: http://localhost{flask_port_display} (직접 Flask 접근)")
        if local_ip and local_ip != "127.0.0.1":
            print(f"   네트워크: http://{local_ip}{flask_port_display}")
        print()

        # PostgreSQL 접근 정보
        postgres_port_display = f":{postgres_port}" if postgres_port != 5432 else ":5432"
        print(f"{Colors.MAGENTA}🐘 PostgreSQL: localhost{postgres_port_display}{Colors.RESET}\n")

        # 보안 경고
        print(f"{Colors.YELLOW}⚠️  브라우저에서 보안 경고가 나타나면:{Colors.RESET}")
        print("   Chrome: '고급' → '안전하지 않음(권장하지 않음)' → '계속 진행'")
        print("   Safari: '고급' → '계속 진행'\n")

        # 기본 로그인 정보
        print(f"{Colors.WHITE}👤 기본 로그인 정보:{Colors.RESET}")
        print("   사용자명: admin")
        print("   비밀번호: admin_test_0623\n")

        # 웹훅 접근
        print(f"{Colors.GREEN}🔗 웹훅 접근:{Colors.RESET}")
        if 'nginx' in services_to_start:
            https_port_display = f":{https_port}" if https_port != 443 else ""
            print(f"   HTTPS (로컬): https://localhost{https_port_display}/api/webhook")
            if external_ip:
                print(f"   HTTPS (외부): https://{external_ip}{https_port_display}/api/webhook")
        print(f"   HTTP (내부): http://localhost:{flask_port}/api/webhook")
        print()

        # 유용한 명령어
        print(f"{Colors.CYAN}📋 유용한 명령어:{Colors.RESET}")
        print("   python run.py stop     - 시스템 중지")
        print("   python run.py logs     - 로그 확인")
        print("   python run.py status   - 상태 확인")
        print("   python run.py restart  - 재시작")

    def _open_browser(self, services_to_start: List[str]):
        """브라우저 자동 열기

        Args:
            services_to_start (list): 시작된 서비스 목록
        """
        try:
            time.sleep(5)  # 서비스 완전 시작 대기

            flask_port = getattr(self, 'flask_port', 5001)
            https_port = getattr(self, 'https_port', 443)

            if 'nginx' in services_to_start:
                # 프로덕션 모드: HTTPS
                https_port_display = f":{https_port}" if https_port != 443 else ""
                webbrowser.open(f'https://localhost{https_port_display}')
            else:
                # 개발 모드: HTTP
                webbrowser.open(f'http://localhost:{flask_port}')
        except Exception:
            pass  # 브라우저 열기 실패는 무시
