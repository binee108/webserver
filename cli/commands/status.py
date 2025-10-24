"""시스템 상태 확인 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
"""
import subprocess
import urllib.request
import urllib.error
import ssl
from pathlib import Path

from .base import BaseCommand
from cli.helpers.printer import Colors


class StatusCommand(BaseCommand):
    """시스템 상태 확인 명령어

    Docker 컨테이너 상태 및 서비스 접근성 확인
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
        """시스템 상태 확인 실행

        Args:
            args (list): 명령행 인자

        Returns:
            int: 종료 코드
        """
        try:
            self.printer.print_status("시스템 상태 확인 중...", "info")

            # Docker 설치 확인
            if not self._check_docker():
                return 1

            # 컨테이너 상태 확인
            self._check_containers()

            # 서비스 접근성 확인
            self._check_service_accessibility()

            return 0

        except Exception as e:
            self.printer.print_status(f"상태 확인 중 오류 발생: {e}", "error")
            return 1

    def _check_docker(self) -> bool:
        """Docker 실행 상태 확인

        Returns:
            bool: Docker가 실행 중이면 True
        """
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                self.printer.print_status("Docker 서비스가 실행되고 있지 않습니다.", "error")
                self.printer.print_status("Docker Desktop을 시작해주세요.", "info")
                return False

            self.printer.print_status("Docker 서비스: 실행 중", "success")
            return True

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            self.printer.print_status("Docker가 설치되지 않았거나 실행되지 않습니다.", "error")
            return False

    def _check_containers(self):
        """컨테이너 상태 출력"""
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN}📦 컨테이너 상태{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")

        try:
            # docker compose ps 실행
            result = subprocess.run(
                self.docker.compose_cmd + ['ps'],
                cwd=self.root_dir,
                capture_output=True,
                text=True
            )

            if result.stdout.strip():
                print(result.stdout)
            else:
                print("실행 중인 컨테이너가 없습니다.\n")

        except subprocess.CalledProcessError:
            print("컨테이너 상태를 확인할 수 없습니다.\n")

    def _check_service_accessibility(self):
        """서비스 접근성 확인"""
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN}🌐 서비스 접근성 확인{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")

        # 1. HTTPS 서비스 확인 (Nginx)
        self._check_https_service()

        # 2. HTTP → HTTPS 리다이렉트 확인
        self._check_http_redirect()

        # 3. 직접 Flask 접근 확인
        self._check_flask_direct()

        print()

    def _check_https_service(self):
        """HTTPS 서비스 확인 (Nginx)"""
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen('https://localhost/api/system/health', timeout=5, context=ctx) as response:
                if response.status == 200:
                    self.printer.print_status("HTTPS 서비스 (https://localhost): 정상", "success")
                else:
                    self.printer.print_status("HTTPS 서비스: 응답 이상", "warning")
        except urllib.error.URLError as e:
            self.printer.print_status(f"HTTPS 서비스: 접근 불가 (개발 모드이거나 Nginx 미실행)", "warning")
        except Exception as e:
            self.printer.print_status(f"HTTPS 서비스: 접근 불가 ({str(e)})", "error")

    def _check_http_redirect(self):
        """HTTP → HTTPS 리다이렉트 확인"""
        try:
            # 리다이렉트를 따르지 않는 요청 생성
            class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            opener = urllib.request.build_opener(NoRedirectHandler)

            try:
                response = opener.open('http://localhost', timeout=5)
                self.printer.print_status("HTTP 서비스: 리다이렉트 미작동 (보안 위험)", "warning")
            except urllib.error.HTTPError as e:
                if e.code in [301, 302]:
                    self.printer.print_status("HTTP → HTTPS 리다이렉트: 정상", "success")
                else:
                    self.printer.print_status(f"HTTP 리다이렉트: 비정상 응답 ({e.code})", "warning")
        except urllib.error.URLError:
            self.printer.print_status("HTTP 리다이렉트: Nginx 미실행 (개발 모드)", "warning")
        except Exception:
            self.printer.print_status("HTTP 리다이렉트: 확인 불가", "warning")

    def _check_flask_direct(self):
        """직접 Flask 접근 확인 (내부용)"""
        try:
            with urllib.request.urlopen('http://localhost:5001/api/system/health', timeout=5) as response:
                if response.status == 200:
                    self.printer.print_status("내부 Flask HTTP (http://localhost:5001): 정상", "success")
                else:
                    self.printer.print_status("내부 Flask HTTP: 응답 이상", "warning")
        except urllib.error.URLError:
            self.printer.print_status("내부 Flask HTTP: 접근 불가 (Flask 미실행)", "error")
        except Exception as e:
            self.printer.print_status(f"내부 Flask HTTP: 접근 불가 ({str(e)})", "error")
