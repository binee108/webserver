"""시스템 재시작 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
"""
import time
import subprocess
from pathlib import Path

from .base import BaseCommand


class RestartCommand(BaseCommand):
    """시스템 재시작 명령어

    stop + start를 순차적으로 실행
    Docker 리소스 완전 해제까지 대기하여 포트 충돌 방지
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

            # 2. Docker 리소스 완전 해제 대기
            if not self._wait_for_containers_cleanup():
                self.printer.print_status("컨테이너 정리 시간 초과", "warning")
                # 경고만 출력하고 계속 진행 (StartCommand가 자체 정리 수행)

            # 3. 시스템 시작 (배너는 이미 출력했으므로 StartCommand는 배너 출력 안 함)
            # StartCommand.execute()는 내부적으로 배너를 다시 출력하므로 여기서는 그대로 호출
            if self.start_cmd.execute(args) != 0:
                self.printer.print_status("시스템 시작 단계에서 실패했습니다.", "error")
                return 1

            return 0

        except Exception as e:
            self.printer.print_status(f"시스템 재시작 실패: {e}", "error")
            return 1

    def _wait_for_containers_cleanup(self, max_wait: int = 15) -> bool:
        """Docker 컨테이너 완전 종료 대기

        Args:
            max_wait (int): 최대 대기 시간(초)

        Returns:
            bool: 모든 컨테이너가 종료되었으면 True
        """
        self.printer.print_status("Docker 리소스 정리 대기 중...", "info")

        for elapsed in range(max_wait):
            try:
                # webserver 관련 컨테이너가 모두 사라졌는지 확인
                result = subprocess.run(
                    ['docker', 'ps', '-a', '--filter', 'name=webserver', '--format', '{{.Names}}'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )

                # Priority 1: returncode 체크 (방어적 프로그래밍)
                if result.returncode != 0:
                    self.printer.print_status("Docker 명령어 실패", "warning")
                    continue

                running_containers = [line for line in result.stdout.strip().split('\n') if line]

                if not running_containers:
                    self.printer.print_status(f"컨테이너 정리 완료 ({elapsed+1}초)", "success")
                    # Docker Compose는 네트워크/볼륨을 비동기로 제거하므로
                    # 컨테이너 종료 후 추가 2초 대기로 포트 바인딩 충돌 방지
                    time.sleep(2)
                    return True

                # 1초 대기 후 재확인
                time.sleep(1)

            except subprocess.TimeoutExpired:
                self.printer.print_status("Docker 명령어 시간 초과", "warning")
                continue
            except Exception as e:
                # Priority 3: 예외 타입 포함으로 디버깅 개선
                self.printer.print_status(f"컨테이너 확인 중 오류 ({type(e).__name__}): {e}", "warning")
                continue

        # 최대 대기 시간 초과
        return False
