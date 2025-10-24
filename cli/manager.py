"""CLI Manager - Command 라우팅 및 Helper 조합

@FEAT:cli-migration @COMP:route @TYPE:core

역할:
1. Helper 인스턴스 생성 및 관리
2. Command 인스턴스 생성 및 의존성 주입
3. 명령행 인자 파싱 및 Command 라우팅
"""
import sys
import argparse
from pathlib import Path
from typing import Optional

from .config import SystemConfig
from .helpers import StatusPrinter, NetworkHelper, DockerHelper, SSLHelper, EnvHelper
from .commands import (
    StartCommand, StopCommand, RestartCommand, LogsCommand,
    StatusCommand, CleanCommand, SetupCommand, ListCommand
)


class TradingSystemCLI:
    """Trading System CLI Manager

    역할:
    1. Helper 인스턴스 생성 및 관리
    2. Command 인스턴스 생성 및 의존성 주입
    3. 명령행 인자 파싱 및 Command 라우팅

    사용 예시:
        cli = TradingSystemCLI()
        exit_code = cli.run(['start'])  # python run.py start
    """

    def __init__(self):
        """초기화 - Helper 및 Command 인스턴스 생성"""
        # 설정 및 루트 디렉토리
        self.config = SystemConfig()
        self.root_dir = self.config.get_root_dir()

        # Helper 인스턴스 생성 (의존성 주입 순서 중요)
        self.printer = StatusPrinter()
        self.network = NetworkHelper(self.printer)
        self.docker = DockerHelper(self.printer, self.root_dir)
        self.ssl = SSLHelper(self.printer, self.root_dir)
        self.env = EnvHelper(self.printer, self.network, self.root_dir)  # Phase 2 수정 반영

        # Command 인스턴스 생성 (의존성 주입)
        self.commands = self._create_commands()

    def _create_commands(self) -> dict:
        """Command 인스턴스 생성

        의존성 주입을 통해 Command에 필요한 Helper들을 전달합니다.
        RestartCommand는 StopCommand와 StartCommand를 조합합니다.

        Returns:
            dict: 명령어명 → Command 인스턴스 매핑
        """
        # StartCommand
        start_cmd = StartCommand(
            self.printer, self.docker, self.network,
            self.ssl, self.env, self.root_dir
        )

        # StopCommand
        stop_cmd = StopCommand(self.printer, self.docker, self.root_dir)

        # RestartCommand (Command 조합)
        restart_cmd = RestartCommand(self.printer, stop_cmd, start_cmd)

        # LogsCommand
        logs_cmd = LogsCommand(self.printer, self.docker, self.root_dir)

        # StatusCommand
        status_cmd = StatusCommand(self.printer, self.docker, self.root_dir)

        # CleanCommand
        clean_cmd = CleanCommand(self.printer, self.docker, self.ssl, self.root_dir)

        # SetupCommand
        setup_cmd = SetupCommand(self.printer, self.env, self.docker, self.root_dir)

        # ListCommand
        list_cmd = ListCommand(self.printer, self.docker)

        return {
            'start': start_cmd,
            'stop': stop_cmd,
            'restart': restart_cmd,
            'logs': logs_cmd,
            'status': status_cmd,
            'clean': clean_cmd,
            'setup': setup_cmd,
            'ls': list_cmd,  # ls 명령어 추가
        }

    def run(self, args: list) -> int:
        """CLI 실행

        명령행 인자를 파싱하고 해당 Command를 실행합니다.

        Args:
            args (list): 명령행 인자 (sys.argv[1:])
                예: ['start'], ['logs', '-f', 'app'], ['clean', '--all']

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        # 명령어 파싱
        if not args or args[0] in ['-h', '--help']:
            self.print_help()
            return 0

        command_name = args[0]
        command_args = args[1:]

        # Command 조회
        command = self.commands.get(command_name)

        if not command:
            self.printer.print_status(f"알 수 없는 명령어: {command_name}", "error")
            self.print_help()
            return 1

        # Command 실행
        try:
            return command.execute(command_args)
        except Exception as e:
            self.printer.print_status(f"명령어 실행 실패: {e}", "error")
            import traceback
            traceback.print_exc()
            return 1

    def print_help(self):
        """도움말 출력

        사용 가능한 명령어와 옵션을 표시합니다.
        """
        from .helpers.printer import Colors

        help_text = f"""
{Colors.CYAN}{'='*60}
{Colors.BOLD}암호화폐 트레이딩 시스템 CLI{Colors.RESET}
{Colors.CYAN}{'='*60}{Colors.RESET}

사용법:
  python run.py <명령어> [옵션]

명령어:
  start       - 시스템 시작
  stop        - 시스템 중지
  restart     - 시스템 재시작
  logs        - Docker 로그 조회
  status      - 시스템 상태 확인
  clean       - 시스템 정리 (컨테이너/볼륨)
  setup       - 초기 환경 설정
  ls          - 실행 중인 프로젝트 목록

옵션:
  -h, --help  - 도움말 표시

예제:
  python run.py start
  python run.py logs -f app
  python run.py clean --all
  python run.py setup --env production

상세 도움말:
  python run.py <명령어> --help
"""
        print(help_text)
