"""
거래소별 열린 주문 제한 추적 서비스

주요 기능:
1. DB에서 OpenOrder 조회하여 활성 주문 카운트
2. ExchangeLimits 기반 제한 초과 여부 확인
3. 주문 가능 슬롯 수 반환

DB 조회 기반:
- REST API 호출 없음 (성능 최적화)
- OpenOrder 테이블을 single source of truth로 사용
"""

import logging
from typing import Dict, Optional
from app.models import OpenOrder, StrategyAccount, Account
from app.constants import ExchangeLimits, MarketType, OrderType
from app import db

logger = logging.getLogger(__name__)


class ExchangeLimitTracker:
    """거래소별 열린 주문 제한 추적

    계정+심볼별로 열린 주문 수를 카운트하고,
    ExchangeLimits에서 계산된 제한과 비교하여 주문 가능 여부를 판단합니다.
    """

    @classmethod
    def count_active_orders(cls, account_id: int, symbol: str) -> Dict[str, int]:
        """특정 계정+심볼의 활성 주문 수 카운트

        DB의 OpenOrder 테이블을 조회하여 카운트합니다.
        REST API 호출 없이 DB만 사용하여 성능을 최적화합니다.

        Args:
            account_id: 계정 ID
            symbol: 거래 심볼 (예: BTC/USDT)

        Returns:
            dict: {
                'total': int,           # 전체 주문 수
                'stop_orders': int,     # STOP 주문 수
                'limit_orders': int,    # LIMIT 주문 수 (STOP 제외)
                'market_orders': int    # MARKET 주문 수 (거의 0)
            }

        Examples:
            >>> ExchangeLimitTracker.count_active_orders(1, 'BTC/USDT')
            {'total': 15, 'stop_orders': 3, 'limit_orders': 12, 'market_orders': 0}
        """
        try:
            # DB에서 OpenOrder 조회 (StrategyAccount를 통해 account_id 필터링)
            orders = OpenOrder.query.join(StrategyAccount).filter(
                StrategyAccount.account_id == account_id,
                OpenOrder.symbol == symbol
            ).all()

            # 주문 타입별 카운트
            total = len(orders)
            stop_orders = sum(1 for order in orders if OrderType.requires_stop_price(order.order_type))
            limit_orders = sum(1 for order in orders if order.order_type in ['LIMIT', 'BEST_LIMIT'])
            market_orders = sum(1 for order in orders if order.order_type == 'MARKET')

            return {
                'total': total,
                'stop_orders': stop_orders,
                'limit_orders': limit_orders,
                'market_orders': market_orders
            }

        except Exception as e:
            logger.error(f"활성 주문 카운트 실패 (account_id={account_id}, symbol={symbol}): {e}")
            return {
                'total': 0,
                'stop_orders': 0,
                'limit_orders': 0,
                'market_orders': 0
            }

    @classmethod
    def can_place_order(
        cls,
        account_id: int,
        symbol: str,
        order_type: str,
        market_type: str = None
    ) -> Dict[str, any]:
        """주문 가능 여부 확인

        현재 활성 주문 수와 거래소 제한을 비교하여
        새로운 주문을 배치할 수 있는지 판단합니다.

        Args:
            account_id: 계정 ID
            symbol: 거래 심볼
            order_type: 주문 타입 (LIMIT, STOP_LIMIT, STOP_MARKET 등)
            market_type: 마켓 타입 (SPOT, FUTURES) - None이면 Account에서 조회

        Returns:
            dict: {
                'can_place': bool,          # 주문 가능 여부
                'reason': str or None,      # 불가능한 경우 사유
                'current_total': int,       # 현재 총 주문 수
                'current_stop': int,        # 현재 STOP 주문 수
                'max_orders': int,          # 최대 주문 제한
                'max_stop_orders': int,     # 최대 STOP 주문 제한
                'available_slots': int      # 남은 슬롯 수
            }

        Examples:
            >>> ExchangeLimitTracker.can_place_order(1, 'BTC/USDT', 'LIMIT')
            {'can_place': True, 'reason': None, ...}

            >>> ExchangeLimitTracker.can_place_order(1, 'BTC/USDT', 'STOP_LIMIT')
            {'can_place': False, 'reason': 'STOP 주문 제한 초과 (5/5)', ...}
        """
        try:
            # 계정 정보 조회
            account = Account.query.get(account_id)
            if not account:
                return {
                    'can_place': False,
                    'reason': f'계정을 찾을 수 없습니다 (ID: {account_id})',
                    'current_total': 0,
                    'current_stop': 0,
                    'max_orders': 0,
                    'max_stop_orders': 0,
                    'available_slots': 0
                }

            # market_type 결정
            if market_type is None:
                # Account에서 전략을 통해 market_type 추론
                # 첫 번째 strategy_account의 strategy.market_type 사용
                strategy_account = StrategyAccount.query.filter_by(account_id=account_id).first()
                if strategy_account and strategy_account.strategy:
                    market_type = strategy_account.strategy.market_type
                else:
                    market_type = MarketType.SPOT  # 기본값

            # 거래소별 제한 계산
            limits = ExchangeLimits.calculate_symbol_limit(
                exchange=account.exchange,
                market_type=market_type,
                symbol=symbol
            )

            max_orders = limits['max_orders']
            max_stop_orders = limits['max_stop_orders']

            # 현재 활성 주문 카운트
            current = cls.count_active_orders(account_id, symbol)
            current_total = current['total']
            current_stop = current['stop_orders']

            # 주문 타입 확인
            is_stop = OrderType.requires_stop_price(order_type)

            # 제한 체크
            can_place = True
            reason = None

            if current_total >= max_orders:
                can_place = False
                reason = f'전체 주문 제한 초과 ({current_total}/{max_orders})'
            elif is_stop and current_stop >= max_stop_orders:
                can_place = False
                reason = f'STOP 주문 제한 초과 ({current_stop}/{max_stop_orders})'

            # 남은 슬롯 계산
            if is_stop:
                available_slots = min(
                    max_orders - current_total,
                    max_stop_orders - current_stop
                )
            else:
                available_slots = max_orders - current_total

            available_slots = max(0, available_slots)

            return {
                'can_place': can_place,
                'reason': reason,
                'current_total': current_total,
                'current_stop': current_stop,
                'max_orders': max_orders,
                'max_stop_orders': max_stop_orders,
                'available_slots': available_slots,
                'exchange': account.exchange,
                'market_type': market_type
            }

        except Exception as e:
            logger.error(f"주문 가능 여부 확인 실패 (account_id={account_id}, symbol={symbol}): {e}")
            return {
                'can_place': False,
                'reason': f'오류 발생: {str(e)}',
                'current_total': 0,
                'current_stop': 0,
                'max_orders': 0,
                'max_stop_orders': 0,
                'available_slots': 0
            }

    @classmethod
    def get_available_slots(
        cls,
        account_id: int,
        symbol: str,
        market_type: str = None
    ) -> int:
        """남은 주문 슬롯 수 반환

        간편한 슬롯 확인 메서드입니다.

        Args:
            account_id: 계정 ID
            symbol: 거래 심볼
            market_type: 마켓 타입 (선택적)

        Returns:
            int: 남은 슬롯 수 (0 이상)

        Examples:
            >>> ExchangeLimitTracker.get_available_slots(1, 'BTC/USDT')
            5
        """
        result = cls.can_place_order(account_id, symbol, 'LIMIT', market_type)
        return result.get('available_slots', 0)

    @classmethod
    def get_limit_info(
        cls,
        account_id: int,
        symbol: str,
        market_type: str = None
    ) -> Dict[str, any]:
        """계정+심볼의 제한 정보 상세 조회

        현재 상태와 제한 정보를 모두 포함한 상세 정보를 반환합니다.

        Args:
            account_id: 계정 ID
            symbol: 거래 심볼
            market_type: 마켓 타입 (선택적)

        Returns:
            dict: {
                'account_id': int,
                'symbol': str,
                'exchange': str,
                'market_type': str,
                'current': {
                    'total': int,
                    'stop_orders': int,
                    'limit_orders': int,
                    'market_orders': int
                },
                'limits': {
                    'max_orders': int,
                    'max_stop_orders': int,
                    'per_symbol_limit': int,
                    'per_account_limit': int,
                    'calculation_method': str
                },
                'available': {
                    'total_slots': int,
                    'stop_slots': int,
                    'usage_percent': float
                }
            }
        """
        try:
            # 계정 정보
            account = Account.query.get(account_id)
            if not account:
                return {}

            # market_type 결정
            if market_type is None:
                strategy_account = StrategyAccount.query.filter_by(account_id=account_id).first()
                if strategy_account and strategy_account.strategy:
                    market_type = strategy_account.strategy.market_type
                else:
                    market_type = MarketType.SPOT

            # 제한 계산
            limits = ExchangeLimits.calculate_symbol_limit(
                exchange=account.exchange,
                market_type=market_type,
                symbol=symbol
            )

            # 현재 상태
            current = cls.count_active_orders(account_id, symbol)

            # 가용 슬롯 계산
            total_slots = max(0, limits['max_orders'] - current['total'])
            stop_slots = max(0, limits['max_stop_orders'] - current['stop_orders'])
            usage_percent = (current['total'] / limits['max_orders'] * 100) if limits['max_orders'] > 0 else 0

            return {
                'account_id': account_id,
                'symbol': symbol,
                'exchange': account.exchange,
                'market_type': market_type,
                'current': current,
                'limits': limits,
                'available': {
                    'total_slots': total_slots,
                    'stop_slots': stop_slots,
                    'usage_percent': round(usage_percent, 2)
                }
            }

        except Exception as e:
            logger.error(f"제한 정보 조회 실패 (account_id={account_id}, symbol={symbol}): {e}")
            return {}
