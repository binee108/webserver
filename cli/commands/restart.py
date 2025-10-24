"""시스템 재시작 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
"""
import time
from pathlib import Path

from .base import BaseCommand


class RestartCommand(BaseCommand):
    """시스템 재시작 명령어

    stop + start를 순차적으로 실행
    """

    def __init__(self, printer, stop_cmd, start_cmd):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            stop_cmd: StopCommand 인스턴스
            start_cmd: StartCommand 인스턴스
        """
        super().__init__(printer)
        self.stop_cmd = stop_cmd
        self.start_cmd = start_cmd

    def execute(self, args: list) -> int:
        """시스템 재시작 실행

        Args:
            args (list): 명령행 인자

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        try:
            # 배너 출력
            self.printer.print_banner()
            self.printer.print_status("시스템 재시작 중...", "info")

            # 1. 시스템 중지
            if self.stop_cmd.execute(args) != 0:
                self.printer.print_status("시스템 중지 단계에서 실패했습니다.", "error")
                return 1

            # 2. 컨테이너 정리 대기
            self.printer.print_status("컨테이너 정리 대기 중...", "info")
            time.sleep(5)

            # 3. 시스템 시작 (배너는 이미 출력했으므로 StartCommand는 배너 출력 안 함)
            # StartCommand.execute()는 내부적으로 배너를 다시 출력하므로 여기서는 그대로 호출
            if self.start_cmd.execute(args) != 0:
                self.printer.print_status("시스템 시작 단계에서 실패했습니다.", "error")
                return 1

            return 0

        except Exception as e:
            self.printer.print_status(f"시스템 재시작 실패: {e}", "error")
            return 1
