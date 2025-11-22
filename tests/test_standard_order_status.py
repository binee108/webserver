# @FEAT:order-status-standardization @COMP:transformer @TYPE:standardization
"""
StandardOrderStatus 클래스 TDD 테스트

거래소 중립적 표준 주문 상태 상수를 테스트합니다.
"""

import pytest
from web_server.app.constants import StandardOrderStatus


class TestStandardOrderStatus:
    """StandardOrderStatus 클래스 테스트"""

    def test_standard_order_status_constants_exist(self):
        """표준 주문 상태 상수들이 존재하는지 테스트"""
        # 기본 상태 상수 존재 확인
        assert hasattr(StandardOrderStatus, 'PENDING')
        assert hasattr(StandardOrderStatus, 'NEW')
        assert hasattr(StandardOrderStatus, 'OPEN')
        assert hasattr(StandardOrderStatus, 'PARTIALLY_FILLED')
        assert hasattr(StandardOrderStatus, 'FILLED')
        assert hasattr(StandardOrderStatus, 'CANCELLED')
        assert hasattr(StandardOrderStatus, 'CANCELED')  # 호환성용
        assert hasattr(StandardOrderStatus, 'REJECTED')
        assert hasattr(StandardOrderStatus, 'EXPIRED')
        assert hasattr(StandardOrderStatus, 'FAILED')

    def test_standard_order_status_values(self):
        """표준 주문 상태 값이 올바른지 테스트"""
        assert StandardOrderStatus.PENDING == 'PENDING'
        assert StandardOrderStatus.NEW == 'NEW'
        assert StandardOrderStatus.OPEN == 'OPEN'
        assert StandardOrderStatus.PARTIALLY_FILLED == 'PARTIALLY_FILLED'
        assert StandardOrderStatus.FILLED == 'FILLED'
        assert StandardOrderStatus.CANCELLED == 'CANCELLED'
        assert StandardOrderStatus.CANCELED == 'CANCELLED'  # CANCELLED와 동일
        assert StandardOrderStatus.REJECTED == 'REJECTED'
        assert StandardOrderStatus.EXPIRED == 'EXPIRED'
        assert StandardOrderStatus.FAILED == 'FAILED'

    def test_all_valid_statuses(self):
        """유효한 상태 목록이 올바른지 테스트"""
        valid_statuses = StandardOrderStatus.get_all_valid_statuses()

        # 필수 상태 포함 확인
        assert StandardOrderStatus.PENDING in valid_statuses
        assert StandardOrderStatus.NEW in valid_statuses
        assert StandardOrderStatus.OPEN in valid_statuses
        assert StandardOrderStatus.PARTIALLY_FILLED in valid_statuses
        assert StandardOrderStatus.FILLED in valid_statuses
        assert StandardOrderStatus.CANCELLED in valid_statuses
        assert StandardOrderStatus.REJECTED in valid_statuses
        assert StandardOrderStatus.EXPIRED in valid_statuses
        assert StandardOrderStatus.FAILED in valid_statuses

    def test_is_valid_status(self):
        """유효한 상태인지 확인하는 메서드 테스트"""
        # 유효한 상태들
        assert StandardOrderStatus.is_valid('PENDING') is True
        assert StandardOrderStatus.is_valid('NEW') is True
        assert StandardOrderStatus.is_valid('OPEN') is True
        assert StandardOrderStatus.is_valid('PARTIALLY_FILLED') is True
        assert StandardOrderStatus.is_valid('FILLED') is True
        assert StandardOrderStatus.is_valid('CANCELLED') is True
        assert StandardOrderStatus.is_valid('REJECTED') is True
        assert StandardOrderStatus.is_valid('EXPIRED') is True
        assert StandardOrderStatus.is_valid('FAILED') is True

        # 호환성 상태들
        assert StandardOrderStatus.is_valid('CANCELED') is True

        # 유효하지 않은 상태들
        assert StandardOrderStatus.is_valid('INVALID') is False
        assert StandardOrderStatus.is_valid('UNKNOWN') is False
        assert StandardOrderStatus.is_valid(None) is False
        assert StandardOrderStatus.is_valid('') is False

    def test_normalize_status(self):
        """상태 값을 표준 형식으로 정규화하는 메서드 테스트"""
        # 이미 표준 형식인 경우
        assert StandardOrderStatus.normalize('PENDING') == 'PENDING'
        assert StandardOrderStatus.normalize('FILLED') == 'FILLED'
        assert StandardOrderStatus.normalize('CANCELLED') == 'CANCELLED'

        # 호환성 처리 (CANCELED -> CANCELLED)
        assert StandardOrderStatus.normalize('CANCELED') == 'CANCELLED'
        assert StandardOrderStatus.normalize('canceled') == 'CANCELLED'

        # 대소문자 처리
        assert StandardOrderStatus.normalize('pending') == 'PENDING'
        assert StandardOrderStatus.normalize('filled') == 'FILLED'
        assert StandardOrderStatus.normalize('Cancelled') == 'CANCELLED'

        # 공백/언더스코어 처리
        assert StandardOrderStatus.normalize('partially_filled') == 'PARTIALLY_FILLED'
        assert StandardOrderStatus.normalize('partially-filled') == 'PARTIALLY_FILLED'

        # 유효하지 않은 값 처리
        assert StandardOrderStatus.normalize('INVALID') is None
        assert StandardOrderStatus.normalize(None) is None
        assert StandardOrderStatus.normalize('') is None

    def test_get_terminal_statuses(self):
        """최종 상태 목록을 올바르게 반환하는지 테스트"""
        terminal_statuses = StandardOrderStatus.get_terminal_statuses()

        # 최종 상태들 확인
        assert StandardOrderStatus.FILLED in terminal_statuses
        assert StandardOrderStatus.CANCELLED in terminal_statuses
        assert StandardOrderStatus.REJECTED in terminal_statuses
        assert StandardOrderStatus.EXPIRED in terminal_statuses
        assert StandardOrderStatus.FAILED in terminal_statuses

        # 비최종 상태들은 포함되지 않아야 함
        assert StandardOrderStatus.PENDING not in terminal_statuses
        assert StandardOrderStatus.NEW not in terminal_statuses
        assert StandardOrderStatus.OPEN not in terminal_statuses
        assert StandardOrderStatus.PARTIALLY_FILLED not in terminal_statuses

    def test_is_terminal_status(self):
        """최종 상태인지 확인하는 메서드 테스트"""
        # 최종 상태들
        assert StandardOrderStatus.is_terminal('FILLED') is True
        assert StandardOrderStatus.is_terminal('CANCELLED') is True
        assert StandardOrderStatus.is_terminal('REJECTED') is True
        assert StandardOrderStatus.is_terminal('EXPIRED') is True
        assert StandardOrderStatus.is_terminal('FAILED') is True

        # 비최종 상태들
        assert StandardOrderStatus.is_terminal('PENDING') is False
        assert StandardOrderStatus.is_terminal('NEW') is False
        assert StandardOrderStatus.is_terminal('OPEN') is False
        assert StandardOrderStatus.is_terminal('PARTIALLY_FILLED') is False

        # 유효하지 않은 상태들
        assert StandardOrderStatus.is_terminal('INVALID') is False
        assert StandardOrderStatus.is_terminal(None) is False

    def test_get_active_statuses(self):
        """활성 상태 목록을 올바르게 반환하는지 테스트"""
        active_statuses = StandardOrderStatus.get_active_statuses()

        # 활성 상태들 확인
        assert StandardOrderStatus.PENDING in active_statuses
        assert StandardOrderStatus.NEW in active_statuses
        assert StandardOrderStatus.OPEN in active_statuses
        assert StandardOrderStatus.PARTIALLY_FILLED in active_statuses

        # 최종 상태들은 포함되지 않아야 함
        assert StandardOrderStatus.FILLED not in active_statuses
        assert StandardOrderStatus.CANCELLED not in active_statuses
        assert StandardOrderStatus.REJECTED not in active_statuses

    def test_is_active_status(self):
        """활성 상태인지 확인하는 메서드 테스트"""
        # 활성 상태들
        assert StandardOrderStatus.is_active('PENDING') is True
        assert StandardOrderStatus.is_active('NEW') is True
        assert StandardOrderStatus.is_active('OPEN') is True
        assert StandardOrderStatus.is_active('PARTIALLY_FILLED') is True

        # 최종 상태들
        assert StandardOrderStatus.is_active('FILLED') is False
        assert StandardOrderStatus.is_active('CANCELLED') is False
        assert StandardOrderStatus.is_active('REJECTED') is False

        # 유효하지 않은 상태들
        assert StandardOrderStatus.is_active('INVALID') is False
        assert StandardOrderStatus.is_active(None) is False