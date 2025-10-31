"""마이그레이션 Helper - 자동 감지 및 실행

@FEAT:cli-migration @COMP:helper @TYPE:core

역할:
1. web_server/migrations/ 디렉토리의 마이그레이션 파일 스캔
2. schema_migrations 테이블로 실행 이력 관리
3. 미실행 마이그레이션 자동 실행
"""

import importlib.util
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime


class MigrationHelper:
    """마이그레이션 자동 실행 Helper

    사용 예시:
        migration = MigrationHelper(printer, project_name)
        success = migration.run_pending_migrations()
    """

    def __init__(self, printer, project_name: str = "webserver"):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            project_name: Docker Compose 프로젝트명
        """
        self.printer = printer
        self.project_name = project_name

    def run_pending_migrations(self, root_dir: Path) -> bool:
        """미실행 마이그레이션 감지 및 실행

        Args:
            root_dir: 프로젝트 루트 디렉토리

        Returns:
            bool: 성공 여부 (마이그레이션 없으면 True)
        """
        try:
            # 마이그레이션 디렉토리 확인
            migrations_dir = root_dir / "web_server" / "migrations"
            if not migrations_dir.exists():
                self.printer.print_status(
                    "마이그레이션 디렉토리 없음, 건너뜀",
                    "info"
                )
                return True

            # PostgreSQL 컨테이너명 확인
            postgres_container = self._get_postgres_container()
            if not postgres_container:
                self.printer.print_status(
                    "PostgreSQL 컨테이너를 찾을 수 없습니다",
                    "error"
                )
                return False

            # schema_migrations 테이블 생성 (없으면)
            if not self._ensure_migrations_table(postgres_container):
                return False

            # 실행된 마이그레이션 목록 조회
            executed_migrations = self._get_executed_migrations(postgres_container)
            if executed_migrations is None:
                return False

            # 마이그레이션 파일 목록 조회 (날짜순 정렬)
            all_migrations = self._get_migration_files(migrations_dir)

            # 미실행 마이그레이션 필터링
            pending_migrations = [
                (name, path) for name, path in all_migrations
                if name not in executed_migrations
            ]

            if not pending_migrations:
                self.printer.print_status(
                    "실행할 마이그레이션 없음",
                    "info"
                )
                return True

            # 미실행 마이그레이션 실행
            self.printer.print_status(
                f"🔄 {len(pending_migrations)}개 마이그레이션 실행 시작...",
                "info"
            )

            for migration_name, migration_path in pending_migrations:
                if not self._run_migration(
                    postgres_container,
                    migration_name,
                    migration_path
                ):
                    self.printer.print_status(
                        f"❌ 마이그레이션 실패: {migration_name}",
                        "error"
                    )
                    return False

            self.printer.print_status(
                f"✅ {len(pending_migrations)}개 마이그레이션 완료",
                "success"
            )
            return True

        except Exception as e:
            self.printer.print_status(
                f"마이그레이션 실행 오류: {e}",
                "error"
            )
            return False

    def _get_postgres_container(self) -> Optional[str]:
        """PostgreSQL 컨테이너명 조회

        Returns:
            str: 컨테이너명 (없으면 None)
        """
        try:
            result = subprocess.run(
                [
                    'docker', 'ps',
                    '--filter', f'name={self.project_name}-postgres',
                    '--format', '{{.Names}}'
                ],
                capture_output=True,
                text=True,
                check=True
            )

            containers = result.stdout.strip().split('\n')
            if containers and containers[0]:
                return containers[0]
            return None

        except subprocess.CalledProcessError:
            return None

    def _ensure_migrations_table(self, container: str) -> bool:
        """schema_migrations 테이블 생성 (없으면)

        Args:
            container: PostgreSQL 컨테이너명

        Returns:
            bool: 성공 여부
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            migration_name VARCHAR(255) UNIQUE NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """

        try:
            subprocess.run(
                [
                    'docker', 'exec', '-i', container,
                    'psql', '-U', 'trader', '-d', 'trading_system',
                    '-c', create_table_sql
                ],
                capture_output=True,
                check=True
            )
            return True

        except subprocess.CalledProcessError as e:
            self.printer.print_status(
                f"schema_migrations 테이블 생성 실패: {e.stderr.decode()}",
                "error"
            )
            return False

    def _get_executed_migrations(self, container: str) -> Optional[List[str]]:
        """실행된 마이그레이션 목록 조회

        Args:
            container: PostgreSQL 컨테이너명

        Returns:
            list: 실행된 마이그레이션명 목록 (실패 시 None)
        """
        try:
            result = subprocess.run(
                [
                    'docker', 'exec', '-i', container,
                    'psql', '-U', 'trader', '-d', 'trading_system',
                    '-t', '-A',  # -t: no headers, -A: unaligned
                    '-c', 'SELECT migration_name FROM schema_migrations ORDER BY applied_at;'
                ],
                capture_output=True,
                text=True,
                check=True
            )

            migrations = result.stdout.strip().split('\n')
            return [m for m in migrations if m]  # 빈 문자열 제거

        except subprocess.CalledProcessError:
            return []

    def _get_migration_files(self, migrations_dir: Path) -> List[Tuple[str, Path]]:
        """마이그레이션 파일 목록 조회 (날짜순 정렬)

        Args:
            migrations_dir: migrations 디렉토리 경로

        Returns:
            list: (migration_name, path) 튜플 리스트
        """
        migration_files = []

        for file_path in migrations_dir.glob("*.py"):
            # __init__.py와 README는 제외
            if file_path.name in ['__init__.py'] or file_path.stem.startswith('README'):
                continue

            # 파일명에서 확장자 제거
            migration_name = file_path.stem
            migration_files.append((migration_name, file_path))

        # 파일명 기준 정렬 (날짜 프리픽스 기준)
        migration_files.sort(key=lambda x: x[0])

        return migration_files

    def _run_migration(
        self,
        container: str,
        migration_name: str,
        migration_path: Path
    ) -> bool:
        """마이그레이션 실행

        Args:
            container: PostgreSQL 컨테이너명
            migration_name: 마이그레이션명
            migration_path: 마이그레이션 파일 경로

        Returns:
            bool: 성공 여부
        """
        self.printer.print_status(
            f"  🔧 {migration_name} 실행 중...",
            "info"
        )

        try:
            # 마이그레이션 모듈 동적 로드
            spec = importlib.util.spec_from_file_location(
                "migration_module",
                migration_path
            )
            if not spec or not spec.loader:
                self.printer.print_status(
                    f"마이그레이션 파일 로드 실패: {migration_path}",
                    "error"
                )
                return False

            migration_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration_module)

            # upgrade 함수 확인
            if not hasattr(migration_module, 'upgrade'):
                self.printer.print_status(
                    f"upgrade 함수 없음: {migration_path}",
                    "error"
                )
                return False

            # SQLAlchemy 엔진 생성 (Docker 내부 접근)
            from sqlalchemy import create_engine

            # PostgreSQL 접속 정보 (Docker 네트워크 내부)
            database_url = "postgresql://trader:password123@postgres:5432/trading_system"

            # Docker exec를 통해 마이그레이션 실행
            # Python 코드를 문자열로 작성
            python_code = f"""
import sys
sys.path.insert(0, '/app/web_server')
from sqlalchemy import create_engine
import importlib.util

# 마이그레이션 모듈 로드
spec = importlib.util.spec_from_file_location(
    'migration_module',
    '/app/web_server/migrations/{migration_path.name}'
)
migration_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration_module)

# 엔진 생성 및 마이그레이션 실행
engine = create_engine('{database_url}')
migration_module.upgrade(engine)
engine.dispose()
"""

            # Docker 컨테이너 확인 (app 컨테이너 사용)
            app_container = self._get_app_container()
            if not app_container:
                # app 컨테이너가 없으면 postgres 컨테이너에서 직접 실행 (로컬)
                from sqlalchemy import create_engine

                # 로컬 접속
                local_database_url = "postgresql://trader:password123@localhost:5432/trading_system"
                engine = create_engine(local_database_url)
                migration_module.upgrade(engine)
                engine.dispose()
            else:
                # app 컨테이너에서 실행
                result = subprocess.run(
                    [
                        'docker', 'exec', '-i', app_container,
                        'python', '-c', python_code
                    ],
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    self.printer.print_status(
                        f"마이그레이션 실행 실패:\n{result.stderr}",
                        "error"
                    )
                    return False

            # 마이그레이션 이력 기록
            if not self._record_migration(container, migration_name):
                return False

            self.printer.print_status(
                f"  ✅ {migration_name} 완료",
                "success"
            )
            return True

        except Exception as e:
            self.printer.print_status(
                f"마이그레이션 실행 오류: {e}",
                "error"
            )
            import traceback
            traceback.print_exc()
            return False

    def _get_app_container(self) -> Optional[str]:
        """App 컨테이너명 조회

        Returns:
            str: 컨테이너명 (없으면 None)
        """
        try:
            result = subprocess.run(
                [
                    'docker', 'ps',
                    '--filter', f'name={self.project_name}-app',
                    '--format', '{{.Names}}'
                ],
                capture_output=True,
                text=True,
                check=True
            )

            containers = result.stdout.strip().split('\n')
            if containers and containers[0]:
                return containers[0]
            return None

        except subprocess.CalledProcessError:
            return None

    def _record_migration(self, container: str, migration_name: str) -> bool:
        """마이그레이션 이력 기록

        Args:
            container: PostgreSQL 컨테이너명
            migration_name: 마이그레이션명

        Returns:
            bool: 성공 여부
        """
        insert_sql = f"""
        INSERT INTO schema_migrations (migration_name, applied_at)
        VALUES ('{migration_name}', NOW())
        ON CONFLICT (migration_name) DO NOTHING;
        """

        try:
            subprocess.run(
                [
                    'docker', 'exec', '-i', container,
                    'psql', '-U', 'trader', '-d', 'trading_system',
                    '-c', insert_sql
                ],
                capture_output=True,
                check=True
            )
            return True

        except subprocess.CalledProcessError as e:
            self.printer.print_status(
                f"마이그레이션 이력 기록 실패: {e.stderr.decode()}",
                "error"
            )
            return False
