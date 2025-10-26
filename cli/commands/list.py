"""프로젝트 목록 조회 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
@FEAT:dynamic-port-allocation @COMP:route @TYPE:core
"""
import subprocess
from typing import List

from .base import BaseCommand
from cli.helpers.printer import Colors

# 테이블 너비 계산: 프로젝트명(40) + 포트(25) + 상태(24, ANSI 색상 코드 포함) + 컨테이너(10) + 여백(6) = 105
# ANSI 색상 코드(\033[32m, \033[0m 등)는 터미널 출력 시 보이지 않지만 문자열 길이에 포함되므로 추가 공간 필요
TABLE_WIDTH = 105


class ListCommand(BaseCommand):
    """프로젝트 목록 조회 명령어

    모든 webserver 관련 Docker Compose 프로젝트를 표 형식으로 출력
    """

    def __init__(self, printer, docker):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            docker: DockerHelper 인스턴스
        """
        super().__init__(printer)
        self.docker = docker

    def execute(self, args: list) -> int:
        """프로젝트 목록 조회 실행

        Args:
            args (list): 명령행 인자 (사용 안 함)

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        try:
            # 모든 webserver 프로젝트 조회 (BaseCommand 메서드 사용)
            projects = super()._get_all_webserver_projects()

            if not projects:
                self.printer.print_status("실행 중인 webserver 프로젝트가 없습니다.", "info")
                return 0

            # 표 헤더 출력
            self._print_header(len(projects))

            # 각 프로젝트 상세 정보 출력
            for project in projects:
                self._print_project_info(project)

            # 표 푸터 및 가이드 출력
            self._print_footer()

            return 0

        except Exception as e:
            self.printer.print_status(f"프로젝트 목록 조회 실패: {e}", "error")
            return 1

    def _print_header(self, project_count: int):
        """표 헤더 출력

        Args:
            project_count (int): 프로젝트 개수
        """
        colors = Colors

        print(f"\n{colors.CYAN}{'='*TABLE_WIDTH}{colors.RESET}")
        print(f"{colors.BOLD}Docker Compose 프로젝트 목록 ({project_count}개){colors.RESET}")
        print(f"{colors.CYAN}{'='*TABLE_WIDTH}{colors.RESET}\n")

        # 테이블 헤더
        print(f"{colors.BOLD}{'프로젝트명':<40} {'포트 (HTTPS, APP, DB)':<25} {'상태':<15} {'컨테이너 수':<10}{colors.RESET}")
        print("-" * TABLE_WIDTH)

    def _print_project_info(self, project: str):
        """프로젝트 상세 정보 출력

        Args:
            project (str): 프로젝트명
        """
        colors = Colors

        try:
            # 포트 정보 가져오기
            port_info = self._get_port_info(project)

            # 프로젝트의 컨테이너 정보 조회
            result = subprocess.run(
                ['docker', 'ps', '-a', '--filter', f'label=com.docker.compose.project={project}',
                 '--format', '{{.Status}}'],
                capture_output=True,
                text=True,
                check=True
            )

            statuses = result.stdout.strip().split('\n')
            container_count = len([s for s in statuses if s])

            # 실행 중인 컨테이너 확인
            running_count = len([s for s in statuses if s.startswith('Up')])

            # 상태 결정
            if running_count == container_count and container_count > 0:
                status = f"{colors.GREEN}실행 중{colors.RESET}"
            elif running_count > 0:
                status = f"{colors.YELLOW}부분 실행{colors.RESET}"
            else:
                status = f"{colors.RED}중지됨{colors.RESET}"

            print(f"{project:<40} {port_info:<25} {status:<24} {container_count}개")

        except subprocess.CalledProcessError:
            port_info = self._get_port_info(project)
            print(f"{project:<40} {port_info:<25} {colors.RED}오류{colors.RESET:<24} -")

    def _get_port_info(self, project: str) -> str:
        """프로젝트의 호스트 포트 정보 가져오기 (Docker API 전용)

        Docker API를 통해 실행 중인 컨테이너의 포트 매핑을 조회합니다.

        @FEAT:dynamic-port-allocation @COMP:util @TYPE:helper
        @CHANGE: Docker API 전용 (단일 소스 원칙), .env.local 의존성 제거

        Args:
            project (str): Docker Compose 프로젝트명

        Returns:
            str: 포트 정보
                - 성공: "(5087, 5059, 5490)"
                - 일부 실패: "(5087, 5059, N/A)"
                - 완전 실패: "N/A"
        """
        # Docker API로 포트 조회
        ports = self.docker.get_container_ports(project)

        if not ports:
            return "N/A"

        # 포트 정보 포맷팅 (Docker API 전용, nginx 컨테이너 포트 → https 키)
        https_port = ports.get("https") or "N/A"
        app_port = ports.get("app") or "N/A"
        postgres_port = ports.get("postgres") or "N/A"

        return f"({https_port}, {app_port}, {postgres_port})"

    def _print_footer(self):
        """표 푸터 및 사용 가이드 출력"""
        colors = Colors

        print(f"\n{colors.CYAN}{'='*TABLE_WIDTH}{colors.RESET}")
        print(f"\n{colors.BLUE}사용 가능한 명령어:{colors.RESET}")
        print(f"  python run.py stop [프로젝트명]   - 특정 프로젝트 중지")
        print(f"  python run.py clean [프로젝트명]  - 특정 프로젝트 완전 정리")
        print(f"  python run.py stop --all         - 모든 프로젝트 중지")
        print(f"  python run.py clean --all        - 모든 프로젝트 완전 정리\n")
