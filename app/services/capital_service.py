"""
자본 할당 서비스 모듈
자본 할당, 배분, 관리 등 자본 관련 로직
"""

import logging
from datetime import datetime

from app import db
from app.models import Account, StrategyAccount, StrategyCapital
from app.services.exchange_service import exchange_service

logger = logging.getLogger(__name__)

class CapitalError(Exception):
    """자본 관련 오류"""
    pass

class CapitalService:
    """자본 서비스 클래스"""
    
    def __init__(self):
        self.session = db.session
    
    def auto_allocate_capital_for_account(self, account_id):
        """계좌에 연결된 모든 전략에 마켓 타입별로 자동 자본 할당"""
        try:
            # 계좌 조회
            account = Account.query.get(account_id)
            if not account:
                logger.error(f'자본 할당 실패: 계좌 ID {account_id}를 찾을 수 없음')
                return False
            
            # 해당 계좌에 연결된 모든 전략 조회
            strategy_accounts = StrategyAccount.query.filter_by(account_id=account_id).all()
            
            if not strategy_accounts:
                logger.info(f'계좌 {account.name}에 연결된 전략이 없음')
                return True
            
            # 마켓 타입별로 전략 분리
            spot_strategies = []
            futures_strategies = []
            
            for sa in strategy_accounts:
                if sa.strategy.market_type == 'futures':
                    futures_strategies.append(sa)
                else:  # 기본값은 spot
                    spot_strategies.append(sa)
            
            logger.info(f'계좌 {account.name}: spot 전략 {len(spot_strategies)}개, futures 전략 {len(futures_strategies)}개')
            
            # 각 마켓 타입별로 자본 할당 처리
            success_count = 0
            
            # 1. Spot 전략들 처리
            if spot_strategies:
                if self._allocate_capital_by_market_type(account, spot_strategies, 'spot'):
                    success_count += 1
            
            # 2. Futures 전략들 처리
            if futures_strategies:
                if self._allocate_capital_by_market_type(account, futures_strategies, 'futures'):
                    success_count += 1
            
            self.session.commit()
            logger.info(f'계좌 {account.name}의 마켓별 자본 할당 완료 ({success_count}개 마켓)')
            return success_count > 0
            
        except Exception as e:
            self.session.rollback()
            logger.error(f'자동 자본 할당 오류: {str(e)}')
            return False

    def _allocate_capital_by_market_type(self, account, strategy_accounts, market_type):
        """특정 마켓 타입의 전략들에 자본 할당"""
        try:
            from flask import current_app
            
            # 개발 환경에서는 기본값 사용
            if current_app.config.get('SKIP_EXCHANGE_TEST', False):
                total_balance = 10000.0  # 개발 환경 기본값
                logger.info(f'개발 환경: 계좌 {account.name} {market_type} 기본 잔고 ${total_balance} 사용')
            else:
                # 실제 환경에서는 거래소에서 마켓별 잔고 조회
                try:
                    total_balance = exchange_service.get_balance_by_market_type(account, market_type, 'USDT')
                    logger.info(f'계좌 {account.name} {market_type} USDT 잔고: ${total_balance}')
                except Exception as e:
                    logger.error(f'{market_type} 잔고 조회 실패 - 계좌 {account.name}: {str(e)}')
                    # 잔고 조회 실패 시 기본값 사용
                    total_balance = 1000.0
            
            # 해당 마켓 타입의 총 weight 계산
            total_weight = sum(sa.weight for sa in strategy_accounts)
            
            if total_weight <= 0:
                logger.warning(f'계좌 {account.name} {market_type}의 총 weight가 0 이하: {total_weight}')
                return False
            
            # 각 전략에 비례적으로 자본 할당
            for strategy_account in strategy_accounts:
                allocated_amount = (total_balance * strategy_account.weight) / total_weight
                
                # 기존 자본 정보가 있는지 확인
                existing_capital = StrategyCapital.query.filter_by(strategy_account_id=strategy_account.id).first()
                
                if existing_capital:
                    # 기존 자본 정보 업데이트
                    existing_capital.allocated_capital = allocated_amount
                    existing_capital.last_updated = datetime.utcnow()
                    logger.info(f'자본 할당 업데이트: 전략 {strategy_account.strategy.name} ({market_type}) - ${allocated_amount:.2f}')
                else:
                    # 새 자본 정보 생성
                    new_capital = StrategyCapital(
                        strategy_account_id=strategy_account.id,
                        allocated_capital=allocated_amount,
                        current_pnl=0.0
                    )
                    self.session.add(new_capital)
                    logger.info(f'자본 할당 생성: 전략 {strategy_account.strategy.name} ({market_type}) - ${allocated_amount:.2f}')
            
            logger.info(f'계좌 {account.name} {market_type} 자본 할당 완료 (총 잔고: ${total_balance:.2f}, 총 weight: {total_weight})')
            return True
            
        except Exception as e:
            logger.error(f'{market_type} 자본 할당 오류: {str(e)}')
            return False

# 전역 인스턴스
capital_service = CapitalService() 