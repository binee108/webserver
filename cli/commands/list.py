"""프로젝트 목록 조회 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
@FEAT:dynamic-port-allocation @COMP:route @TYPE:core
"""
import subprocess
from pathlib import Path
from typing import List

from .base import BaseCommand
from cli.helpers.printer import Colors
from cli.helpers.env import EnvHelper

# 테이블 너비 계산: 프로젝트명(40) + 포트(25) + 상태(24, ANSI 색상 코드 포함) + 컨테이너(10) + 여백(6) = 105
# ANSI 색상 코드(\033[32m, \033[0m 등)는 터미널 출력 시 보이지 않지만 문자열 길이에 포함되므로 추가 공간 필요
TABLE_WIDTH = 105


class ListCommand(BaseCommand):
    """프로젝트 목록 조회 명령어

    모든 webserver 관련 Docker Compose 프로젝트를 표 형식으로 출력
    """

    def __init__(self, printer, docker, env_helper):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            docker: DockerHelper 인스턴스
            env_helper: EnvHelper 인스턴스 (.env.local 파일에서 포트 정보 로드)
        """
        super().__init__(printer)
        self.docker = docker
        self.env_helper = env_helper

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
        """프로젝트의 포트 정보 가져오기

        @FEAT:dynamic-port-allocation @COMP:util @TYPE:helper

        Args:
            project (str): 프로젝트명 (예: "webserver", "webserver_test-feature")

        Returns:
            str: 포맷팅된 포트 정보 (예: "(443, 5001, 5432)")

        Side Effects:
            - .env.local 파일 읽기 (Phase 1 EnvHelper 통합)
            - 파일 없을 경우 기본값(443, 5001, 5432) 사용 (graceful degradation)
        """
        # 프로젝트명에서 워크트리 경로 추론
        root_dir = self._get_project_root_dir(project)

        # .env.local 파일에서 포트 정보 로드 (Phase 1에서 구현된 메서드)
        # 파일 부재 시 빈 딕셔너리 반환 → 기본값 사용 (graceful degradation)
        env_dict = self.env_helper.load_local_env(root_dir)

        # 포트 추출 (없으면 기본값)
        https_port = env_dict.get("HTTPS_PORT", "443")
        app_port = env_dict.get("APP_PORT", "5001")
        postgres_port = env_dict.get("POSTGRES_PORT", "5432")

        return f"({https_port}, {app_port}, {postgres_port})"

    def _get_project_root_dir(self, project: str) -> Path:
        """프로젝트명에서 루트 디렉토리 경로 추론 (워크트리 인식)

        현재 경로가 워크트리 내부인지 자동 감지하여 메인 루트를 정확히 파악합니다.

        @FEAT:dynamic-port-allocation @COMP:util @TYPE:helper

        Args:
            project (str): Docker Compose 프로젝트명 (예: "webserver", "webserver_dynamic-port-allocation")

        Returns:
            Path: 프로젝트 루트 디렉토리 절대 경로

        Examples:
            >>> # 메인 프로젝트에서 실행
            >>> _get_project_root_dir("webserver")
            PosixPath('/Users/binee/Desktop/quant/webserver')

            >>> # 워크트리 내부에서 실행
            >>> _get_project_root_dir("webserver_dynamic-port-allocation")
            PosixPath('/Users/binee/Desktop/quant/webserver/.worktree/dynamic-port-allocation')
        """
        cwd = Path.cwd()

        # 현재 경로가 워크트리 내부인지 확인
        if ".worktree" in cwd.parts:
            # 메인 프로젝트 루트: .worktree 이전까지의 경로
            try:
                parts = cwd.parts
                worktree_idx = parts.index(".worktree")
                main_root = Path(*parts[:worktree_idx])
            except (ValueError, IndexError):
                # .worktree를 찾지 못하면 현재 디렉토리 사용 (폴백)
                main_root = cwd
        else:
            # 메인 프로젝트에서 실행 중
            main_root = cwd

        # 프로젝트명별 경로 계산 (항상 메인 루트 기준)
        if project == "webserver":
            return main_root

        if project.startswith("webserver_"):
            worktree_name = project.removeprefix("webserver_")
            return main_root / ".worktree" / worktree_name

        # 알 수 없는 프로젝트명은 현재 디렉토리 반환
        return cwd

    def _print_footer(self):
        """표 푸터 및 사용 가이드 출력"""
        colors = Colors

        print(f"\n{colors.CYAN}{'='*TABLE_WIDTH}{colors.RESET}")
        print(f"\n{colors.BLUE}사용 가능한 명령어:{colors.RESET}")
        print(f"  python run.py stop [프로젝트명]   - 특정 프로젝트 중지")
        print(f"  python run.py clean [프로젝트명]  - 특정 프로젝트 완전 정리")
        print(f"  python run.py stop --all         - 모든 프로젝트 중지")
        print(f"  python run.py clean --all        - 모든 프로젝트 완전 정리\n")
