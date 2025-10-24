"""Command 기본 클래스

@FEAT:cli-migration @COMP:route @TYPE:core
"""
from abc import ABC, abstractmethod
from typing import Any, Optional


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
