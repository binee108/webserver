"""
전략 관리 서비스 모듈
전략 생성, 조회, 수정, 삭제 등 전략 관련 비즈니스 로직
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import selectinload  # 🆕 eager loading을 위한 import 추가

from app import db
from app.models import Strategy, Account, StrategyAccount, StrategyCapital
from app.services.capital_service import capital_service
from app.constants import MarketType

logger = logging.getLogger(__name__)

class StrategyError(Exception):
    """전략 관련 오류"""
    pass

class StrategyService:
    """전략 서비스 클래스"""
    
    def __init__(self):
        self.session = db.session
    
    def get_strategies_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """사용자의 전략 목록 조회 (N+1 쿼리 문제 해결)"""
        try:
            # 🆕 selectinload를 사용하여 관련 데이터를 한 번에 로드 (N+1 쿼리 문제 해결)
            strategies = (
                Strategy.query
                .options(
                    selectinload(Strategy.strategy_accounts)
                    .selectinload(StrategyAccount.account),  # StrategyAccount -> Account eager loading
                    selectinload(Strategy.strategy_accounts)
                    .selectinload(StrategyAccount.strategy_capital),  # StrategyAccount -> StrategyCapital eager loading
                    selectinload(Strategy.strategy_accounts)
                    .selectinload(StrategyAccount.strategy_positions)  # StrategyAccount -> StrategyPosition eager loading (포지션 수 계산용)
                )
                .filter_by(user_id=user_id)
                .all()
            )
            
            strategies_data = []
            
            for strategy in strategies:
                # 연결된 계좌 정보 (이제 추가 쿼리 없이 접근 가능)
                connected_accounts = []
                total_allocated_capital = 0
                
                for sa in strategy.strategy_accounts:
                    account_info = {
                        'id': sa.account.id,
                        'account_id': sa.account.id,
                        'name': sa.account.name,
                        'exchange': sa.account.exchange,
                        'weight': sa.weight,
                        'leverage': sa.leverage,
                        'max_symbols': sa.max_symbols
                    }
                    
                    # 할당된 자본 정보 (이제 추가 쿼리 없이 접근 가능)
                    if sa.strategy_capital:
                        account_info['allocated_capital'] = sa.strategy_capital.allocated_capital
                        account_info['current_pnl'] = sa.strategy_capital.current_pnl
                        total_allocated_capital += sa.strategy_capital.allocated_capital
                    else:
                        account_info['allocated_capital'] = 0
                        account_info['current_pnl'] = 0
                    
                    connected_accounts.append(account_info)
                
                strategies_data.append({
                    'id': strategy.id,
                    'name': strategy.name,
                    'description': strategy.description,
                    'group_name': strategy.group_name,
                    'market_type': strategy.market_type,
                    'is_active': strategy.is_active,
                    'created_at': strategy.created_at.isoformat(),
                    'connected_accounts': connected_accounts,
                    'total_allocated_capital': total_allocated_capital,
                    'position_count': sum(len([pos for pos in sa.strategy_positions if pos.quantity != 0]) for sa in strategy.strategy_accounts)  # 활성 포지션만 계산
                })
            
            return strategies_data
            
        except Exception as e:
            logger.error(f'전략 목록 조회 오류: {str(e)}')
            raise StrategyError(f'전략 목록 조회 실패: {str(e)}')
    
    def create_strategy(self, user_id: int, strategy_data: Dict[str, Any]) -> Dict[str, Any]:
        """새 전략 생성"""
        try:
            # 입력 데이터 검증
            required_fields = ['name', 'group_name']
            for field in required_fields:
                if not strategy_data.get(field):
                    raise StrategyError(f'{field} 필드가 필요합니다.')
            
            # market_type 검증 및 정규화
            market_type = strategy_data.get('market_type', MarketType.SPOT)
            market_type = MarketType.normalize(market_type)
            if not MarketType.is_valid(market_type):
                raise StrategyError(f'market_type은 {MarketType.VALID_TYPES}만 가능합니다.')
            
            # group_name 중복 확인
            existing_strategy = Strategy.query.filter_by(group_name=strategy_data['group_name']).first()
            if existing_strategy:
                raise StrategyError('이미 존재하는 그룹 이름입니다.')
            
            # 전략 생성
            strategy = Strategy(
                user_id=user_id,
                name=strategy_data['name'],
                description=strategy_data.get('description', ''),
                group_name=strategy_data['group_name'],
                market_type=market_type,
                is_active=strategy_data.get('is_active', True)
            )
            
            self.session.add(strategy)
            self.session.flush()  # ID 생성을 위해 flush
            
            # 계좌 연결 정보가 있는 경우 처리
            connected_accounts = []
            if strategy_data.get('accounts'):
                for account_data in strategy_data['accounts']:
                    account = Account.query.filter_by(
                        id=account_data['account_id'], 
                        user_id=user_id
                    ).first()
                    
                    if not account:
                        self.session.rollback()
                        raise StrategyError(f'계좌 ID {account_data["account_id"]}를 찾을 수 없습니다.')
                    
                    # max_symbols 유효성 검증
                    max_symbols = account_data.get('max_symbols')
                    if max_symbols is not None:
                        if not isinstance(max_symbols, int) or max_symbols <= 0:
                            self.session.rollback()
                            raise StrategyError('최대 보유 심볼 수는 양의 정수여야 합니다.')
                    
                    strategy_account = StrategyAccount(
                        strategy_id=strategy.id,
                        account_id=account.id,
                        weight=account_data.get('weight', 1.0),
                        leverage=account_data.get('leverage', 1.0),
                        max_symbols=max_symbols  # 🆕 최대 보유 심볼 수 설정
                    )
                    
                    self.session.add(strategy_account)
                    connected_accounts.append(account.id)
            
            self.session.commit()
            
            # 연결된 계좌들에 대해 자동 자본 할당 실행
            for account_id in connected_accounts:
                capital_service.auto_allocate_capital_for_account(account_id)
            
            logger.info(f'새 전략 생성: {strategy.name} ({strategy.group_name}) - {strategy.market_type}')
            
            return {
                'strategy_id': strategy.id,
                'name': strategy.name,
                'group_name': strategy.group_name,
                'market_type': strategy.market_type
            }
            
        except StrategyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'전략 생성 오류: {str(e)}')
            raise StrategyError(f'전략 생성 실패: {str(e)}')
    
    def get_strategy_by_id(self, strategy_id: int, user_id: int) -> Optional[Strategy]:
        """ID로 전략 조회 (권한 확인 포함)"""
        return Strategy.query.filter_by(id=strategy_id, user_id=user_id).first()
    
    def update_strategy(self, strategy_id: int, user_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """전략 정보 수정"""
        try:
            strategy = self.get_strategy_by_id(strategy_id, user_id)
            if not strategy:
                raise StrategyError('전략을 찾을 수 없습니다.')
            
            # 수정 가능한 필드들
            updatable_fields = ['name', 'description', 'is_active']
            
            for field in updatable_fields:
                if field in update_data:
                    setattr(strategy, field, update_data[field])
            
            strategy.updated_at = datetime.utcnow()
            self.session.commit()
            
            logger.info(f'전략 수정: {strategy.name} (ID: {strategy.id})')
            
            return {
                'strategy_id': strategy.id,
                'name': strategy.name,
                'description': strategy.description,
                'is_active': strategy.is_active
            }
            
        except StrategyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'전략 수정 오류: {str(e)}')
            raise StrategyError(f'전략 수정 실패: {str(e)}')
    
    def delete_strategy(self, strategy_id: int, user_id: int) -> bool:
        """전략 삭제"""
        try:
            strategy = self.get_strategy_by_id(strategy_id, user_id)
            if not strategy:
                raise StrategyError('전략을 찾을 수 없습니다.')
            
            # 연결된 데이터들 확인
            if strategy.strategy_accounts:
                raise StrategyError('연결된 계좌가 있는 전략은 삭제할 수 없습니다.')
            
            # 포지션 확인 - StrategyAccount를 통해 확인
            has_positions = False
            for strategy_account in strategy.strategy_accounts:
                if strategy_account.strategy_positions:
                    # 활성 포지션이 있는지 확인 (수량이 0이 아닌 포지션)
                    active_positions = [pos for pos in strategy_account.strategy_positions if pos.quantity != 0]
                    if active_positions:
                        has_positions = True
                        break
            
            if has_positions:
                raise StrategyError('활성 포지션이 있는 전략은 삭제할 수 없습니다.')
            
            self.session.delete(strategy)
            self.session.commit()
            
            logger.info(f'전략 삭제: {strategy.name} (ID: {strategy.id})')
            return True
            
        except StrategyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'전략 삭제 오류: {str(e)}')
            raise StrategyError(f'전략 삭제 실패: {str(e)}')
    
    def connect_account_to_strategy(self, strategy_id: int, user_id: int, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """전략에 계좌 연결"""
        try:
            strategy = self.get_strategy_by_id(strategy_id, user_id)
            if not strategy:
                raise StrategyError('전략을 찾을 수 없습니다.')
            
            account = Account.query.filter_by(
                id=account_data['account_id'],
                user_id=user_id
            ).first()
            
            if not account:
                raise StrategyError('계좌를 찾을 수 없습니다.')
            
            # 이미 연결된 계좌인지 확인
            existing_connection = StrategyAccount.query.filter_by(
                strategy_id=strategy_id,
                account_id=account.id
            ).first()
            
            if existing_connection:
                raise StrategyError('이미 연결된 계좌입니다.')
            
            # max_symbols 유효성 검증
            max_symbols = account_data.get('max_symbols')
            if max_symbols is not None:
                if not isinstance(max_symbols, int) or max_symbols <= 0:
                    raise StrategyError('최대 보유 심볼 수는 양의 정수여야 합니다.')
            
            strategy_account = StrategyAccount(
                strategy_id=strategy.id,
                account_id=account.id,
                weight=account_data.get('weight', 1.0),
                leverage=account_data.get('leverage', 1.0),
                max_symbols=max_symbols  # 🆕 최대 보유 심볼 수 설정
            )
            
            self.session.add(strategy_account)
            self.session.commit()
            
            # 자동 자본 할당 실행
            capital_service.auto_allocate_capital_for_account(account.id)
            
            logger.info(f'전략-계좌 연결: 전략 {strategy.name} - 계좌 {account.name}' + 
                       (f' (최대 심볼: {max_symbols})' if max_symbols else ''))
            
            return {
                'strategy_id': strategy.id,
                'account_id': account.id,
                'weight': strategy_account.weight,
                'leverage': strategy_account.leverage,
                'max_symbols': strategy_account.max_symbols  # 🆕 최대 보유 심볼 수 반환
            }
            
        except StrategyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'전략-계좌 연결 오류: {str(e)}')
            raise StrategyError(f'전략-계좌 연결 실패: {str(e)}')
    
    def update_strategy_account(self, strategy_id: int, user_id: int, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """기존 전략-계좌 연결 설정 업데이트"""
        try:
            strategy = self.get_strategy_by_id(strategy_id, user_id)
            if not strategy:
                raise StrategyError('전략을 찾을 수 없습니다.')
            
            account = Account.query.filter_by(
                id=account_data['account_id'],
                user_id=user_id
            ).first()
            
            if not account:
                raise StrategyError('계좌를 찾을 수 없습니다.')
            
            # 기존 연결 찾기
            strategy_account = StrategyAccount.query.filter_by(
                strategy_id=strategy_id,
                account_id=account.id
            ).first()
            
            if not strategy_account:
                raise StrategyError('연결된 계좌를 찾을 수 없습니다.')
            
            # max_symbols 유효성 검증
            max_symbols = account_data.get('max_symbols')
            if max_symbols is not None:
                if not isinstance(max_symbols, int) or max_symbols <= 0:
                    raise StrategyError('최대 보유 심볼 수는 양의 정수여야 합니다.')
            
            # 설정 업데이트
            strategy_account.weight = account_data.get('weight', strategy_account.weight)
            strategy_account.leverage = account_data.get('leverage', strategy_account.leverage)
            strategy_account.max_symbols = max_symbols
            
            self.session.commit()
            
            # 자동 자본 할당 실행 (설정 변경으로 인한 재할당)
            capital_service.auto_allocate_capital_for_account(account.id)
            
            logger.info(f'전략-계좌 설정 업데이트: 전략 {strategy.name} - 계좌 {account.name}' + 
                       (f' (최대 심볼: {max_symbols})' if max_symbols else ''))
            
            return {
                'strategy_id': strategy.id,
                'account_id': account.id,
                'weight': strategy_account.weight,
                'leverage': strategy_account.leverage,
                'max_symbols': strategy_account.max_symbols
            }
            
        except StrategyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'전략-계좌 설정 업데이트 오류: {str(e)}')
            raise StrategyError(f'전략-계좌 설정 업데이트 실패: {str(e)}')

# 전역 인스턴스 생성
strategy_service = StrategyService() 