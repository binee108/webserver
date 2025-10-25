"""Command 기본 클래스

@FEAT:cli-migration @COMP:route @TYPE:core
"""
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Optional, List


class BaseCommand(ABC):
    """CLI 명령어 기본 클래스

    모든 Command 클래스가 상속해야 하는 추상 클래스
    """

    def __init__(self, printer):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
        """
        self.printer = printer

    @abstractmethod
    def execute(self, args: list) -> int:
        """명령어 실행

        Args:
            args (list): 명령행 인자 리스트

        Returns:
            int: 종료 코드 (0=성공, 1=실패)
        """
        pass

    def print_help(self):
        """도움말 출력 (선택적 구현)"""
        pass

    def _get_all_webserver_projects(self) -> List[str]:
        """모든 webserver 프로젝트 조회

        Docker Compose ls 또는 docker ps를 사용하여 모든 webserver 프로젝트를 조회

        @FEAT:cli-migration @COMP:util @TYPE:helper

        Returns:
            List[str]: 프로젝트명 리스트 (정렬됨)
        """
        try:
            # Docker Compose ls 시도
            result = subprocess.run(
                ['docker', 'compose', 'ls', '--format', 'json'],
                capture_output=True,
                text=True,
                check=True
            )
            import json
            projects_data = json.loads(result.stdout)
            projects = set()
            for item in projects_data:
                name = item.get('Name', '')
                if name and name.startswith('webserver'):
                    projects.add(name)
            return sorted(list(projects))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            # Fallback to docker ps
            try:
                result = subprocess.run(
                    ['docker', 'ps', '-a', '--filter', 'label=com.docker.compose.project',
                     '--format', '{{.Label "com.docker.compose.project"}}'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                projects = set()
                for line in result.stdout.strip().split('\n'):
                    if line and line.startswith('webserver'):
                        projects.add(line)
                return sorted(list(projects))
            except subprocess.CalledProcessError:
                return []
