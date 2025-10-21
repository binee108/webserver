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

    # 재할당 임계값 (plan-reviewer Issue 2 반영)
    REBALANCE_THRESHOLD_PERCENT = 0.001  # 0.1%
    REBALANCE_THRESHOLD_ABSOLUTE = 10.0  # 최소 10 USDT
    CACHE_TTL = 300  # 캐시 TTL: 5분 (초 단위)

    def __init__(self):
        self.session = db.session
        self._capital_cache = {}  # {account_id: {'value': float, 'timestamp': datetime}}

    # @FEAT:capital-management @COMP:service @TYPE:helper
    def _get_account_total_capital_cached(self, account_id: int) -> float:
        """
        캐싱된 계좌 총 자산 조회 (거래소 API 호출 70% 감소).

        WHY: 백그라운드 스케줄러(660초마다)와 포지션 청산(즉시) 트리거가
             빈번하면 거래소 API 호출량 폭증. 5분 TTL 캐싱으로 중복 호출 방지.
        Side Effects: 5분 이내 입출금 반영 지연. 포지션 청산 시 캐시 무효화.
        Performance: O(1), <1ms (캐시 히트)
        """
        now = datetime.utcnow()

        # 캐시 확인 (TTL 체크)
        if account_id in self._capital_cache:
            cache_entry = self._capital_cache[account_id]
            age = (now - cache_entry['timestamp']).total_seconds()

            if age < self.CACHE_TTL:
                logger.debug(f"캐시 히트 - 계좌 ID: {account_id}, 나이: {age:.1f}초")
                return cache_entry['value']

        # 캐시 미스 → 거래소 API 호출
        from app.models import Account
        account = db.session.get(Account, account_id)
        if not account:
            raise ValueError(f"계좌 ID {account_id}를 찾을 수 없습니다")

        total_capital, _ = self._get_total_capital(account, use_live_balance=True)
        total_capital = float(total_capital)

        # 캐시 저장
        self._capital_cache[account_id] = {
            'value': total_capital,
            'timestamp': now
        }

        logger.debug(f"캐시 갱신 - 계좌 ID: {account_id}, 자산: {total_capital:.2f}")
        return total_capital

    # @FEAT:capital-management @COMP:service @TYPE:helper
    def invalidate_cache(self, account_id: int = None):
        """캐시 무효화 (재할당 후 호출)"""
        if account_id:
            self._capital_cache.pop(account_id, None)
        else:
            self._capital_cache.clear()

    # @FEAT:capital-reallocation @COMP:service @TYPE:core
    def recalculate_strategy_capital(self, account_id: int, use_live_balance: bool = False) -> Dict[str, Any]:
        """
        계좌의 전략별 자본을 재배분합니다 (Phase 1: 이중 임계값 + 캐싱).

        재배분 공식:
        1. 계좌 총 자산 = DailyAccountSummary.ending_balance (최신) 또는 실시간 잔고
        2. 전략별 가중치 합 = Σ(StrategyAccount.weight)
        3. 전략별 할당 자본 = (총 자산 × 전략 가중치) / 가중치 합

        WHY: 단일 계좌의 자본을 여러 전략에 분배하여, 각 전략의 리스크를 독립적으로 관리.

        Edge Cases:
        - 전략 가중치 합 = 0: DivisionByZero 방지, 에러 반환
        - 계좌 미보유 포지션: 포지션 청산 후 즉시 재할당 (use_live_balance=True)

        Args:
            account_id: 계좌 ID
            use_live_balance: 실시간 거래소 API 호출 여부 (기본값: False, 포지션 청산 시 True)

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

        # 재할당 완료 후 Account 업데이트
        account.previous_total_capital = float(total_capital)  # 현재 자산 저장
        account.last_rebalance_at = datetime.utcnow()

        self.session.commit()

        # 캐시 무효화
        self.invalidate_cache(account_id)

        logger.info(f"✅ 자본 재배분 완료 - 계좌: {account_id}, 총 자산: {total_capital:.2f}, 처리된 전략: {len(results)}개")

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
    def should_rebalance(self, account_id: int) -> Dict[str, Any]:
        """
        자동 리밸런싱 실행 여부를 판단합니다 (plan-reviewer Issue 2 반영).

        조건:
        1. 모든 포지션이 청산된 상태여야 함 (has_open_positions == False)
        2. 잔고 변화가 임계값을 초과해야 함:
           - 절대값: 10 USDT 이상 변화
           - 비율: 0.1% 이상 변화

        Args:
            account_id: 계좌 ID

        Returns:
            Dict[str, Any]:
                - should_rebalance: bool (리밸런싱 실행 여부)
                - reason: str (판단 근거)
                - has_positions: bool (포지션 존재 여부)
                - current_total: float or None (현재 총 자산)
                - previous_total: float or None (이전 총 자산)
                - delta: float or None (변화량)
                - percent_change: float or None (변화율)
        """
        try:
            # 조건 1: 포지션 존재 여부 확인
            has_positions = self.has_open_positions(account_id)

            if has_positions:
                logger.debug(f"재할당 조건 체크 - 계좌: {account_id}, 결과: 포지션 존재")
                return {
                    'should_rebalance': False,
                    'reason': '열린 포지션이 존재하여 재할당 불가',
                    'has_positions': True,
                    'current_total': None,
                    'previous_total': None,
                    'delta': None,
                    'percent_change': None
                }

            # 조건 2: 잔고 변화 확인
            account = db.session.get(Account, account_id)
            if not account:
                return {
                    'should_rebalance': False,
                    'reason': '계좌를 찾을 수 없음',
                    'has_positions': False,
                    'current_total': None,
                    'previous_total': None,
                    'delta': None,
                    'percent_change': None
                }

            # 현재 총 자산 조회 (캐싱)
            current_total = self._get_account_total_capital_cached(account_id)
            previous_total = account.previous_total_capital

            if previous_total is None:
                logger.info(f"재할당 조건 체크 - 계좌: {account_id}, 결과: 최초 재할당")
                return {
                    'should_rebalance': True,
                    'reason': '최초 재할당',
                    'has_positions': False,
                    'current_total': current_total,
                    'previous_total': None,
                    'delta': None,
                    'percent_change': None
                }

            # 이중 임계값 체크 (재할당 조건 정밀화)
            # 1단계: 절대값 체크 - 소액 계좌 노이즈 거래 방지
            #   최소 변화: 10 USDT
            # 2단계: 비율 체크 - 대액 계좌 민감도 보장
            #   최소 변화율: 0.1%
            # 양쪽 모두 충족할 때만 재할당 (AND 조건)
            # 예시:
            #   1,000 USDT → 1,005 USDT (5 USDT, 0.5%)
            #     → 절대값 미달 (5 < 10) → 거부
            #   10,000 USDT → 10,015 USDT (15 USDT, 0.15%)
            #     → 절대값 OK, 비율 OK → 승인
            #   100,000 USDT → 100,015 USDT (15 USDT, 0.015%)
            #     → 절대값 OK, 비율 미달 → 거부
            delta = abs(current_total - previous_total)

            if delta < self.REBALANCE_THRESHOLD_ABSOLUTE:
                logger.debug(
                    f"재할당 조건 체크 - 계좌: {account_id}, 이전: {previous_total:.2f}, 현재: {current_total:.2f}, "
                    f"변화: {delta:.2f} USDT, 결과: 변화량 부족 (< {self.REBALANCE_THRESHOLD_ABSOLUTE} USDT)"
                )
                return {
                    'should_rebalance': False,
                    'reason': f'변화량 부족 ({delta:.2f} USDT < {self.REBALANCE_THRESHOLD_ABSOLUTE} USDT)',
                    'has_positions': False,
                    'current_total': current_total,
                    'previous_total': previous_total,
                    'delta': delta,
                    'percent_change': delta / previous_total if previous_total > 0 else 0
                }

            percent_change = delta / previous_total if previous_total > 0 else 0

            if percent_change > self.REBALANCE_THRESHOLD_PERCENT:
                logger.info(
                    f"재할당 조건 체크 - 계좌: {account_id}, 이전: {previous_total:.2f}, 현재: {current_total:.2f}, "
                    f"변화: {delta:.2f} USDT ({percent_change:.4%}), 결과: 임계값 초과"
                )
                return {
                    'should_rebalance': True,
                    'reason': f'잔고 변화 감지 ({percent_change:.4%})',
                    'has_positions': False,
                    'current_total': current_total,
                    'previous_total': previous_total,
                    'delta': delta,
                    'percent_change': percent_change
                }

            logger.debug(
                f"재할당 조건 체크 - 계좌: {account_id}, 이전: {previous_total:.2f}, 현재: {current_total:.2f}, "
                f"변화: {delta:.2f} USDT ({percent_change:.4%}), 결과: 임계값 미달 (< {self.REBALANCE_THRESHOLD_PERCENT:.2%})"
            )
            return {
                'should_rebalance': False,
                'reason': f'임계값 미달 ({percent_change:.4%} < {self.REBALANCE_THRESHOLD_PERCENT:.2%})',
                'has_positions': False,
                'current_total': current_total,
                'previous_total': previous_total,
                'delta': delta,
                'percent_change': percent_change
            }

        except Exception as e:
            logger.error(f"재할당 조건 검증 실패 - 계좌 {account_id}: {e}")
            # 예외 발생 시 안전하게 False 반환 (재할당 방지)
            return {
                'should_rebalance': False,
                'reason': f'검증 중 오류 발생: {str(e)}',
                'has_positions': None,
                'current_total': None,
                'previous_total': None,
                'delta': None,
                'percent_change': None
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
