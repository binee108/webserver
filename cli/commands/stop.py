"""시스템 중지 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
"""
import subprocess
from pathlib import Path

from .base import BaseCommand
from cli.helpers.printer import Colors


class StopCommand(BaseCommand):
    """시스템 중지 명령어

    TradingSystemManager.stop_system() 로직을 Command 패턴으로 구현
    """

    def __init__(self, printer, docker, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            docker: DockerHelper 인스턴스
            root_dir: 프로젝트 루트 디렉토리
        """
        super().__init__(printer)
        self.docker = docker
        self.root_dir = root_dir

    def execute(self, args: list) -> int:
        """시스템 중지 실행

        Args:
            args (list): 명령행 인자 (예: ['project_name'])

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        # 프로젝트명 결정
        if args:
            project_name = args[0]
            self.printer.print_status(f"프로젝트 중지 중: {project_name}", "info")
        else:
            # 기본 프로젝트명 추론
            project_name = self._infer_project_name()
            self.printer.print_status("트레이딩 시스템 중지 중...", "info")

        try:
            # Docker Compose down 실행
            self.docker.run_command(
                self.docker.compose_cmd + ['-p', project_name, 'down'],
                cwd=self.root_dir
            )

            # 성공 메시지
            if args:
                self.printer.print_status(f"✅ {project_name} 프로젝트가 중지되었습니다.", "success")
            else:
                self.printer.print_status("시스템이 중지되었습니다.", "success")
                print(f"\n{Colors.BLUE}💡 데이터는 보존되었습니다. 다시 시작하려면 'python run.py start'를 실행하세요.{Colors.RESET}")
                print(f"{Colors.RED}🗑️  모든 데이터를 삭제하려면 'python run.py clean'을 실행하세요.{Colors.RESET}")

            return 0

        except subprocess.CalledProcessError as e:
            self.printer.print_status(f"시스템 중지 실패: {e}", "error")
            return 1
        except Exception as e:
            self.printer.print_status(f"예기치 않은 오류 발생: {e}", "error")
            return 1

    def _infer_project_name(self) -> str:
        """현재 경로 기반 프로젝트명 추론

        Returns:
            str: 프로젝트명
        """
        # 워크트리 환경 감지
        try:
            current_path = str(self.root_dir.resolve())
            if '.worktree' in current_path:
                # 워크트리 디렉토리 이름 추출
                worktree_name = self.root_dir.name
                return f"webserver_{worktree_name.replace('.', '_')}"
        except Exception:
            pass

        # 기본 프로젝트명
        return "webserver"
