"""시스템 정리 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
"""
import subprocess
import shutil
from pathlib import Path

from .base import BaseCommand
from cli.helpers.printer import Colors


class CleanCommand(BaseCommand):
    """시스템 정리 명령어

    TradingSystemManager.clean_system() 로직을 Command 패턴으로 구현
    """

    def __init__(self, printer, docker, ssl, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            docker: DockerHelper 인스턴스
            ssl: SSLHelper 인스턴스 (인증서 정리용)
            root_dir: 프로젝트 루트 디렉토리
        """
        super().__init__(printer)
        self.docker = docker
        self.ssl = ssl
        self.root_dir = root_dir

    def execute(self, args: list) -> int:
        """시스템 정리 실행

        Args:
            args (list): ['--all'] 또는 ['--full'] 또는 ['project_name'] 등
                        --all: 모든 webserver 프로젝트 정리
                        --full: SSL/로그도 함께 정리 (현재 프로젝트 또는 --all과 조합)
                        project_name: 특정 프로젝트만 정리

        Returns:
            int: 종료 코드
        """
        # 옵션 파싱 (독립적으로)
        clean_all_projects = '--all' in args      # 모든 프로젝트 정리
        clean_ssl_logs = '--full' in args         # SSL/로그도 정리

        # 특정 프로젝트 정리 (프로젝트명이 첫 번째 인자일 때)
        if args and not args[0].startswith('--'):
            project_name = args[0]

            # --full 옵션은 특정 프로젝트 정리 시 무시 (경고 출력)
            if clean_ssl_logs:
                self.printer.print_status(
                    "⚠️  특정 프로젝트 정리 시 --full 옵션은 무시됩니다. (SSL/로그는 모든 프로젝트가 공유)",
                    "warning"
                )

            return self._clean_specific_project(project_name)

        # --all 옵션: 모든 프로젝트 정리
        if clean_all_projects:
            return self._clean_all_projects(clean_ssl_logs)

        # 기본: 현재 프로젝트만 정리
        return self._clean_current_project(clean_ssl_logs)

    def _clean_current_project(self, clean_ssl_logs: bool = False) -> int:
        """현재 프로젝트 정리

        Args:
            clean_ssl_logs (bool): SSL 인증서 및 로그 파일도 함께 삭제할지 여부

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        try:
            # 프로젝트명 추론
            project_name = self._infer_project_name()

            self.printer.print_status("시스템 완전 정리를 시작합니다...", "warning")

            # 상세한 경고 메시지
            print(f"\n{Colors.RED}{Colors.BOLD}⚠️  경고: 다음 항목들이 완전히 삭제됩니다:{Colors.RESET}")
            print(f"{Colors.RED}  • 모든 데이터베이스 데이터 (사용자, 거래기록, 설정 등){Colors.RESET}")

            if clean_ssl_logs:
                print(f"{Colors.RED}  • SSL 인증서 파일 (./certs/ 디렉토리){Colors.RESET}")
                print(f"{Colors.RED}  • 로그 파일 (./web_server/logs/ 디렉토리){Colors.RESET}")

            print(f"{Colors.RED}  • Docker 이미지 (재빌드 필요){Colors.RESET}")
            print(f"{Colors.RED}  • Docker 볼륨 및 네트워크{Colors.RESET}")
            print(f"\n{Colors.YELLOW}이 작업은 되돌릴 수 없습니다!{Colors.RESET}\n")

            # 확인 메시지
            confirm = input(f"{Colors.RED}정말로 모든 데이터를 삭제하시겠습니까? (yes/no): {Colors.RESET}")

            if confirm.lower() not in ['yes', 'y']:
                self.printer.print_status("작업이 취소되었습니다.", "info")
                return 0

            # 1. Docker 컨테이너, 볼륨, 이미지 삭제
            self._clean_docker_resources(project_name)

            # 2. SSL 인증서 삭제 (--full 옵션 시)
            if clean_ssl_logs:
                self._clean_ssl_certificates()

            # 3. 로그 파일 삭제 (--full 옵션 시)
            if clean_ssl_logs:
                self._clean_logs()

            # 4. Docker 시스템 정리
            self._clean_docker_system()

            print(f"\n{Colors.GREEN}✅ 시스템 정리가 완료되었습니다!{Colors.RESET}\n")
            return 0

        except Exception as e:
            self.printer.print_status(f"시스템 정리 실패: {e}", "error")
            return 1

    def _clean_all_projects(self, clean_ssl_logs: bool = False) -> int:
        """모든 webserver 프로젝트 정리

        Args:
            clean_ssl_logs (bool): SSL 인증서 및 로그 파일도 함께 삭제할지 여부

        Returns:
            int: 종료 코드 (0=모두 성공, 1=일부 실패)
        """
        self.printer.print_status("모든 webserver 프로젝트 정리를 시작합니다...", "warning")

        # 모든 webserver 프로젝트 조회 (BaseCommand 메서드 사용)
        projects = super()._get_all_webserver_projects()

        if not projects:
            self.printer.print_status("실행 중인 webserver 프로젝트가 없습니다.", "info")
            return 0

        # 상세한 경고 메시지
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  경고: 다음 프로젝트들이 완전히 삭제됩니다:{Colors.RESET}")
        for project in projects:
            print(f"{Colors.RED}  • {project}{Colors.RESET}")
        print(f"{Colors.RED}  • 모든 데이터베이스 데이터 (사용자, 거래기록, 설정 등){Colors.RESET}")
        print(f"{Colors.RED}  • Docker 이미지 (재빌드 필요){Colors.RESET}")
        print(f"{Colors.RED}  • Docker 볼륨 및 네트워크{Colors.RESET}")

        if clean_ssl_logs:
            print(f"{Colors.RED}  • SSL 인증서 파일 (./certs/ 디렉토리){Colors.RESET}")
            print(f"{Colors.RED}  • 로그 파일 (./web_server/logs/ 디렉토리){Colors.RESET}")

        print(f"\n{Colors.YELLOW}이 작업은 되돌릴 수 없습니다!{Colors.RESET}\n")

        # 확인 메시지
        confirm = input(f"{Colors.RED}정말로 {len(projects)}개 프로젝트를 모두 삭제하시겠습니까? (yes/no): {Colors.RESET}")

        if confirm.lower() not in ['yes', 'y']:
            self.printer.print_status("작업이 취소되었습니다.", "info")
            return 0

        # 각 프로젝트 정리 (Best-effort)
        failed_projects = []
        cleaned_count = 0

        for project in projects:
            try:
                self.printer.print_status(f"  → {project} 정리 중...", "info")

                # docker compose down --rmi all -v 실행
                self.docker.run_command(
                    self.docker.compose_cmd + ['-p', project, 'down', '--rmi', 'all', '-v'],
                    cwd=self.root_dir
                )

                cleaned_count += 1
                self.printer.print_status(f"  ✓ {project} 정리 완료", "success")

            except subprocess.CalledProcessError as e:
                # 이미지 삭제 실패 시 볼륨만이라도 삭제 시도
                try:
                    self.printer.print_status(f"  ⚠️  {project} 이미지 삭제 실패, 볼륨만 정리 시도...", "warning")
                    self.docker.run_command(
                        self.docker.compose_cmd + ['-p', project, 'down', '-v'],
                        cwd=self.root_dir
                    )
                    cleaned_count += 1
                    self.printer.print_status(f"  ✓ {project} 부분 정리 완료 (이미지 제외)", "success")
                except subprocess.CalledProcessError:
                    self.printer.print_status(f"  ✗ {project} 정리 실패", "error")
                    failed_projects.append(project)
            except Exception as e:
                self.printer.print_status(f"  ✗ {project} 정리 중 오류: {e}", "error")
                failed_projects.append(project)

        # SSL/로그 정리 (--full 옵션 시)
        if clean_ssl_logs:
            self._clean_ssl_certificates()
            self._clean_logs()

        # Docker 시스템 정리
        self._clean_docker_system()

        # 결과 요약
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        if failed_projects:
            self.printer.print_status(
                f"⚠️  {cleaned_count}/{len(projects)}개 프로젝트 정리 완료 (실패: {', '.join(failed_projects)})",
                "warning"
            )
            return 1
        else:
            self.printer.print_status(f"✅ {cleaned_count}개 프로젝트가 모두 정리되었습니다!", "success")
            return 0

    def _clean_specific_project(self, project_name: str) -> int:
        """특정 프로젝트 정리

        Args:
            project_name (str): 정리할 프로젝트명

        Returns:
            int: 종료 코드
        """
        self.printer.print_status(f"프로젝트 정리 중: {project_name}", "warning")

        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  경고: 다음 항목들이 삭제됩니다:{Colors.RESET}")
        print(f"{Colors.RED}  • {project_name} 프로젝트의 모든 데이터{Colors.RESET}")
        print(f"{Colors.RED}  • Docker 볼륨 및 네트워크{Colors.RESET}")
        print(f"{Colors.RED}  • Docker 이미지{Colors.RESET}")
        print(f"\n{Colors.YELLOW}이 작업은 되돌릴 수 없습니다!{Colors.RESET}\n")

        confirm = input(f"{Colors.RED}정말로 {project_name} 프로젝트를 삭제하시겠습니까? (yes/no): {Colors.RESET}")

        if confirm.lower() not in ['yes', 'y']:
            self.printer.print_status("작업이 취소되었습니다.", "info")
            return 0

        try:
            # 볼륨 포함 완전 삭제
            self.docker.run_command(
                self.docker.compose_cmd + ['-p', project_name, 'down', '--rmi', 'all', '-v'],
                cwd=self.root_dir
            )
            self.printer.print_status(f"✅ {project_name} 프로젝트 정리 완료", "success")

            # Docker 시스템 정리
            self._clean_docker_system()

            return 0

        except subprocess.CalledProcessError:
            # 이미지 삭제 실패 시 볼륨만이라도 삭제 시도
            try:
                self.docker.run_command(
                    self.docker.compose_cmd + ['-p', project_name, 'down', '-v'],
                    cwd=self.root_dir
                )
                self.printer.print_status(f"⚠️  {project_name} 부분 정리 완료 (이미지 제외)", "warning")
                return 0
            except subprocess.CalledProcessError as e:
                self.printer.print_status(f"❌ {project_name} 정리 실패: {e}", "error")
                return 1

    def _clean_docker_resources(self, project_name: str):
        """Docker 컨테이너, 볼륨, 이미지 삭제

        Args:
            project_name (str): 프로젝트명
        """
        self.printer.print_status("Docker 컨테이너, 볼륨, 이미지 삭제 중...", "info")

        try:
            self.docker.run_command(
                self.docker.compose_cmd + ['-p', project_name, 'down', '--rmi', 'all', '-v'],
                cwd=self.root_dir
            )
            self.printer.print_status("Docker 컨테이너, 볼륨, 이미지 삭제 완료", "success")
        except subprocess.CalledProcessError as e:
            self.printer.print_status(f"Docker 정리 중 일부 오류 발생: {e}", "warning")

            # 기본 정리라도 시도
            try:
                self.docker.run_command(
                    self.docker.compose_cmd + ['-p', project_name, 'down', '-v'],
                    cwd=self.root_dir
                )
                self.printer.print_status("기본 Docker 정리 완료", "success")
            except subprocess.CalledProcessError:
                self.printer.print_status("Docker 정리 실패", "error")

    def _clean_ssl_certificates(self):
        """SSL 인증서 삭제"""
        cert_dir = self.root_dir / "certs"

        if cert_dir.exists():
            self.printer.print_status("SSL 인증서 삭제 중...", "info")
            try:
                shutil.rmtree(cert_dir)
                self.printer.print_status("SSL 인증서 삭제 완료", "success")
            except Exception as e:
                self.printer.print_status(f"SSL 인증서 삭제 실패: {e}", "error")
        else:
            self.printer.print_status("SSL 인증서 디렉토리가 존재하지 않습니다", "info")

    def _clean_logs(self):
        """로그 파일 삭제"""
        log_dir = self.root_dir / "web_server" / "logs"

        if log_dir.exists():
            self.printer.print_status("로그 파일 삭제 중...", "info")
            try:
                shutil.rmtree(log_dir)
                log_dir.mkdir()  # 빈 디렉토리 재생성
                self.printer.print_status("로그 파일 삭제 완료", "success")
            except Exception as e:
                self.printer.print_status(f"로그 파일 삭제 실패: {e}", "error")
        else:
            self.printer.print_status("로그 디렉토리가 존재하지 않습니다", "info")

    def _clean_docker_system(self):
        """Docker 시스템 정리 (미사용 볼륨, 네트워크)"""
        self.printer.print_status("Docker 시스템 정리 중...", "info")

        try:
            # 미사용 볼륨 정리
            subprocess.run(['docker', 'volume', 'prune', '-f'], capture_output=True)

            # 미사용 네트워크 정리
            subprocess.run(['docker', 'network', 'prune', '-f'], capture_output=True)

            self.printer.print_status("Docker 시스템 정리 완료", "success")
        except subprocess.CalledProcessError as e:
            self.printer.print_status(f"Docker 시스템 정리 중 오류: {e}", "warning")

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
