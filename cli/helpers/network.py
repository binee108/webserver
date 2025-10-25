"""네트워크 유틸리티 헬퍼 모듈

@FEAT:cli-migration @COMP:util @TYPE:helper
"""
import socket
import urllib.request
import urllib.error
from typing import Tuple, Optional


class NetworkHelper:
    """네트워크 관련 유틸리티

    TradingSystemManager의 네트워크 관련 메서드들을 독립 모듈로 분리:
    - get_local_ip()
    - get_external_ip()
    - check_port_availability()
    - find_available_port()
    """

    # 외부 IP 조회 서비스 목록
    EXTERNAL_IP_SERVICES = [
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com"
    ]

    def __init__(self, printer):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
        """
        self.printer = printer

    def get_local_ip(self) -> str:
        """로컬 네트워크 IP 주소 조회

        Returns:
            str: 로컬 IP 주소 (예: "192.168.1.100") 또는 "127.0.0.1" (실패 시)
        """
        try:
            # 임시 소켓을 만들어서 로컬 IP 확인
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def get_external_ip(services: Optional[list] = None) -> Optional[str]:
        """외부 IP 주소 조회

        Args:
            services (list, optional): IP 조회 서비스 URL 리스트

        Returns:
            str: 외부 IP 주소 또는 None (실패 시)
        """
        services = services or NetworkHelper.EXTERNAL_IP_SERVICES

        try:
            # 여러 서비스를 시도해서 외부 IP 확인
            for service in services:
                try:
                    with urllib.request.urlopen(service, timeout=5) as response:
                        return response.read().decode().strip()
                except (urllib.error.URLError, socket.timeout, OSError):
                    continue
            return None
        except Exception:
            return None

    def check_port_availability(self, port: int) -> bool:
        """포트 사용 가능 여부 확인

        Args:
            port (int): 확인할 포트 번호

        Returns:
            bool: 사용 가능하면 True, 사용 중이면 False
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result != 0  # Port is available if connection fails
        except Exception:
            return True  # Assume available if check fails

    def find_available_port(self, port_range: Tuple[int, int]) -> Optional[int]:
        """사용 가능한 포트 찾기

        Args:
            port_range (Tuple[int, int]): (시작 포트, 종료 포트)

        Returns:
            int: 사용 가능한 포트 번호 (없으면 None)
        """
        start_port, end_port = port_range

        for port in range(start_port, end_port + 1):
            if self.check_port_availability(port):
                return port

        return None
