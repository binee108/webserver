# @FEAT:capital-management @COMP:service @TYPE:core
"""
자본 배분 서비스 모듈

계좌의 전략별 자본을 재배분하는 로직을 제공합니다.
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, List

from app import db
from app.models import Account, StrategyAccount, StrategyCapital, DailyAccountSummary, StrategyPosition, TradeExecution
from app.services.exchange import exchange_service
from app.utils.logging_security import get_secure_logger

logger = get_secure_logger(__name__)


# @FEAT:capital-management @COMP:model @TYPE:core
class CapitalAllocationError(Exception):
    """자본 배분 관련 오류"""
    pass


# @FEAT:capital-management @COMP:service @TYPE:core
class CapitalAllocationService:
    """자본 배분 서비스 클래스"""

    def __init__(self):
        self.session = db.session

    # @FEAT:capital-management @COMP:service @TYPE:core
    def recalculate_strategy_capital(self, account_id: int, use_live_balance: bool = False) -> Dict[str, Any]:
        """
        계좌의 전략별 자본을 재배분합니다.

        재배분 공식:
        1. 계좌 총 자산 = DailyAccountSummary.ending_balance (최신) 또는 실시간 잔고
        2. 전략별 가중치 합 = Σ(StrategyAccount.weight)
        3. 전략별 할당 자본 = (총 자산 × 전략 가중치) / 가중치 합

        Args:
            account_id: 계좌 ID
            use_live_balance: 실시간 거래소 API 호출 여부 (기본값: False)

        Returns:
            Dict[str, Any]: 재배분 결과
                - total_capital: 총 자본
                - allocations: 전략별 할당 내역
                - source: 잔고 출처 (db/live)

        Raises:
            CapitalAllocationError: 계좌를 찾을 수 없거나 전략이 없는 경우
        """
        logger.info(f"🔄 자본 재배분 시작 - 계좌: {account_id}, 실시간 조회: {use_live_balance}")

        # 1. 계좌 조회
        account = Account.query.get(account_id)
        if not account:
            raise CapitalAllocationError(f"계좌를 찾을 수 없습니다: {account_id}")

        # 2. 총 자산 계산
        total_capital, balance_source = self._get_total_capital(account, use_live_balance)

        logger.info(f"💰 총 자산: {total_capital} USDT (출처: {balance_source})")

        # 3. 전략 목록 및 가중치 합 계산
        strategy_accounts = StrategyAccount.query.filter_by(
            account_id=account_id,
            is_active=True
        ).all()

        if not strategy_accounts:
            logger.warning(f"⚠️ 계좌 {account_id}에 연결된 활성 전략이 없습니다")
            return {
                'account_id': account_id,
                'total_capital': float(total_capital),
                'allocations': [],
                'source': balance_source,
                'message': '연결된 활성 전략이 없습니다'
            }

        total_weight = sum(sa.weight for sa in strategy_accounts)

        if total_weight == 0:
            raise CapitalAllocationError(f"전략 가중치 합이 0입니다 (계좌: {account_id})")

        logger.info(f"📊 전략 수: {len(strategy_accounts)}, 총 가중치: {total_weight}")

        # 4. 전략별 자본 재배분
        results = []
        for sa in strategy_accounts:
            allocated = (total_capital * Decimal(sa.weight)) / Decimal(total_weight)

            # StrategyCapital 업데이트 또는 생성
            capital = StrategyCapital.query.filter_by(
                strategy_account_id=sa.id
            ).first()

            old_capital = capital.allocated_capital if capital else 0

            rebalance_time = datetime.utcnow()

            if capital:
                capital.allocated_capital = float(allocated)
                capital.last_updated = rebalance_time
                capital.last_rebalance_at = rebalance_time  # 리밸런싱 시각 기록
            else:
                capital = StrategyCapital(
                    strategy_account_id=sa.id,
                    allocated_capital=float(allocated),
                    last_rebalance_at=rebalance_time  # 최초 배분 시각 기록
                )
                self.session.add(capital)

            results.append({
                'strategy_account_id': sa.id,
                'strategy_name': sa.strategy.name if sa.strategy else 'Unknown',
                'weight': sa.weight,
                'old_capital': float(old_capital),
                'allocated_capital': float(allocated),
                'change': float(allocated - Decimal(str(old_capital)))
            })

            logger.info(
                f"  ✅ {sa.strategy.name if sa.strategy else 'Unknown'}: "
                f"{old_capital:.2f} → {allocated:.2f} USDT (가중치: {sa.weight})"
            )

        self.session.commit()

        logger.info(f"✅ 자본 재배분 완료 - 계좌: {account_id}, 처리된 전략: {len(results)}개")

        return {
            'account_id': account_id,
            'account_name': account.name,
            'total_capital': float(total_capital),
            'allocations': results,
            'source': balance_source,
            'total_weight': total_weight,
            'timestamp': datetime.utcnow().isoformat()
        }

    # @FEAT:capital-management @COMP:service @TYPE:helper @DEPS:exchange-integration
    def _get_total_capital(self, account: Account, use_live_balance: bool) -> tuple[Decimal, str]:
        """
        계좌의 총 자산을 조회합니다.

        Args:
            account: 계좌 객체
            use_live_balance: 실시간 조회 여부

        Returns:
            tuple: (총 자산, 출처)
        """
        if use_live_balance:
            # 실시간 거래소 API 호출
            try:
                balance = exchange_service.get_balance(
                    account=account,
                    asset='USDT',
                    market_type='futures'
                )
                total = Decimal(str(balance.get('total', 0)))
                logger.info(f"📡 실시간 잔고 조회: {total} USDT")
                return total, 'live'
            except Exception as e:
                logger.warning(f"⚠️ 실시간 잔고 조회 실패: {e}, DB 폴백")

        # DB에서 최신 잔고 조회
        latest_summary = DailyAccountSummary.query.filter_by(
            account_id=account.id
        ).order_by(DailyAccountSummary.date.desc()).first()

        if latest_summary:
            total = Decimal(str(latest_summary.ending_balance))
            logger.info(f"💾 DB 잔고 조회: {total} USDT (날짜: {latest_summary.date})")
            return total, 'db'

        # DB에도 없으면 실시간 조회 시도
        logger.warning(f"⚠️ DB에 잔고 기록이 없습니다, 실시간 조회 시도")
        try:
            balance = exchange_service.get_balance(
                account=account,
                asset='USDT',
                market_type='futures'
            )
            total = Decimal(str(balance.get('total', 0)))
            logger.info(f"📡 실시간 잔고 조회 (폴백): {total} USDT")
            return total, 'live_fallback'
        except Exception as e:
            logger.error(f"❌ 잔고 조회 실패: {e}")
            raise CapitalAllocationError(f"잔고를 조회할 수 없습니다: {e}")

    # @FEAT:capital-management @COMP:service @TYPE:helper @DEPS:position-tracking
    def has_open_positions(self, account_id: int) -> bool:
        """
        계좌의 모든 전략에 대해 열린 포지션이 있는지 확인합니다.

        Args:
            account_id: 계좌 ID

        Returns:
            bool: True = 포지션 존재, False = 모든 포지션 청산됨
        """
        try:
            # 해당 계좌와 연결된 모든 StrategyAccount 조회
            strategy_account_ids = [
                sa.id for sa in StrategyAccount.query.filter_by(
                    account_id=account_id,
                    is_active=True
                ).all()
            ]

            if not strategy_account_ids:
                logger.debug(f"계좌 {account_id}에 활성 전략이 없습니다")
                return False

            # 해당 전략들에 대해 포지션 수량이 0이 아닌 레코드 조회
            open_position_count = StrategyPosition.query.filter(
                StrategyPosition.strategy_account_id.in_(strategy_account_ids),
                StrategyPosition.quantity != 0
            ).count()

            has_positions = open_position_count > 0

            logger.debug(
                f"📊 계좌 {account_id} 포지션 상태: "
                f"{'열린 포지션 존재' if has_positions else '모든 포지션 청산됨'} "
                f"(포지션 수: {open_position_count})"
            )

            return has_positions

        except Exception as e:
            logger.error(f"포지션 상태 조회 실패 - 계좌 {account_id}: {e}")
            # 예외 발생 시 안전하게 True 반환 (리밸런싱 방지)
            return True

    # @FEAT:capital-management @COMP:service @TYPE:validation
    def should_rebalance(self, account_id: int, min_interval_hours: int = 1) -> Dict[str, Any]:
        """
        자동 리밸런싱 실행 여부를 판단합니다.

        조건:
        1. 모든 포지션이 청산된 상태여야 함 (has_open_positions == False)
        2. 마지막 리밸런싱 이후 최소 시간이 경과했어야 함 (기본 1시간)

        Args:
            account_id: 계좌 ID
            min_interval_hours: 최소 리밸런싱 간격 (시간 단위, 기본값: 1)

        Returns:
            Dict[str, Any]:
                - should_rebalance: bool (리밸런싱 실행 여부)
                - reason: str (판단 근거)
                - has_positions: bool (포지션 존재 여부)
                - last_rebalance_at: datetime or None (마지막 리밸런싱 시각)
                - time_since_last: float or None (마지막 리밸런싱 이후 경과 시간, 시간 단위)
        """
        try:
            # 조건 1: 포지션 존재 여부 확인
            has_positions = self.has_open_positions(account_id)

            if has_positions:
                logger.debug(f"🔒 계좌 {account_id} 리밸런싱 불가: 열린 포지션 존재")
                return {
                    'should_rebalance': False,
                    'reason': '열린 포지션이 존재하여 리밸런싱 불가',
                    'has_positions': True,
                    'last_rebalance_at': None,
                    'time_since_last': None
                }

            # 조건 2: 마지막 리밸런싱 시간 확인
            # 해당 계좌의 전략들에 대한 StrategyCapital 조회
            strategy_capitals = db.session.query(StrategyCapital).join(
                StrategyAccount
            ).filter(
                StrategyAccount.account_id == account_id,
                StrategyAccount.is_active == True
            ).all()

            if not strategy_capitals:
                logger.debug(f"ℹ️  계좌 {account_id} 리밸런싱 가능: 전략 자본 레코드 없음 (최초 배분)")
                return {
                    'should_rebalance': True,
                    'reason': '최초 자본 배분 필요',
                    'has_positions': False,
                    'last_rebalance_at': None,
                    'time_since_last': None
                }

            # 가장 최근 리밸런싱 시각 찾기
            last_rebalance_times = [
                sc.last_rebalance_at for sc in strategy_capitals
                if sc.last_rebalance_at is not None
            ]

            if not last_rebalance_times:
                logger.debug(f"✅ 계좌 {account_id} 리밸런싱 가능: 리밸런싱 기록 없음")
                return {
                    'should_rebalance': True,
                    'reason': '리밸런싱 기록 없음',
                    'has_positions': False,
                    'last_rebalance_at': None,
                    'time_since_last': None
                }

            last_rebalance_at = max(last_rebalance_times)
            time_since_last = (datetime.utcnow() - last_rebalance_at).total_seconds() / 3600  # 시간 단위

            if time_since_last < min_interval_hours:
                logger.debug(
                    f"🔒 계좌 {account_id} 리밸런싱 불가: "
                    f"최소 간격 미달 ({time_since_last:.2f}시간 < {min_interval_hours}시간)"
                )
                return {
                    'should_rebalance': False,
                    'reason': f'최소 리밸런싱 간격 미달 ({time_since_last:.2f}시간 < {min_interval_hours}시간)',
                    'has_positions': False,
                    'last_rebalance_at': last_rebalance_at,
                    'time_since_last': time_since_last
                }

            logger.info(
                f"✅ 계좌 {account_id} 리밸런싱 가능: "
                f"포지션 청산 완료, 마지막 리밸런싱 이후 {time_since_last:.2f}시간 경과"
            )
            return {
                'should_rebalance': True,
                'reason': f'리밸런싱 조건 충족 (마지막 리밸런싱 이후 {time_since_last:.2f}시간 경과)',
                'has_positions': False,
                'last_rebalance_at': last_rebalance_at,
                'time_since_last': time_since_last
            }

        except Exception as e:
            logger.error(f"리밸런싱 조건 검증 실패 - 계좌 {account_id}: {e}")
            # 예외 발생 시 안전하게 False 반환 (리밸런싱 방지)
            return {
                'should_rebalance': False,
                'reason': f'검증 중 오류 발생: {str(e)}',
                'has_positions': None,
                'last_rebalance_at': None,
                'time_since_last': None
            }

    # @FEAT:capital-management @COMP:service @TYPE:helper @DEPS:order-tracking
    def calculate_unreflected_pnl(self, strategy_account_id: int, since: datetime = None) -> Decimal:
        """
        특정 전략 계좌의 미반영 실현 손익을 계산합니다.

        Args:
            strategy_account_id: 전략 계좌 ID
            since: 집계 시작 시각 (None이면 전체 기간)

        Returns:
            Decimal: 미반영 실현 손익 합계
        """
        try:
            query = self.session.query(
                db.func.sum(TradeExecution.realized_pnl)
            ).filter(
                TradeExecution.strategy_account_id == strategy_account_id,
                TradeExecution.realized_pnl.isnot(None)
            )

            if since:
                query = query.filter(TradeExecution.execution_time >= since)

            result = query.scalar()
            total_pnl = Decimal(str(result)) if result else Decimal('0')

            logger.debug(f"전략 계좌 {strategy_account_id} 미반영 실현 손익: {total_pnl} USDT")
            return total_pnl

        except Exception as e:
            logger.error(f"실현 손익 계산 실패 - 전략 계좌 {strategy_account_id}: {e}")
            return Decimal('0')

    # @FEAT:capital-management @COMP:service @TYPE:core
    def apply_realized_pnl_to_capital(self, strategy_account_id: int, update_timestamp: bool = True) -> Dict[str, Any]:
        """
        전략의 실현 손익을 할당 자본에 반영합니다 (복리 효과).

        Args:
            strategy_account_id: 전략 계좌 ID
            update_timestamp: last_rebalance_at 업데이트 여부 (기본값: True)

        Returns:
            Dict[str, Any]: 반영 결과
                - applied: 반영 여부
                - pnl_amount: 반영된 손익 금액
                - old_capital: 이전 자본
                - new_capital: 새 자본
        """
        try:
            # 전략 자본 레코드 조회
            strategy_capital = StrategyCapital.query.filter_by(
                strategy_account_id=strategy_account_id
            ).first()

            if not strategy_capital:
                logger.warning(f"전략 계좌 {strategy_account_id}의 StrategyCapital 레코드가 없습니다")
                return {
                    'applied': False,
                    'error': 'StrategyCapital 레코드 없음'
                }

            # 마지막 반영 시각 이후의 실현 손익 계산
            since = strategy_capital.last_rebalance_at if strategy_capital.last_rebalance_at else None
            unreflected_pnl = self.calculate_unreflected_pnl(strategy_account_id, since)

            if unreflected_pnl == Decimal('0'):
                logger.debug(f"전략 계좌 {strategy_account_id}: 반영할 실현 손익 없음")
                return {
                    'applied': False,
                    'pnl_amount': 0.0,
                    'old_capital': float(strategy_capital.allocated_capital),
                    'new_capital': float(strategy_capital.allocated_capital),
                    'reason': '반영할 손익 없음'
                }

            # 자본에 손익 반영
            old_capital = Decimal(str(strategy_capital.allocated_capital))
            new_capital = old_capital + unreflected_pnl

            strategy_capital.allocated_capital = float(new_capital)
            if update_timestamp:
                strategy_capital.last_rebalance_at = datetime.utcnow()
            strategy_capital.last_updated = datetime.utcnow()

            self.session.commit()

            logger.info(
                f"💰 전략 계좌 {strategy_account_id} 실현 손익 반영: "
                f"{float(unreflected_pnl):+.2f} USDT "
                f"({float(old_capital):.2f} → {float(new_capital):.2f})"
            )

            return {
                'applied': True,
                'pnl_amount': float(unreflected_pnl),
                'old_capital': float(old_capital),
                'new_capital': float(new_capital)
            }

        except Exception as e:
            self.session.rollback()
            logger.error(f"실현 손익 자본 반영 실패 - 전략 계좌 {strategy_account_id}: {e}")
            return {
                'applied': False,
                'error': str(e)
            }


# 싱글톤 인스턴스
capital_allocation_service = CapitalAllocationService()
