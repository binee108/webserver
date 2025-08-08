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
                    # 연결된 계좌가 없거나 소유자가 아니면 제외
                    if not sa.account or sa.account.user_id != user_id:
                        continue
                    account_info = {
                        'id': sa.account.id,
                        'account_id': sa.account.id,
                        'name': sa.account.name,
                        'exchange': sa.account.exchange,
                        'weight': sa.weight,
                        'leverage': sa.leverage,
                        'max_symbols': sa.max_symbols
                    }
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
                    'is_public': getattr(strategy, 'is_public', False),
                    'is_active': strategy.is_active,
                    'created_at': strategy.created_at.isoformat(),
                    'connected_accounts': connected_accounts,
                    'total_allocated_capital': total_allocated_capital,
                    'position_count': sum(
                        len([pos for pos in sa.strategy_positions if pos.quantity != 0])
                        for sa in strategy.strategy_accounts if sa.account and sa.account.user_id == user_id
                    )  # 내 계좌의 활성 포지션만 계산
                })
            
            return strategies_data
            
        except Exception as e:
            logger.error(f'전략 목록 조회 오류: {str(e)}')
            raise StrategyError(f'전략 목록 조회 실패: {str(e)}')

    def get_accessible_strategies(self, user_id: int) -> List[Dict[str, Any]]:
        """사용자가 접근 가능한 전략: 내가 소유하거나, 내가 구독(내 계좌 연결) 중인 public 전략.
        계좌 정보는 현재 사용자 소유 계좌로 한정하여 반환한다.
        """
        try:
            # 내가 소유한 전략
            owned_strategies = (
                Strategy.query
                .options(
                    selectinload(Strategy.strategy_accounts)
                    .selectinload(StrategyAccount.account),
                    selectinload(Strategy.strategy_accounts)
                    .selectinload(StrategyAccount.strategy_capital),
                    selectinload(Strategy.strategy_accounts)
                    .selectinload(StrategyAccount.strategy_positions)
                )
                .filter_by(user_id=user_id)
                .all()
            )

            # 내가 구독한 전략 (내 계좌가 연결된 모든 전략)
            subscribed_strategy_accounts = (
                StrategyAccount.query
                .options(
                    selectinload(StrategyAccount.strategy),
                    selectinload(StrategyAccount.account),
                    selectinload(StrategyAccount.strategy_capital),
                    selectinload(StrategyAccount.strategy_positions)
                )
                .join(StrategyAccount.account)
                .filter(Account.user_id == user_id)
                .all()
            )

            # 전략별로 현재 사용자 계좌만 담아서 구성
            strategy_id_to_data: Dict[int, Dict[str, Any]] = {}

            def ensure_strategy_entry(strategy: Strategy):
                if strategy.id not in strategy_id_to_data:
                    strategy_id_to_data[strategy.id] = {
                        'id': strategy.id,
                        'name': strategy.name,
                        'description': strategy.description,
                        # 소유자가 아닌 경우 group_name 비노출
                        'group_name': strategy.group_name if strategy.user_id == user_id else None,
                        'market_type': strategy.market_type,
                        'is_active': strategy.is_active,
                        'is_public': getattr(strategy, 'is_public', False),
                        'created_at': strategy.created_at.isoformat(),
                        'connected_accounts': [],
                        'position_count': 0,
                        'ownership': 'owner' if strategy.user_id == user_id else 'subscriber'
                    }

            # 소유 전략 처리 (계좌 전체 표시)
            for strategy in owned_strategies:
                ensure_strategy_entry(strategy)
                entry = strategy_id_to_data[strategy.id]
                position_count = 0
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
                    account_info['is_active'] = getattr(sa, 'is_active', True)
                    if sa.strategy_capital:
                        account_info['allocated_capital'] = sa.strategy_capital.allocated_capital
                        account_info['current_pnl'] = sa.strategy_capital.current_pnl
                    else:
                        account_info['allocated_capital'] = 0
                        account_info['current_pnl'] = 0
                    entry['connected_accounts'].append(account_info)
                    position_count += len([pos for pos in sa.strategy_positions if pos.quantity != 0])
                entry['position_count'] = position_count

            # 구독 전략 처리 (내 계좌만 표시)
            for sa in subscribed_strategy_accounts:
                strategy = sa.strategy
                ensure_strategy_entry(strategy)
                entry = strategy_id_to_data[strategy.id]
                # 내 계좌만 추가
                account_info = {
                    'id': sa.account.id,
                    'account_id': sa.account.id,
                    'name': sa.account.name,
                    'exchange': sa.account.exchange,
                    'weight': sa.weight,
                    'leverage': sa.leverage,
                    'max_symbols': sa.max_symbols
                }
                account_info['is_active'] = getattr(sa, 'is_active', True)
                if sa.strategy_capital:
                    account_info['allocated_capital'] = sa.strategy_capital.allocated_capital
                    account_info['current_pnl'] = sa.strategy_capital.current_pnl
                else:
                    account_info['allocated_capital'] = 0
                    account_info['current_pnl'] = 0

                entry['connected_accounts'].append(account_info)
                entry['position_count'] += len([pos for pos in sa.strategy_positions if pos.quantity != 0])

            # 리스트로 반환
            return list(strategy_id_to_data.values())

        except Exception as e:
            logger.error(f'접근 가능한 전략 조회 오류: {str(e)}')
            raise StrategyError(f'접근 가능한 전략 조회 실패: {str(e)}')
    
    def create_strategy(self, user_id: int, strategy_data: Dict[str, Any]) -> Dict[str, Any]:
        """새 전략 생성"""
        try:
            # 입력 데이터 검증
            required_fields = ['name', 'group_name']
            for field in required_fields:
                if not strategy_data.get(field):
                    raise StrategyError(f'{field} 필드가 필요합니다.')
            
            # market_type 검증
            market_type = strategy_data.get('market_type', 'spot')
            if market_type not in ['spot', 'futures']:
                raise StrategyError('market_type은 "spot" 또는 "futures"만 가능합니다.')
            
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
                is_active=strategy_data.get('is_active', True),
                is_public=strategy_data.get('is_public', False)
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
            updatable_fields = ['name', 'description', 'is_active', 'is_public']
            
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
                'is_active': strategy.is_active,
                'is_public': strategy.is_public
            }
            
        except StrategyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'전략 수정 오류: {str(e)}')
            raise StrategyError(f'전략 수정 실패: {str(e)}')

    def subscribe_to_strategy(self, strategy_id: int, user_id: int, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """공개 전략 구독: 현재 사용자 소유 계좌를 전략에 연결한다.
        소유자는 공개 여부와 관계없이 자신의 전략에 계좌를 연결할 수 있다.
        """
        try:
            strategy = Strategy.query.filter_by(id=strategy_id).first()
            if not strategy:
                raise StrategyError('전략을 찾을 수 없습니다.')

            if not strategy.is_public and strategy.user_id != user_id:
                raise StrategyError('공개되지 않은 전략입니다.')

            account = Account.query.filter_by(id=account_data['account_id'], user_id=user_id).first()
            if not account:
                raise StrategyError('계좌를 찾을 수 없습니다.')

            existing_connection = StrategyAccount.query.filter_by(
                strategy_id=strategy.id,
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
                max_symbols=max_symbols
            )

            self.session.add(strategy_account)
            self.session.commit()

            # 자본 자동 배분
            capital_service.auto_allocate_capital_for_account(account.id)

            logger.info(f'공개 전략 구독: 전략 {strategy.name} - 계좌 {account.name}')

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
            logger.error(f'공개 전략 구독 오류: {str(e)}')
            raise StrategyError(f'공개 전략 구독 실패: {str(e)}')

    def unsubscribe_from_strategy(self, strategy_id: int, user_id: int, account_id: int) -> bool:
        """공개 전략 구독 해제: 현재 사용자 소유 계좌 연결을 제거한다(활성 포지션 없을 때)."""
        try:
            strategy_account = StrategyAccount.query.filter_by(
                strategy_id=strategy_id,
                account_id=account_id
            ).first()

            if not strategy_account:
                raise StrategyError('연결된 계좌를 찾을 수 없습니다.')

            if strategy_account.account.user_id != user_id:
                raise StrategyError('권한이 없습니다.')

            # 활성 포지션 확인
            if hasattr(strategy_account, 'strategy_positions') and strategy_account.strategy_positions:
                active_positions = [pos for pos in strategy_account.strategy_positions if pos.quantity != 0]
                if active_positions:
                    raise StrategyError('활성 포지션이 있는 계좌는 연결 해제할 수 없습니다. 먼저 모든 포지션을 청산하세요.')

            account_name = strategy_account.account.name
            # 세션 분리/삭제 후 lazy load 방지를 위해 미리 참조값 보관
            strategy_name = strategy_account.strategy.name if hasattr(strategy_account, 'strategy') and strategy_account.strategy else '알수없음'
            self.session.delete(strategy_account)
            self.session.commit()

            # 남은 전략들로 자본 재배분
            capital_service.auto_allocate_capital_for_account(account_id)

            logger.info(f'공개 전략 구독 해제: 전략 {strategy_name} - 계좌 {account_name}')
            return True

        except StrategyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'공개 전략 구독 해제 오류: {str(e)}')
            raise StrategyError(f'공개 전략 구독 해제 실패: {str(e)}')
    
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