"""환경 설정 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
"""
from pathlib import Path

from .base import BaseCommand


class SetupCommand(BaseCommand):
    """환경 설정 명령어

    초기 환경 설정 및 요구사항 확인
    """

    def __init__(self, printer, env, docker, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            env: EnvHelper 인스턴스
            docker: DockerHelper 인스턴스
            root_dir: 프로젝트 루트 디렉토리
        """
        super().__init__(printer)
        self.env = env
        self.docker = docker
        self.root_dir = root_dir

    def execute(self, args: list) -> int:
        """환경 설정 실행

        Args:
            args (list): 명령행 인자
                        --env <type>: 환경 타입 지정 (development, staging, production)

        Returns:
            int: 종료 코드
        """
        # 환경 타입 파싱
        env_type = None
        if '--env' in args:
            try:
                env_idx = args.index('--env')
                if env_idx + 1 < len(args):
                    env_type = args[env_idx + 1]
            except (ValueError, IndexError):
                pass

        try:
            # 배너 출력
            self.printer.print_banner()
            self.printer.print_status("환경 설정을 시작합니다...", "info")

            # 1. 시스템 요구사항 확인
            if not self._check_requirements():
                return 1

            # 2. 환경 설정 마법사 실행
            if not self.env.setup_environment(env_type):
                self.printer.print_status("환경 설정이 취소되었습니다.", "warning")
                return 1

            # 3. 설정 완료 메시지
            print()
            self.printer.print_status("✅ 환경 설정이 완료되었습니다!", "success")
            print()
            print("다음 명령으로 시스템을 시작할 수 있습니다:")
            print("  python run.py start")
            print()

            return 0

        except Exception as e:
            self.printer.print_status(f"환경 설정 실패: {e}", "error")
            return 1

    def _check_requirements(self) -> bool:
        """시스템 요구사항 확인

        Returns:
            bool: 모든 요구사항 충족 시 True
        """
        self.printer.print_status("시스템 요구사항 확인 중...", "info")

        # Docker 설치 및 실행 확인
        if not self.docker.check_requirements():
            return False

        # 추가 요구사항 확인 (필요 시)
        # - Python 버전
        # - 필수 패키지
        # - 디스크 공간
        # 등...

        return True

    def print_help(self):
        """도움말 출력"""
        print("사용법: python run.py setup [options]")
        print()
        print("Options:")
        print("  --env <type>    환경 타입 지정 (development, staging, production)")
        print("                  지정하지 않으면 대화형 설정 모드로 진행됩니다.")
        print()
        print("Examples:")
        print("  python run.py setup                    # 대화형 설정")
        print("  python run.py setup --env development  # 개발 환경 자동 설정")
        print("  python run.py setup --env production   # 운영 환경 자동 설정")
