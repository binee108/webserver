# @FEAT:order-status-standardization @COMP:transformer @TYPE:standardization
"""
주문 상태 변환기 (Order Status Transformer)

거래소별 주문 상태를 표준 상태로 변환하는 변환기 클래스입니다.
모든 거래소의 상태를 StandardOrderStatus로 통합합니다.
"""

from web_server.app.constants import StandardOrderStatus


class OrderStatusTransformer:
    """거래소별 주문 상태를 표준 상태로 변환하는 변환기

    모든 거래소의 고유한 주문 상태를 StandardOrderStatus 형식으로 통합합니다.
    새로운 거래소 추가 시 상태 매핑만 추가하면 됩니다.

    지원 거래소:
    - BINANCE: NEW, PARTIALLY_FILLED, FILLED, CANCELED, CANCELLED, REJECTED, EXPIRED
    - UPBIT: wait, watch, done, completed, cancel, cancelled
    - BITHUMB: bid, ask, fill, complete, cancel
    - BYBIT: Created, New, PartiallyFilled, Filled, Cancelled, Canceled, Rejected
    """

    # 거래소별 상태 매핑 테이블
    _STATUS_MAPPINGS = {
        'BINANCE': {
            'NEW': StandardOrderStatus.NEW,
            'PARTIALLY_FILLED': StandardOrderStatus.PARTIALLY_FILLED,
            'FILLED': StandardOrderStatus.FILLED,
            'CANCELED': StandardOrderStatus.CANCELLED,
            'CANCELLED': StandardOrderStatus.CANCELLED,
            'REJECTED': StandardOrderStatus.REJECTED,
            'EXPIRED': StandardOrderStatus.EXPIRED
        },
        'UPBIT': {
            'wait': StandardOrderStatus.OPEN,
            'watch': StandardOrderStatus.OPEN,  # 호환성
            'done': StandardOrderStatus.FILLED,
            'completed': StandardOrderStatus.FILLED,  # 호환성
            'cancel': StandardOrderStatus.CANCELLED,
            'cancelled': StandardOrderStatus.CANCELLED  # 호환성
        },
        'BITHUMB': {
            'bid': StandardOrderStatus.OPEN,
            'ask': StandardOrderStatus.OPEN,
            'fill': StandardOrderStatus.FILLED,
            'complete': StandardOrderStatus.FILLED,
            'cancel': StandardOrderStatus.CANCELLED
        },
        'BYBIT': {
            'Created': StandardOrderStatus.NEW,
            'New': StandardOrderStatus.OPEN,
            'PartiallyFilled': StandardOrderStatus.PARTIALLY_FILLED,
            'Filled': StandardOrderStatus.FILLED,
            'Cancelled': StandardOrderStatus.CANCELLED,
            'Canceled': StandardOrderStatus.CANCELLED,
            'Rejected': StandardOrderStatus.REJECTED
        }
    }

    def transform(self, status, exchange):
        """거래소별 주문 상태를 표준 상태로 변환

        Args:
            status (str): 거래소 원본 주문 상태
            exchange (str): 거래소 이름

        Returns:
            str: 표준 주문 상태 또는 원본 상태 (미지원 시)

        Examples:
            >>> transformer = OrderStatusTransformer()
            >>> transformer.transform('NEW', 'BINANCE')
            'NEW'
            >>> transformer.transform('wait', 'UPBIT')
            'OPEN'
            >>> transformer.transform('UNKNOWN', 'BINANCE')
            'UNKNOWN'
        """
        # 입력값 유효성 검사
        if not status or not exchange:
            return status

        # 거래소 이름 정규화
        exchange_normalized = self._normalize_exchange_name(exchange)

        # 상태 매핑 조회
        return self._lookup_status_mapping(status, exchange_normalized)

    def _normalize_exchange_name(self, exchange):
        """거래소 이름을 정규화 (대소문자 무시)

        Args:
            exchange (str): 거래소 이름

        Returns:
            str: 정규화된 거래소 이름 (대문자)
        """
        return exchange.upper()

    def _lookup_status_mapping(self, status, exchange_normalized):
        """상태 매핑을 조회하여 반환

        Args:
            status (str): 원본 상태
            exchange_normalized (str): 정규화된 거래소 이름

        Returns:
            str: 변환된 상태 또는 원본 상태 (미지원 시)
        """
        # 지원되는 거래소인지 확인
        status_mapping = self._STATUS_MAPPINGS.get(exchange_normalized)
        if not status_mapping:
            return status

        # 상태 매핑 확인
        return status_mapping.get(status, status)

    def get_supported_exchanges(self):
        """지원되는 거래소 목록 반환

        Returns:
            list: 지원되는 거래소 이름 목록
        """
        return list(self._STATUS_MAPPINGS.keys())

    def is_supported_exchange(self, exchange):
        """지원되는 거래소인지 확인

        Args:
            exchange (str): 확인할 거래소 이름

        Returns:
            bool: 지원되는 거래소이면 True

        Examples:
            >>> transformer = OrderStatusTransformer()
            >>> transformer.is_supported_exchange('BINANCE')
            True
            >>> transformer.is_supported_exchange('binance')  # 대소문자 무시
            True
            >>> transformer.is_supported_exchange('UNKNOWN')
            False
        """
        if not exchange:
            return False

        # _normalize_exchange_name 메서드 재사용
        exchange_normalized = self._normalize_exchange_name(exchange)
        return exchange_normalized in self._STATUS_MAPPINGS

    @classmethod
    def create_legacy_adapter(cls):
        """기존 Order.from_exchange 스타일의 어댑터 생성

        Returns:
            function: 기존 from_exchange 인터페이스와 호환되는 함수

        Examples:
            >>> transformer = OrderStatusTransformer()
            >>> legacy_adapter = transformer.create_legacy_adapter()
            >>> legacy_adapter('NEW', 'BINANCE')
            'NEW'
        """
        transformer_instance = cls()

        def legacy_adapter(status, exchange):
            """기존 OrderStatus.from_exchange 호환 어댑터

            Args:
                status (str): 거래소 원본 상태
                exchange (str): 거래소 이름

            Returns:
                str: 변환된 상태
            """
            return transformer_instance.transform(status, exchange)

        return legacy_adapter

    def transform_with_validation(self, status, exchange):
        """상태 변환과 유효성 검증을 함께 수행

        Args:
            status (str): 거래소 원본 상태
            exchange (str): 거래소 이름

        Returns:
            dict: {
                'original_status': str,
                'transformed_status': str,
                'is_valid_standard': bool,
                'is_terminal': bool,
                'is_active': bool
            }

        Examples:
            >>> transformer = OrderStatusTransformer()
            >>> result = transformer.transform_with_validation('NEW', 'BINANCE')
            >>> result['transformed_status']
            'NEW'
            >>> result['is_valid_standard']
            True
        """
        transformed_status = self.transform(status, exchange)

        return {
            'original_status': status,
            'transformed_status': transformed_status,
            'is_valid_standard': StandardOrderStatus.is_valid(transformed_status) if transformed_status else False,
            'is_terminal': StandardOrderStatus.is_terminal(transformed_status) if transformed_status else False,
            'is_active': StandardOrderStatus.is_active(transformed_status) if transformed_status else False,
            'exchange_supported': self.is_supported_exchange(exchange)
        }