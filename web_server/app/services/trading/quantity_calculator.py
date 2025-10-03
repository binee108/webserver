
"""Order quantity calculation utilities extracted from the legacy trading service."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Dict, Optional, Tuple

from app.models import StrategyAccount, StrategyCapital, StrategyPosition
from app.services.price_cache import price_cache
from app.services.symbol_validator import symbol_validator

logger = logging.getLogger(__name__)


class QuantityCalculationError(Exception):
    """Raised when order quantity cannot be determined safely."""


class QuantityCalculator:
    """Encapsulates order quantity and price calculations."""

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service

    # ------------------------------------------------------------------
    # Price helpers
    # ------------------------------------------------------------------
    def determine_order_price(
        self,
        order_type: str,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        symbol: Optional[str] = None,
        exchange: str = 'BINANCE',
        market_type: str = 'FUTURES',
    ) -> Optional[Decimal]:
        """Resolve an effective price for the supplied order parameters."""
        from app.constants import OrderType  # Local import to avoid circular deps

        if OrderType.requires_price(order_type) and price is not None:
            logger.debug("📊 %s 주문: 지정가 %s 사용", order_type, price)
            return Decimal(str(price))

        if OrderType.requires_stop_price(order_type) and stop_price is not None:
            logger.debug("🛑 %s 주문: 스탑가 %s 사용", order_type, stop_price)
            return Decimal(str(stop_price))

        if symbol:
            price_info = price_cache.get_price(
                symbol=symbol,
                exchange=exchange,
                market_type=market_type,
                fallback_to_api=True,
                return_details=True,
            )

            if isinstance(price_info, dict) and price_info.get('price'):
                logger.info(
                    "💰 %s 현재가: %s (source=%s, age=%.1fs)",
                    symbol,
                    price_info['price'],
                    price_info.get('source'),
                    price_info.get('age_seconds', 0.0),
                )
                return Decimal(price_info['price'])

        logger.critical("❌ 가격 결정 실패: %s - 캐시/거래소 가격을 가져올 수 없습니다", symbol)
        return None

    # ------------------------------------------------------------------
    # Quantity helpers
    # ------------------------------------------------------------------
    def calculate_order_quantity(
        self,
        strategy_account: StrategyAccount,
        qty_per: Decimal,
        symbol: str,
        order_type: str,
        market_type: str = 'futures',
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
    ) -> Decimal:
        """Return the order quantity derived from allocated capital."""
        try:
            qty_per_decimal = Decimal(str(qty_per))
            if qty_per_decimal < 0 or qty_per_decimal > 100:
                logger.error("qty_per 범위 오류: %s%% (0-100 필요)", qty_per_decimal)
                return Decimal('0')

            if qty_per_decimal == 0:
                return Decimal('0')

            exchange_name = (
                strategy_account.account.exchange if strategy_account.account else 'BINANCE'
            )
            effective_price = self.determine_order_price(
                order_type=order_type,
                price=price,
                stop_price=stop_price,
                symbol=symbol,
                exchange=exchange_name,
                market_type=market_type,
            )

            if not effective_price or effective_price <= 0:
                logger.error("유효한 가격을 결정할 수 없음: %s", symbol)
                return Decimal('0')

            logger.info(
                "🎯 수량 계산용 가격: %s (주문타입: %s)",
                effective_price,
                order_type,
            )

            strategy_capital = StrategyCapital.query.filter_by(
                strategy_account_id=strategy_account.id
            ).first()

            if not strategy_capital:
                logger.error("전략 캐피털 정보 없음: strategy_account_id=%s", strategy_account.id)
                return Decimal('0')

            allocated_capital = Decimal(str(strategy_capital.allocated_capital))

            leverage = Decimal('1')
            if market_type.lower() == 'futures':
                leverage = Decimal(str(getattr(strategy_account, 'leverage', 1)))

            quantity = (
                allocated_capital
                * (qty_per_decimal / Decimal('100'))
                / effective_price
                * leverage
            )

            logger.info(
                "📊 수량 계산: %s × %s%% ÷ %s × %s = %s",
                allocated_capital,
                qty_per_decimal,
                effective_price,
                leverage,
                quantity,
            )

            validation = symbol_validator.validate_order_params(
                exchange=exchange_name,
                symbol=symbol,
                market_type=market_type,
                quantity=quantity,
                price=effective_price,
            )

            if not validation.get('success'):
                logger.warning(
                    "❌ 수량 검증 실패 (%s): %s",
                    validation.get('error_type'),
                    validation.get('error'),
                )
                return Decimal('0')

            adjusted_quantity = validation.get('adjusted_quantity', quantity)
            if adjusted_quantity <= 0:
                logger.warning(
                    "❌ 검증된 수량이 0 이하입니다 (symbol=%s qty_per=%s)",
                    symbol,
                    qty_per_decimal,
                )
                return Decimal('0')

            return adjusted_quantity

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("수량 계산 실패: %s", exc)
            return Decimal('0')

    def calculate_quantity_from_percentage(
        self,
        strategy_account: StrategyAccount,
        qty_per: Decimal,
        symbol: str,
        market_type: str = 'futures',
        price: Optional[Decimal] = None,
        order_type: str = 'MARKET',
        stop_price: Optional[Decimal] = None,
        side: Optional[str] = None,
    ) -> Decimal:
        """Convert qty_per into an absolute quantity for entry or exit."""
        try:
            qty_per_decimal = Decimal(str(qty_per))
        except (InvalidOperation, ValueError, TypeError) as exc:
            logger.error(
                "qty_per 타입 검증 실패: %s (타입: %s), 오류: %s",
                qty_per,
                type(qty_per),
                exc,
            )
            raise QuantityCalculationError('수량 비율이 올바르지 않습니다.') from exc

        if qty_per_decimal == 0:
            logger.info('qty_per가 0%: 거래량 0 반환')
            return Decimal('0')

        order_type_normalized = str(order_type or 'MARKET').upper()

        price_decimal = None
        if price is not None:
            try:
                price_decimal = Decimal(str(price))
            except (InvalidOperation, ValueError, TypeError) as exc:
                logger.error("가격 변환 실패: %s", price)
                raise QuantityCalculationError('주문 가격 형식이 올바르지 않습니다.') from exc

        stop_price_decimal = None
        if stop_price is not None:
            try:
                stop_price_decimal = Decimal(str(stop_price))
            except (InvalidOperation, ValueError, TypeError) as exc:
                logger.error("스탑가격 변환 실패: %s", stop_price)
                raise QuantityCalculationError('스탑 가격 형식이 올바르지 않습니다.') from exc

        if qty_per_decimal > 0:
            if qty_per_decimal > Decimal('100'):
                logger.error("qty_per 범위 오류: %s%% (0-100 범위 필요)", qty_per_decimal)
                raise QuantityCalculationError('수량 비율은 0~100% 사이여야 합니다.')

            quantity = self.calculate_order_quantity(
                strategy_account=strategy_account,
                qty_per=qty_per_decimal,
                symbol=symbol,
                order_type=order_type_normalized,
                market_type=market_type,
                price=price_decimal,
                stop_price=stop_price_decimal,
            )

            if quantity <= 0:
                raise QuantityCalculationError(
                    '계좌 잔고 부족 또는 주문 제한으로 수량을 계산할 수 없습니다.'
                )

            logger.info(
                "📊 퍼센테이지 수량 계산 완료: qty_per=%s%% → quantity=%s",
                qty_per_decimal,
                quantity,
            )
            return quantity

        close_percent = abs(qty_per_decimal)
        if close_percent > Decimal('100'):
            logger.warning(
                "청산 비율이 100%% 초과하여 100%%로 조정됩니다: %s%%",
                close_percent,
            )
            close_percent = Decimal('100')

        if not side:
            raise QuantityCalculationError('포지션 청산을 위해 side 값이 필요합니다.')

        position = StrategyPosition.query.filter_by(
            strategy_account_id=strategy_account.id,
            symbol=symbol,
        ).first()

        if not position or not position.quantity:
            raise QuantityCalculationError('보유 포지션이 없습니다.')

        position_qty = Decimal(str(position.quantity))

        side_normalized = str(side or '').upper()
        if side_normalized == 'BUY':
            if position_qty >= 0:
                raise QuantityCalculationError('보유한 숏 포지션이 없습니다.')
            base_quantity = abs(position_qty)
        elif side_normalized == 'SELL':
            if position_qty <= 0:
                raise QuantityCalculationError('보유한 롱 포지션이 없습니다.')
            base_quantity = position_qty
        else:
            raise QuantityCalculationError('지원하지 않는 주문 방향입니다.')

        raw_quantity = base_quantity * (close_percent / Decimal('100'))

        if raw_quantity <= 0:
            raise QuantityCalculationError('계산된 청산 수량이 0입니다.')

        exchange_name = (
            strategy_account.account.exchange if strategy_account.account else 'BINANCE'
        )
        effective_price = self.determine_order_price(
            order_type=order_type_normalized,
            price=price_decimal,
            stop_price=stop_price_decimal,
            symbol=symbol,
            exchange=exchange_name,
            market_type=market_type,
        )

        validation = symbol_validator.validate_order_params(
            exchange=exchange_name,
            symbol=symbol,
            market_type=market_type,
            quantity=raw_quantity,
            price=effective_price,
        )

        if not validation.get('success'):
            error_msg = validation.get('error', '거래소 제한으로 수량을 계산할 수 없습니다.')
            raise QuantityCalculationError(error_msg)

        adjusted_quantity = validation.get('adjusted_quantity', raw_quantity)
        if adjusted_quantity <= 0:
            raise QuantityCalculationError('검증된 청산 수량이 0입니다.')

        logger.info(
            "📊 포지션 청산 수량 계산 완료: base=%s, percent=%s%% → quantity=%s",
            base_quantity,
            close_percent,
            adjusted_quantity,
        )

        return adjusted_quantity

    def quantize_quantity_for_symbol(
        self,
        strategy_account: StrategyAccount,
        symbol: str,
        quantity: Decimal,
        rounding=ROUND_DOWN,
    ) -> Tuple[Decimal, Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Adjust the quantity to satisfy exchange precision rules."""
        try:
            if not strategy_account or not strategy_account.account or not strategy_account.strategy:
                return quantity, None, None, None

            exchange_name = strategy_account.account.exchange
            market_type = (strategy_account.strategy.market_type or 'SPOT').upper()

            validation = symbol_validator.validate_order_params(
                exchange=exchange_name,
                symbol=symbol,
                market_type=market_type,
                quantity=quantity.copy_abs(),
                price=None,
            )

            if not validation.get('success'):
                error_type = validation.get('error_type')
                min_quantity = validation.get('min_quantity')
                step_size = validation.get('step_size')
                min_notional = validation.get('min_notional')

                if error_type == 'min_quantity_error':
                    return Decimal('0'), min_quantity, step_size, min_notional
                if error_type == 'min_notional_error':
                    return Decimal('0'), None, step_size, min_notional
                return quantity, None, None, None

            adjusted_quantity = validation.get('adjusted_quantity', quantity.copy_abs())
            min_quantity = validation.get('min_quantity')
            step_size = validation.get('step_size')
            min_notional = validation.get('min_notional')

            adjusted_quantity = adjusted_quantity if quantity >= 0 else -adjusted_quantity

            return adjusted_quantity, min_quantity, step_size, min_notional

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug(
                "수량 보정에 실패하여 원본 사용 - strategy_account=%s symbol=%s error=%s",
                getattr(strategy_account, 'id', None),
                symbol,
                exc,
            )
            return quantity, None, None, None
