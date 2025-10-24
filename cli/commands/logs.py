"""로그 조회 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
"""
import subprocess
from pathlib import Path

from .base import BaseCommand


class LogsCommand(BaseCommand):
    """로그 조회 명령어

    Docker 컨테이너 로그를 실시간으로 조회
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
        """로그 조회 실행

        Args:
            args (list): [service_name, options...] (예: ['app', '-f'])
                        service_name: 서비스 이름 (기본값: 'app')
                        -f: 실시간 로그 추적 (follow)
                        -n <lines>: 마지막 N줄만 출력

        Returns:
            int: 종료 코드
        """
        # 프로젝트명 추론
        project_name = self._infer_project_name()

        # 서비스명 파싱 (기본값: app)
        service_name = "app"
        follow = False
        tail_lines = None

        if args:
            # 첫 번째 인자가 '-'로 시작하지 않으면 서비스명으로 간주
            if not args[0].startswith('-'):
                service_name = args[0]
                args = args[1:]

            # 옵션 파싱
            i = 0
            while i < len(args):
                if args[i] == '-f' or args[i] == '--follow':
                    follow = True
                    i += 1
                elif args[i] == '-n' or args[i] == '--tail':
                    if i + 1 < len(args):
                        try:
                            tail_lines = int(args[i + 1])
                            i += 2
                        except ValueError:
                            self.printer.print_status(f"잘못된 줄 수: {args[i + 1]}", "error")
                            return 1
                    else:
                        self.printer.print_status("-n 옵션에 줄 수가 필요합니다", "error")
                        return 1
                else:
                    i += 1

        try:
            self.printer.print_status(f"{service_name} 서비스 로그 조회 중...", "info")

            # docker compose logs 명령 구성
            cmd = self.docker.compose_cmd + ['-p', project_name, 'logs']

            if follow:
                cmd.append('--follow')

            if tail_lines:
                cmd.extend(['--tail', str(tail_lines)])
            else:
                # 기본값: 최근 100줄
                cmd.extend(['--tail', '100'])

            cmd.append(service_name)

            # 로그 출력 (실시간 출력이므로 show_output=True)
            print()  # 빈 줄
            result = subprocess.run(cmd, cwd=self.root_dir)

            return 0 if result.returncode == 0 else 1

        except KeyboardInterrupt:
            # Ctrl+C로 중단
            print("\n로그 조회를 중단했습니다.")
            return 0
        except subprocess.CalledProcessError as e:
            self.printer.print_status(f"로그 조회 실패: {e}", "error")
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
                worktree_name = self.root_dir.name
                return f"webserver_{worktree_name.replace('.', '_')}"
        except Exception:
            pass

        return "webserver"

    def print_help(self):
        """도움말 출력"""
        print("사용법: python run.py logs [service_name] [options]")
        print()
        print("Arguments:")
        print("  service_name    조회할 서비스 (기본값: app)")
        print("                  사용 가능: app, postgres, nginx")
        print()
        print("Options:")
        print("  -f, --follow    실시간 로그 추적")
        print("  -n, --tail N    마지막 N줄만 출력 (기본값: 100)")
        print()
        print("Examples:")
        print("  python run.py logs                # app 서비스 로그 (최근 100줄)")
        print("  python run.py logs app -f         # app 서비스 실시간 로그")
        print("  python run.py logs postgres -n 50 # postgres 로그 (최근 50줄)")
