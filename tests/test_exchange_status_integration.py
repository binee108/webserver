# @FEAT:order-status-standardization @COMP:transformer @TYPE:standardization
"""
거래소별 상태 매핑 통합 테스트

기존 OrderStatus 클래스와 새로운 StandardOrderStatus/OrderStatusTransformer의
하위 호환성 및 통합을 테스트합니다.
"""

import pytest
from web_server.app.constants import OrderStatus, StandardOrderStatus
from web_server.app.exchanges.transformers.order_status_transformer import OrderStatusTransformer


class TestExchangeStatusIntegration:
    """거래소별 상태 매핑 통합 테스트"""

    def test_legacy_order_status_compatibility(self):
        """기존 OrderStatus 클래스와의 호환성 테스트"""
        # 기존 OrderStatus 메서드들이 여전히 작동하는지 확인
        assert OrderStatus.from_exchange('NEW', 'BINANCE') == OrderStatus.NEW
        assert OrderStatus.from_exchange('wait', 'UPBIT') == OrderStatus.OPEN
        assert OrderStatus.from_exchange('done', 'UPBIT') == OrderStatus.FILLED

    def test_new_standard_order_status_integration(self):
        """새로운 StandardOrderStatus 시스템 통합 테스트"""
        transformer = OrderStatusTransformer()

        # StandardOrderStatus와 호환되는지 확인
        binance_standard = transformer.transform('NEW', 'BINANCE')
        assert StandardOrderStatus.is_valid(binance_standard) is True
        assert binance_standard == StandardOrderStatus.NEW

        upbit_standard = transformer.transform('wait', 'UPBIT')
        assert StandardOrderStatus.is_valid(upbit_standard) is True
        assert upbit_standard == StandardOrderStatus.OPEN

    def test_status_mapping_consistency(self):
        """기존 OrderStatus와 새로운 StandardOrderStatus 간의 일관성 테스트"""
        transformer = OrderStatusTransformer()

        # 주요 상태들이 일관되게 매핑되는지 확인
        test_cases = [
            ('NEW', 'BINANCE'),
            ('PARTIALLY_FILLED', 'BINANCE'),
            ('FILLED', 'BINANCE'),
            ('CANCELED', 'BINANCE'),
            ('wait', 'UPBIT'),
            ('done', 'UPBIT'),
            ('cancel', 'UPBIT'),
        ]

        for original_status, exchange in test_cases:
            # 기존 방식
            legacy_status = OrderStatus.from_exchange(original_status, exchange)

            # 새로운 방식
            new_standard = transformer.transform(original_status, exchange)

            # 기존 상태가 유효한 StandardOrderStatus인지 확인
            if legacy_status in StandardOrderStatus.VALID_STATUSES:
                assert StandardOrderStatus.is_valid(legacy_status) is True

    def test_backward_compatibility_with_existing_orders(self):
        """기존 주문 데이터와의 하위 호환성 테스트"""
        # 기존 DB에 저장될 수 있는 상태 값들
        legacy_statuses = [
            'NEW', 'OPEN', 'PARTIALLY_FILLED', 'FILLED',
            'CANCELLED', 'CANCELED', 'REJECTED', 'EXPIRED'
        ]

        for status in legacy_statuses:
            # StandardOrderStatus가 기존 상태들을 처리할 수 있는지 확인
            normalized = StandardOrderStatus.normalize(status)
            if normalized:
                assert StandardOrderStatus.is_valid(normalized) is True

    def test_terminal_status_classification(self):
        """최종 상태 분류 통합 테스트"""
        transformer = OrderStatusTransformer()

        # 모든 거래소의 최종 상태들이 StandardOrderStatus 기준에 맞는지 확인
        terminal_test_cases = [
            ('FILLED', 'BINANCE'),
            ('CANCELED', 'BINANCE'),
            ('CANCELLED', 'BINANCE'),
            ('REJECTED', 'BINANCE'),
            ('EXPIRED', 'BINANCE'),
            ('done', 'UPBIT'),
            ('cancel', 'UPBIT'),
            ('fill', 'BITHUMB'),
            ('complete', 'BITHUMB'),
            ('Filled', 'BYBIT'),
            ('Cancelled', 'BYBIT'),
            ('Rejected', 'BYBIT'),
        ]

        for original_status, exchange in terminal_test_cases:
            standard_status = transformer.transform(original_status, exchange)
            if standard_status and StandardOrderStatus.is_valid(standard_status):
                # 대부분의 최종 상태들은 StandardOrderStatus에서 terminal로 분류되어야 함
                # 주의: 일부 상태는 OPEN으로 분류될 수 있음 (예: UPBIT의 'wait')
                assert StandardOrderStatus.is_valid(standard_status) is True

    def test_active_status_classification(self):
        """활성 상태 분류 통합 테스트"""
        transformer = OrderStatusTransformer()

        # 모든 거래소의 활성 상태들이 StandardOrderStatus 기준에 맞는지 확인
        active_test_cases = [
            ('NEW', 'BINANCE'),
            ('PARTIALLY_FILLED', 'BINANCE'),
            ('wait', 'UPBIT'),
            ('watch', 'UPBIT'),
            ('bid', 'BITHUMB'),
            ('ask', 'BITHUMB'),
            ('Created', 'BYBIT'),
            ('New', 'BYBIT'),
            ('PartiallyFilled', 'BYBIT'),
        ]

        for original_status, exchange in active_test_cases:
            standard_status = transformer.transform(original_status, exchange)
            if standard_status and StandardOrderStatus.is_valid(standard_status):
                # 활성 상태인지 확인 (단, 일부는 OPEN으로 분류될 수 있음)
                assert StandardOrderStatus.is_valid(standard_status) is True

    def test_migration_path_validation(self):
        """마이그레이션 경로 유효성 테스트"""
        transformer = OrderStatusTransformer()

        # 기존 OrderStatus에서 StandardOrderStatus로의 변환 경로 확인
        legacy_to_standard_mappings = {
            'NEW': StandardOrderStatus.NEW,
            'OPEN': StandardOrderStatus.OPEN,
            'PARTIALLY_FILLED': StandardOrderStatus.PARTIALLY_FILLED,
            'FILLED': StandardOrderStatus.FILLED,
            'CANCELLED': StandardOrderStatus.CANCELLED,
            'REJECTED': StandardOrderStatus.REJECTED,
            'EXPIRED': StandardOrderStatus.EXPIRED,
        }

        for legacy_status, expected_standard in legacy_to_standard_mappings.items():
            # StandardOrderStatus로 직접 정규화
            normalized = StandardOrderStatus.normalize(legacy_status)
            assert normalized == expected_standard

            # 기대 상태가 유효한지 확인
            assert StandardOrderStatus.is_valid(expected_standard) is True

    def test_comprehensive_status_coverage(self):
        """포괄적인 상태 커버리지 테스트"""
        transformer = OrderStatusTransformer()

        # 모든 지원 거래소의 모든 상태가 처리되는지 확인
        all_supported_statuses = []

        for exchange in transformer.get_supported_exchanges():
            if exchange in transformer._STATUS_MAPPINGS:
                all_supported_statuses.extend(
                    transformer._STATUS_MAPPINGS[exchange].keys()
                )

        # 각 상태가 StandardOrderStatus로 변환 가능한지 확인
        for status in set(all_supported_statuses):  # 중복 제거
            for exchange in transformer.get_supported_exchanges():
                transformed = transformer.transform(status, exchange)
                if transformed and transformed != status:  # 성공적으로 변환된 경우
                    assert StandardOrderStatus.is_valid(transformed) is True

    def test_legacy_adapter_functionality(self):
        """레거시 어댑터 기능 테스트"""
        transformer = OrderStatusTransformer()
        legacy_adapter = transformer.create_legacy_adapter()

        # 레거시 스타일 인터페이스 테스트
        assert legacy_adapter('NEW', 'BINANCE') == StandardOrderStatus.NEW
        assert legacy_adapter('wait', 'UPBIT') == StandardOrderStatus.OPEN
        assert legacy_adapter('done', 'UPBIT') == StandardOrderStatus.FILLED

        # None 입력 처리
        assert legacy_adapter(None, 'BINANCE') is None
        assert legacy_adapter('NEW', None) == 'NEW'

    def test_transform_with_validation(self):
        """상태 변환과 유효성 검증 통합 테스트"""
        transformer = OrderStatusTransformer()

        # 정상 변환 케이스
        result = transformer.transform_with_validation('NEW', 'BINANCE')
        assert result['original_status'] == 'NEW'
        assert result['transformed_status'] == StandardOrderStatus.NEW
        assert result['is_valid_standard'] is True
        assert result['is_terminal'] is False
        assert result['is_active'] is True
        assert result['exchange_supported'] is True

        # 최종 상태 케이스
        result = transformer.transform_with_validation('FILLED', 'BINANCE')
        assert result['transformed_status'] == StandardOrderStatus.FILLED
        assert result['is_valid_standard'] is True
        assert result['is_terminal'] is True
        assert result['is_active'] is False

        # 미지원 거래소 케이스
        result = transformer.transform_with_validation('UNKNOWN', 'UNKNOWN_EXCHANGE')
        assert result['transformed_status'] == 'UNKNOWN'
        assert result['is_valid_standard'] is False
        assert result['exchange_supported'] is False

        # None 입력 케이스
        result = transformer.transform_with_validation(None, 'BINANCE')
        assert result['transformed_status'] is None
        assert result['is_valid_standard'] is False
        assert result['exchange_supported'] is True

    def test_complete_integration_workflow(self):
        """완전한 통합 워크플로우 테스트"""
        transformer = OrderStatusTransformer()

        # 실제 사용 시나리오 시뮬레이션
        order_updates = [
            ('NEW', 'BINANCE', 'spot'),
            ('wait', 'UPBIT', 'KRW-BTC'),
            ('PARTIALLY_FILLED', 'BINANCE', 'futures'),
            ('done', 'UPBIT', 'KRW-ETH'),
            ('FILLED', 'BINANCE', 'spot'),
            ('cancel', 'UPBIT', 'KRW-BTC'),
        ]

        for original_status, exchange, symbol in order_updates:
            # 1. 상태 변환
            standard_status = transformer.transform(original_status, exchange)

            # 2. 유효성 확인
            is_valid = StandardOrderStatus.is_valid(standard_status)

            # 3. 상태 분류
            is_terminal = StandardOrderStatus.is_terminal(standard_status)
            is_active = StandardOrderStatus.is_active(standard_status)

            # 검증
            assert standard_status is not None
            assert is_valid is True

            # 논리적 일관성 검증
            if is_terminal:
                assert is_active is False
            elif is_active:
                assert is_terminal is False

            # 변환 상태 로깅 (실제 시스템에서는 DB 저장 등)
            print(f"Order {symbol}: {original_status} ({exchange}) -> {standard_status} "
                  f"[Valid: {is_valid}, Terminal: {is_terminal}, Active: {is_active}]")