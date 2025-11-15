"""데이터베이스 삭제 명령어

@FEAT:cli-migration @COMP:route @TYPE:core
@DEPS:worktree-conflict-resolution
"""
import shutil
from pathlib import Path

from .base import BaseCommand
from cli.helpers.printer import Colors


class DeleteDbCommand(BaseCommand):
    """데이터베이스 삭제 명령어

    실행 컨텍스트(워크트리 vs 프로젝트 루트)를 자동 감지하여
    해당 위치의 DB만 삭제합니다.

    삭제 대상:
    - postgres_data/ (PostgreSQL 데이터)
    - web_server/*.db (SQLite 파일)
    - flask_session/ (세션 캐시, 있으면)
    """

    def __init__(self, printer, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            root_dir: 프로젝트 루트 디렉토리 (Path)
        """
        super().__init__(printer)
        self.root_dir = root_dir
        self.is_worktree = self._detect_worktree_environment()

    def _detect_worktree_environment(self) -> bool:
        """워크트리 환경 감지

        Returns:
            bool: 워크트리 환경이면 True
        """
        # StartCommand와 동일한 로직 사용 (일관성)
        try:
            current_path = str(self.root_dir.resolve())
            return '.worktree' in current_path
        except Exception:
            return False

    def execute(self, args: list) -> int:
        """데이터베이스 삭제 실행

        Args:
            args (list): 명령행 인자 (현재는 사용하지 않음)

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        # 컨텍스트 표시
        context = "워크트리" if self.is_worktree else "프로젝트 루트"
        self.printer.print_status(f"데이터베이스 삭제 ({context})", "warning")

        # 삭제 대상 파일/디렉토리 수집
        targets = self._collect_deletion_targets()

        if not targets:
            self.printer.print_status("삭제할 데이터베이스 파일이 없습니다.", "info")
            return 0

        # 삭제 대상 표시
        self._display_deletion_targets(targets, context)

        # 확인 프롬프트
        if not self._confirm_deletion():
            self.printer.print_status("작업이 취소되었습니다.", "info")
            return 0

        # 삭제 수행
        return self._perform_deletion(targets)

    def _collect_deletion_targets(self) -> list[Path]:
        """삭제 대상 파일/디렉토리 수집

        Returns:
            list[Path]: 존재하는 삭제 대상 경로 리스트
        """
        targets = []

        # PostgreSQL 데이터 디렉토리
        postgres_data = self.root_dir / 'postgres_data'
        if postgres_data.exists() and postgres_data.is_dir():
            targets.append(postgres_data)

        # SQLite 파일
        web_server_dir = self.root_dir / 'web_server'
        if web_server_dir.exists():
            for db_file in web_server_dir.glob('*.db'):
                if db_file.is_file():
                    targets.append(db_file)

        # Flask 세션 캐시 (있으면)
        flask_session = self.root_dir / 'flask_session'
        if flask_session.exists() and flask_session.is_dir():
            targets.append(flask_session)

        return targets

    def _display_deletion_targets(self, targets: list[Path], context: str):
        """삭제 대상 표시

        Args:
            targets (list[Path]): 삭제 대상 경로 리스트
            context (str): 실행 컨텍스트 ("워크트리" or "프로젝트 루트")
        """
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  경고: 다음 항목들이 완전히 삭제됩니다:{Colors.RESET}")
        print(f"{Colors.YELLOW}실행 위치: {context}{Colors.RESET}\n")

        for target in targets:
            relative_path = target.relative_to(self.root_dir)
            if target.is_dir():
                print(f"{Colors.RED}  • {relative_path}/ (디렉토리 전체){Colors.RESET}")
            else:
                size_mb = target.stat().st_size / (1024 * 1024)
                print(f"{Colors.RED}  • {relative_path} ({size_mb:.2f} MB){Colors.RESET}")

        print(f"\n{Colors.YELLOW}이 작업은 되돌릴 수 없습니다!{Colors.RESET}\n")

    def _confirm_deletion(self) -> bool:
        """사용자 확인 프롬프트

        Note: 'yes' 전체 입력만 허용 (CleanCommand의 ['yes', 'y']와 다름)
        이유: 데이터베이스 삭제는 복구 불가능하므로 더 엄격한 확인 필요

        Returns:
            bool: 삭제 승인 시 True
        """
        confirm = input(f"{Colors.RED}정말로 데이터베이스를 삭제하시겠습니까? (yes/no): {Colors.RESET}")
        return confirm.lower() == 'yes'

    def _perform_deletion(self, targets: list[Path]) -> int:
        """삭제 수행

        Args:
            targets (list[Path]): 삭제 대상 경로 리스트

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        success_count = 0
        failed_targets = []

        for target in targets:
            try:
                if target.is_symlink():
                    # Symlink 자체만 삭제 (대상을 따라가지 않음)
                    target.unlink()
                    self.printer.print_status(f"✅ 삭제 완료: {target.name} (symlink)", "success")
                elif target.is_dir():
                    # 디렉토리 삭제 (보안: symlink 따라가지 않음)
                    shutil.rmtree(target, ignore_errors=False)
                    self.printer.print_status(f"✅ 삭제 완료: {target.name}/", "success")
                else:
                    # 파일 삭제
                    target.unlink()
                    self.printer.print_status(f"✅ 삭제 완료: {target.name}", "success")

                success_count += 1
            except PermissionError as e:
                self.printer.print_status(
                    f"❌ 권한 오류: {target.name} - {e}",
                    "error"
                )
                failed_targets.append(target)
            except Exception as e:
                self.printer.print_status(
                    f"❌ 삭제 실패: {target.name} - {e}",
                    "error"
                )
                failed_targets.append(target)

        # 결과 요약
        print()
        if success_count == len(targets):
            self.printer.print_status(
                f"데이터베이스 삭제 완료 ({success_count}개 항목)",
                "success"
            )
            return 0
        elif success_count > 0:
            self.printer.print_status(
                f"일부 삭제 완료 ({success_count}/{len(targets)})",
                "warning"
            )
            return 1
        else:
            self.printer.print_status("모든 삭제 작업 실패", "error")
            return 1
