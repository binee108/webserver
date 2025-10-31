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


class PortAllocationError(Exception):
    """포트 할당 실패 예외

    @FEAT:dynamic-port-allocation @COMP:service @TYPE:core

    포트 범위 내 사용 가능 포트가 없을 때 발생합니다.
    워크트리 환경에서 다중 서비스 실행 시 포트 충돌을 명확히 보고합니다.
    """
    pass


class StartCommand(BaseCommand):
    """시스템 시작 명령어

    TradingSystemManager.start_system() 로직을 Command 패턴으로 구현
    """

    def __init__(self, printer, docker, network, ssl, env, migration, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            docker: DockerHelper 인스턴스
            network: NetworkHelper 인스턴스
            ssl: SSLHelper 인스턴스
            env: EnvHelper 인스턴스
            migration: MigrationHelper 인스턴스
            root_dir: 프로젝트 루트 디렉토리
        """
        super().__init__(printer)
        self.docker = docker
        self.network = network
        self.ssl = ssl
        self.env = env
        self.migration = migration
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

            # 필수 포트 확인 (args 전달)
            if not self._check_required_ports(args):
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

            # 마이그레이션 실행 (PostgreSQL 시작 후, Flask 시작 전)
            self.printer.print_status("데이터베이스 마이그레이션 확인 중...", "info")
            if not self.migration.run_pending_migrations(self.root_dir):
                self.printer.print_status("⚠️  마이그레이션 실패, 계속 진행합니다.", "warning")

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
        """DEPRECATED: 하위 호환성을 위해 유지, 실제로는 종료하지 않음

        다른 워크트리/메인 프로젝트의 서비스 정보만 확인합니다.
        더 이상 서비스를 종료하지 않습니다.

        Returns:
            bool: 항상 True 반환 (하위 호환성 보장)
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
                        f"다른 경로에서 실행 중인 서비스 발견: {', '.join(other_projects)}",
                        "info"
                    )

                    # 정보만 출력 (종료하지 않음)
                    self.printer.print_status(
                        "다른 서비스는 유지되며, 포트 충돌 시 자동 재할당됩니다",
                        "info"
                    )
                    self.printer.print_status(
                        "각 워크트리는 독립적으로 실행되어 서로 영향을 주지 않습니다",
                        "info"
                    )

            return True
        except Exception:
            # 충돌 감지 실패는 무시하고 계속 진행
            return True

    def _calculate_hash_port(self, project_name: str, start_port: int, end_port: int) -> int:
        """프로젝트명 기반 해시 포트 계산

        @FEAT:dynamic-port-allocation @COMP:service @TYPE:helper

        워크트리별 일관된 포트 할당을 위해 프로젝트명의 해시값을 기반으로
        포트 범위 내의 오프셋을 계산합니다. 같은 워크트리는 항상 동일 포트를 할당받습니다.

        Args:
            project_name: 프로젝트명 (예: "webserver_feature-branch")
            start_port: 포트 범위 시작 (예: 5002)
            end_port: 포트 범위 끝 (예: 5100)

        Returns:
            int: 계산된 포트 번호 (start_port <= port <= end_port)

        Examples:
            >>> self._calculate_hash_port("webserver_test", 5002, 5100)
            5042  # 항상 동일 값 반환
        """
        port_range = end_port - start_port
        hash_offset = abs(hash(project_name)) % port_range
        return start_port + hash_offset

    def _allocate_ports_dynamically(self, project_name: str) -> dict:
        """포트 충돌 시 동적으로 빈 포트 할당

        @FEAT:dynamic-port-allocation @COMP:service @TYPE:core

        워크트리 환경에서 포트 충돌 발생 시 자동으로 빈 포트를 탐색하여 할당하고,
        할당된 포트를 .env.local에 영구 저장하여 재시작 시에도 동일 포트를 사용합니다.

        포트 할당 우선순위:
        1. .env.local에 저장된 이전 할당 포트 (존재하고 사용 가능하면 재사용)
        2. 프로젝트명 해시 기반 포트 (일관성 보장)
        3. 포트 범위 내 순차 검색 (충돌 시 다음 가용 포트)
        4. 범위 소진 → PortAllocationError 발생

        Args:
            project_name: 프로젝트명 (예: "webserver_feature-branch")

        Returns:
            dict: 할당된 포트 딕셔너리
                {"HTTPS_PORT": 4431, "APP_PORT": 5002, "POSTGRES_PORT": 5433}

        Raises:
            PortAllocationError: 포트 범위 내 사용 가능 포트 없음
                (범위: HTTPS 4431-4529, APP 5002-5100, POSTGRES 5433-5531)

        Examples:
            >>> ports = self._allocate_ports_dynamically("webserver_feature")
            >>> ports["APP_PORT"]  # "5042"
        """
        MAX_PORT_RETRIES = 10
        PORT_RANGES = {
            "HTTPS_PORT": (4431, 4529),      # 100개 범위
            "APP_PORT": (5002, 5100),        # 100개 범위
            "POSTGRES_PORT": (5433, 5531)    # 100개 범위
        }

        allocated_ports = {}

        # Step 1: .env.local에서 이전 할당 포트 로드 (Graceful Degradation)
        env_dict = self.env.load_local_env(self.root_dir)

        for port_name, (start_port, end_port) in PORT_RANGES.items():
            # Step 2: 저장된 포트 우선 사용 (일관성 보장)
            if port_name in env_dict:
                try:
                    saved_port = int(env_dict[port_name])
                    if self.network.check_port_availability(saved_port):
                        allocated_ports[port_name] = saved_port
                        self.printer.print_status(f"✅ {port_name} 재사용: {saved_port}", "success")
                        continue
                except ValueError:
                    # 파싱 실패: .env.local 파일이 손상되었으나 계속 진행
                    pass

            # Step 3: 해시 기반 포트 시도 (워크트리별 일관된 할당)
            hash_port = self._calculate_hash_port(project_name, start_port, end_port)
            if self.network.check_port_availability(hash_port):
                allocated_ports[port_name] = hash_port
                self.printer.print_status(f"✅ {port_name} 할당: {hash_port} (hash)", "success")
                continue

            # Step 4: 범위 내 순차 검색 (충돌 시 다음 가용 포트 찾기)
            # 이미 할당된 포트는 제외하여 중복 할당 방지
            candidate_port = self.network.find_available_port((start_port, end_port))
            if candidate_port and candidate_port not in allocated_ports.values():
                allocated_ports[port_name] = candidate_port
                self.printer.print_status(
                    f"{port_name} 충돌 감지 → {candidate_port} 할당", "warning"
                )
                found = True
            else:
                found = False

            # Step 5: 범위 소진 처리 (명확한 에러 메시지 제공)
            if not found:
                raise PortAllocationError(
                    f"❌ {port_name} 할당 실패: 포트 범위 {start_port}-{end_port} 내 사용 가능 포트 없음.\n"
                    f"   해결 방법:\n"
                    f"   1. 다른 워크트리를 중지: python run.py stop --all\n"
                    f"   2. 수동 포트 지정: python run.py start --{port_name.lower()} 4550"
                )

        # Step 6: 할당 포트 .env.local에 영구 저장 (재시작 시 재사용)
        if self.env.save_local_env(self.root_dir, allocated_ports):
            self.printer.print_status("💾 포트 설정이 .env.local에 저장되었습니다.", "success")
        else:
            # 파일 저장 실패해도 이미 할당된 포트는 사용 가능
            self.printer.print_status("⚠️  포트 설정 저장 실패 (계속 진행)", "warning")

        return allocated_ports

    def _check_required_ports(self, args: list) -> bool:
        """필수 포트 사용 가능 여부 확인 (충돌 시 동적 할당)

        @FEAT:dynamic-port-allocation @COMP:service @TYPE:core

        워크트리 환경에서 필수 포트(HTTPS, Flask, PostgreSQL)의 사용 가능 여부를 확인합니다.
        포트 충돌 발생 시 자동으로 동적 포트 할당을 시작합니다.

        Args:
            args: 명령행 인자 (프로젝트명 추출용, 예: ["custom_project_name"])

        Returns:
            bool: 모든 포트 사용 가능하거나 동적 할당 성공 시 True, 실패 시 False

        Note:
            - 메인 프로젝트: 고정 포트 (443, 5001, 5432)
            - 워크트리 프로젝트: 동적 할당 (4431-4529, 5002-5100, 5433-5531 범위)
            - 할당된 포트는 os.environ과 self.required_ports로 즉시 반영

        Examples:
            >>> result = self._check_required_ports([])
            >>> result  # True if all ports available or dynamic allocation succeeded
        """
        self.printer.print_status("필수 포트 확인 중...", "info")
        conflicting_ports = []

        for port in self.required_ports:
            if not self.network.check_port_availability(port):
                conflicting_ports.append(port)

        if conflicting_ports:
            self.printer.print_status(
                f"다음 포트가 이미 사용 중입니다: {', '.join(map(str, conflicting_ports))}",
                "warning"
            )

            # 포트 충돌 시 동적 할당 시도
            self.printer.print_status("🔄 포트 충돌 감지, 동적 할당 시작...", "info")

            try:
                # 프로젝트명 추출
                project_name = self.project_name
                if args:
                    project_name = args[0]

                # 동적 포트 할당
                allocated_ports = self._allocate_ports_dynamically(project_name)

                # 할당된 포트로 환경 변수 오버라이드
                for port_name, port_value in allocated_ports.items():
                    os.environ[port_name] = str(port_value)

                # 인스턴스 변수 업데이트
                if "HTTPS_PORT" in allocated_ports:
                    self.https_port = allocated_ports["HTTPS_PORT"]
                if "APP_PORT" in allocated_ports:
                    self.flask_port = allocated_ports["APP_PORT"]
                if "POSTGRES_PORT" in allocated_ports:
                    self.postgres_port = allocated_ports["POSTGRES_PORT"]

                # 필수 포트 목록 업데이트
                self.required_ports = [
                    allocated_ports.get("HTTPS_PORT", self.https_port),
                    allocated_ports.get("APP_PORT", self.flask_port),
                    allocated_ports.get("POSTGRES_PORT", self.postgres_port)
                ]

                self.printer.print_status("✅ 동적 포트 할당 성공", "success")
                return True

            except PortAllocationError as e:
                self.printer.print_status(str(e), "error")
                self._print_port_usage(conflicting_ports)
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
