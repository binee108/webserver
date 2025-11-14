# @FEAT:order-tracking @FEAT:capital-management @COMP:util @TYPE:helper
"""Order quantity calculation utilities extracted from the legacy trading service."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Dict, Optional, Tuple

from app.models import StrategyAccount, StrategyCapital, StrategyPosition
from app.services.price_cache import price_cache
from app.services.symbol_validator import symbol_validator

logger = logging.getLogger(__name__)


# @FEAT:capital-management @FEAT:order-tracking @FEAT:position-tracking @COMP:util @TYPE:helper
class QuantityCalculationError(Exception):
    """Raised when order quantity cannot be determined safely."""


# @FEAT:capital-management @FEAT:order-tracking @FEAT:position-tracking @COMP:service @TYPE:core
class QuantityCalculator:
    """Encapsulates order quantity and price calculations."""

    # @FEAT:capital-management @FEAT:order-tracking @FEAT:position-tracking @COMP:service @TYPE:core
    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service

    # ------------------------------------------------------------------
    # Price helpers
    # ------------------------------------------------------------------
    # @FEAT:capital-management @FEAT:order-tracking @FEAT:position-tracking @COMP:service @TYPE:helper
    def determine_order_price(
        self,
        order_type: str,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        symbol: Optional[str] = None,
        exchange: str = 'BINANCE',
        market_type: str = 'FUTURES',
    ) -> Optional[Decimal]:
        """Resolve an effective price for the supplied order parameters.

        Price Priority (Updated for MARKET ONLY):
        1. MARKET + price provided → Use webhook-provided price
        2. LIMIT orders + price required → Use price parameter
        3. STOP orders + stop_price required → Use stop_price parameter
        4. Fallback → Use local cache price (price_cache or exchange_service)

        @PRINCIPLE: Webhook-provided price takes precedence over cache (accuracy improvement)
        @HISTORICAL: Previously, MARKET orders always used cache price
        @CHANGE: MARKET can now use webhook-provided price (optional)
        @CRITICAL: STOP_MARKET unchanged - always uses stop_price (no price support)
        """
        from app.constants import OrderType  # Local import to avoid circular deps

        # ✅ NEW: MARKET 주문만 웹훅 제공 price 우선 사용
        # @PRINCIPLE: 웹훅 송신자가 더 정확한 가격을 알고 있다고 가정
        # @USE_CASE: TradingView가 최신 시장가를 알고 있어 더 정확한 수량 계산 가능
        # @CRITICAL: STOP_MARKET은 여기서 제외 (기존 동작 유지)
        if order_type == OrderType.MARKET:
            if price is not None:
                logger.info(
                    "💰 MARKET 주문: 웹훅 제공 가격 사용 (수량 계산 정확도 향상) - %s",
                    price
                )
                return Decimal(str(price))

        if OrderType.requires_price(order_type) and price is not None:
            logger.debug("📊 %s 주문: 지정가 %s 사용", order_type, price)
            return Decimal(str(price))

        if OrderType.requires_stop_price(order_type) and stop_price is not None:
            logger.debug("🛑 %s 주문: 스탑가 %s 사용", order_type, stop_price)
            return Decimal(str(stop_price))

        if symbol:
            # ✅ 1차 시도: price_cache (빠른 응답)
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

            # ✅ 2차 시도: exchange_service 직접 호출 (캐시 우회)
            logger.warning(
                "⚠️ price_cache 실패, exchange_service 직접 호출 시도: %s",
                symbol
            )

            try:
                from app.services.exchange import exchange_service

                # exchange_service.get_ticker() 호출 (공개 API)
                ticker = exchange_service.get_ticker(
                    exchange=exchange,
                    symbol=symbol,
                    market_type=market_type.lower()
                )

                if ticker and 'last' in ticker:
                    price_value = Decimal(str(ticker['last']))
                    logger.info(
                        "✅ exchange_service 직접 호출 성공: %s = %s",
                        symbol,
                        price_value
                    )
                    return price_value

            except Exception as e:
                logger.error(
                    "❌ exchange_service 직접 호출 실패: %s - %s",
                    symbol,
                    str(e),
                    exc_info=True
                )

        logger.critical("❌ 가격 결정 실패: %s - 캐시/거래소 가격을 가져올 수 없습니다", symbol)
        return None

    # ------------------------------------------------------------------
    # Quantity helpers
    # ------------------------------------------------------------------
    # @FEAT:order-tracking @FEAT:capital-management @COMP:util @TYPE:core @DEPS:position-tracking
    def calculate_order_quantity(
        self,
        strategy_account: StrategyAccount,
        symbol: str,
        order_type: str,
        qty_per: Optional[Decimal] = None,  # 🆕 None 허용
        qty: Optional[Decimal] = None,      # 🆕 추가
        market_type: str = 'futures',
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        side: Optional[str] = None,
    ) -> Decimal:
        """Return the order quantity derived from allocated capital or absolute value.

        Args:
            strategy_account: StrategyAccount instance for the trading strategy.
            symbol: Trading symbol (e.g., 'BTC/USDT', 'AAPL').
            order_type: Order type (e.g., 'MARKET', 'LIMIT', 'STOP_MARKET').
            qty_per: Allocation percentage. Positive values (>0) for entry orders
                     (no upper limit, supports leverage >100%). Negative values (<0)
                     trigger position liquidation logic.
            qty: Absolute quantity (bypasses percentage calculation). Must be positive.
                 Use qty_per=-100 for liquidation. Overridden by qty_per when both
                 are provided (qty_per priority).
            market_type: Market type ('futures' or 'spot'). Default: 'futures'.
            price: Order price for LIMIT orders.
            stop_price: Stop price for STOP orders.
            side: Trade side ('BUY' or 'SELL') for position liquidation.

        Returns:
            Decimal: Calculated order quantity, or Decimal('0') if validation fails.
        """
        # 🆕 Validation: qty 또는 qty_per 중 하나는 필수
        if qty_per is None and qty is None:
            logger.error("qty 또는 qty_per 중 하나는 필수입니다")
            raise ValueError("qty 또는 qty_per 중 하나는 필수입니다")

        # 🆕 Priority: qty_per > qty
        if qty_per is not None and qty is not None:
            logger.warning(
                "⚠️ qty_per (%s%%)와 qty (%s) 둘 다 제공됨. "
                "qty_per를 우선 사용합니다 (우선순위 정책)",
                qty_per,
                qty
            )
            # qty_per 로직으로 진행 (기존 코드 경로)

        # 🆕 Case 1: qty 제공 (qty_per 없음) → 절대 수량 직접 사용
        if qty_per is None and qty is not None:
            # 🆕 Issue Fix #1: qty 음수 검증 추가 (plan-reviewer 피드백)
            if qty <= 0:
                logger.error("qty는 양수여야 합니다: %s. 청산은 qty_per=-100 사용", qty)
                raise ValueError("qty는 양수여야 합니다. 청산은 qty_per=-100 사용")

            logger.info("🎯 절대 수량 모드: qty=%s (퍼센트 계산 우회)", qty)

            # 검증만 수행 (수량 계산 우회)
            exchange_name = (
                strategy_account.account.exchange if strategy_account.account else 'BINANCE'
            )

            validation = symbol_validator.validate_order_params(
                exchange=exchange_name,
                symbol=symbol,
                market_type=market_type,
                quantity=qty,
                price=price or self.determine_order_price(
                    order_type=order_type,
                    price=price,
                    stop_price=stop_price,
                    symbol=symbol,
                    exchange=exchange_name,
                    market_type=market_type,
                ),
            )

            if not validation.get('success'):
                logger.warning(
                    "❌ 수량 검증 실패 (%s): %s",
                    validation.get('error_type'),
                    validation.get('error')
                )
                return Decimal('0')

            adjusted_quantity = validation.get('adjusted_quantity', qty)
            if adjusted_quantity <= 0:
                logger.warning("❌ 검증된 수량이 0 이하입니다 (symbol=%s qty=%s)", symbol, qty)
                return Decimal('0')

            return adjusted_quantity

        # 🆕 Case 2: qty_per 제공 (기존 로직)
        try:
            qty_per_decimal = Decimal(str(qty_per))

            # 음수 qty_per: 포지션 청산 로직으로 위임
            if qty_per_decimal < 0:
                logger.info("🔄 청산 모드 감지: qty_per=%s%%, calculate_quantity_from_percentage 호출", qty_per_decimal)
                return self.calculate_quantity_from_percentage(
                    strategy_account=strategy_account,
                    qty_per=qty_per_decimal,
                    symbol=symbol,
                    market_type=market_type,
                    price=price,
                    order_type=order_type,
                    stop_price=stop_price,
                    side=side
                )

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

            # @FEAT:capital-management - allocated_capital 조회 및 사용
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

            # @FEAT:capital-management - 핵심 수량 계산 공식
            # quantity = (allocated_capital × qty_per% ÷ price) × leverage
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

        except QuantityCalculationError:
            # 청산 관련 예외는 그대로 전파하여 정확한 에러 메시지 제공
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("수량 계산 실패: %s", exc)
            return Decimal('0')

    # @FEAT:order-tracking @FEAT:position-tracking @COMP:util @TYPE:helper
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
        """Convert qty_per into an absolute quantity for entry or exit.

        Handles both positive qty_per (entry orders, unlimited %) and negative
        qty_per (position liquidation, capped at -100%).
        """
        # NOTE: 청산 로직에서 사용 중 (calculate_order_quantity Line 154-165 참조)
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
            quantity = self.calculate_order_quantity(
                strategy_account=strategy_account,
                symbol=symbol,
                order_type=order_type_normalized,
                qty_per=qty_per_decimal,  # 명시적으로 qty_per 전달
                qty=None,  # qty는 사용하지 않음
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

        # 포지션 수량 확인
        position_qty = Decimal('0')
        if position and position.quantity:
            position_qty = Decimal(str(position.quantity))

        # Side에 따른 청산 가능 여부 검증
        side_normalized = str(side or '').upper()
        if side_normalized == 'BUY':
            # BUY 청산 = 숏 포지션 청산
            if position_qty >= 0:
                raise QuantityCalculationError('보유한 숏 포지션이 없습니다.')
            base_quantity = abs(position_qty)
        elif side_normalized == 'SELL':
            # SELL 청산 = 롱 포지션 청산
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

    # @FEAT:capital-management @FEAT:order-tracking @FEAT:position-tracking @COMP:service @TYPE:helper
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
                quantity=abs(quantity),
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

            adjusted_quantity = validation.get('adjusted_quantity', abs(quantity))
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
