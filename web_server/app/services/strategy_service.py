"""
전략 관리 서비스 모듈
전략 생성, 조회, 수정, 삭제 등 전략 관련 비즈니스 로직
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import selectinload, joinedload  # eager loading을 위한 import 추가

from app import db
from app.models import Strategy, Account, StrategyAccount, StrategyCapital
from app.services.analytics import analytics_service
from app.constants import MarketType
from flask import current_app

logger = logging.getLogger(__name__)

class StrategyError(Exception):
    """전략 관련 오류"""
    pass

class StrategyService:
    """전략 서비스 클래스"""
    
    def __init__(self):
        self.session = db.session
    
    def _validate_strategy_data(self, data: Dict[str, Any]) -> None:
        """전략 데이터 포괄적 검증 - RCE 예방 수칙 준수"""
        if not isinstance(data, dict):
            raise StrategyError('입력 데이터는 딕셔너리 형태여야 합니다')
        
        # 필수 필드 검증
        if 'name' in data:
            name = data['name']
            if not isinstance(name, str):
                raise StrategyError('전략명은 문자열이어야 합니다')
            if not name.strip():
                raise StrategyError('전략명은 필수입니다')
            if len(name) > 100:
                raise StrategyError('전략명은 100자를 초과할 수 없습니다')
            # 위험한 문자열 패턴 차단
            if any(char in name for char in ['<', '>', '{', '}', '"', "'", '\\', '\n', '\r']):
                raise StrategyError('전략명에 특수문자를 포함할 수 없습니다')
        
        if 'group_name' in data:
            group_name = data['group_name']
            if not isinstance(group_name, str):
                raise StrategyError('그룹명은 문자열이어야 합니다')
            if not group_name.strip():
                raise StrategyError('그룹명은 필수입니다')
            if len(group_name) > 50:
                raise StrategyError('그룹명은 50자를 초과할 수 없습니다')
            # 알파벳, 숫자, 하이픈, 언더스코어만 허용
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', group_name):
                raise StrategyError('그룹명은 영문, 숫자, 하이픈, 언더스코어만 사용 가능합니다')
        
        if 'description' in data:
            description = data['description']
            if description is not None:
                if not isinstance(description, str):
                    raise StrategyError('설명은 문자열이어야 합니다')
                if len(description) > 1000:
                    raise StrategyError('설명은 1000자를 초과할 수 없습니다')
        
        # 불린 필드 검증
        for bool_field in ['is_active', 'is_public']:
            if bool_field in data:
                value = data[bool_field]
                if not isinstance(value, bool):
                    raise StrategyError(f'{bool_field}는 불린 값이어야 합니다')
        
        # market_type 검증
        if 'market_type' in data:
            market_type = data['market_type']
            if market_type is not None:
                if not isinstance(market_type, str):
                    raise StrategyError('마켓 타입은 문자열이어야 합니다')
                # MarketType 클래스에서 검증
                market_type = MarketType.normalize(market_type)
                if not MarketType.is_valid(market_type):
                    raise StrategyError(f'마켓 타입은 {MarketType.VALID_TYPES}만 가능합니다')

    def _validate_account_data(self, data: Dict[str, Any]) -> None:
        """계좌 연결 데이터 포괄적 검증 - RCE 예방 수칙 준수"""
        if not isinstance(data, dict):
            raise StrategyError('계좌 데이터는 딕셔너리 형태여야 합니다')
        
        # account_id 검증
        if 'account_id' not in data:
            raise StrategyError('account_id는 필수입니다')
        
        account_id = data['account_id']
        if not isinstance(account_id, int):
            raise StrategyError('account_id는 정수여야 합니다')
        if account_id <= 0:
            raise StrategyError('account_id는 양의 정수여야 합니다')
        
        # weight 검증
        if 'weight' in data:
            weight = data['weight']
            if weight is not None:
                if not isinstance(weight, (int, float)):
                    raise StrategyError('가중치는 숫자여야 합니다')
                if not (0.01 <= weight <= 100.0):
                    raise StrategyError('가중치는 0.01과 100.0 사이여야 합니다')
        
        # leverage 검증
        if 'leverage' in data:
            leverage = data['leverage']
            if leverage is not None:
                if not isinstance(leverage, (int, float)):
                    raise StrategyError('레버리지는 숫자여야 합니다')
                if not (0.1 <= leverage <= 125.0):
                    raise StrategyError('레버리지는 0.1과 125.0 사이여야 합니다')
        
        # max_symbols 포괄적 검증 (요구사항의 핵심)
        if 'max_symbols' in data:
            max_symbols = data['max_symbols']
            if max_symbols is not None:
                if not isinstance(max_symbols, int):
                    raise StrategyError('최대 보유 심볼 수는 정수여야 합니다')
                if not (1 <= max_symbols <= 1000):
                    raise StrategyError('최대 보유 심볼 수는 1과 1000 사이여야 합니다')

    def _validate_update_data(self, data: Dict[str, Any]) -> None:
        """업데이트 데이터 검증 - 허용된 필드만 수정 가능"""
        if not isinstance(data, dict):
            raise StrategyError('업데이트 데이터는 딕셔너리 형태여야 합니다')
        
        allowed_fields = {'name', 'description', 'is_active', 'is_public'}
        invalid_fields = set(data.keys()) - allowed_fields
        if invalid_fields:
            raise StrategyError(f'수정할 수 없는 필드입니다: {", ".join(invalid_fields)}')
        
        # 허용된 필드들에 대해 검증
        if 'name' in data:
            self._validate_strategy_data({'name': data['name']})
        if 'description' in data:
            self._validate_strategy_data({'description': data['description']})
        if 'is_active' in data:
            self._validate_strategy_data({'is_active': data['is_active']})
        if 'is_public' in data:
            self._validate_strategy_data({'is_public': data['is_public']})

    def get_strategies_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """사용자의 전략 목록 조회 (최적화된 쿼리 패턴)"""
        try:
            # 최적화된 쿼리: 단일 쿼리로 모든 필요한 관계 로드
            strategies = (
                Strategy.query
                .options(
                    # strategy_accounts와 관련된 모든 데이터를 한 번에 로드
                    selectinload(Strategy.strategy_accounts).options(
                        joinedload(StrategyAccount.account),  # account는 1:1 관계이므로 joinedload 사용
                        joinedload(StrategyAccount.strategy_capital),  # strategy_capital도 1:1 관계
                        selectinload(StrategyAccount.strategy_positions)  # positions는 1:N 관계이므로 selectinload 사용
                    )
                )
                .filter_by(user_id=user_id)
                .all()
            )
            
            strategies_data = []
            refreshed_accounts = set()
            refresh_interval_seconds = int(current_app.config.get('CAPITAL_AUTO_REFRESH_SECONDS', 300) or 0)
            refresh_delta = timedelta(seconds=refresh_interval_seconds) if refresh_interval_seconds > 0 else None
            
            for strategy in strategies:
                # 연결된 계좌 정보 (미리 로드된 데이터 사용)
                connected_accounts = []
                total_allocated_capital = 0
                position_count = 0
                
                for sa in strategy.strategy_accounts:
                    # 소유자 확인 (미리 로드된 account 사용)
                    if not sa.account or sa.account.user_id != user_id:
                        continue

                    # 할당 자본 정보가 사전에 계산되지 않았다면 즉시 재계산을 시도한다
                    capital_obj = sa.strategy_capital
                    should_refresh = capital_obj is None

                    if not should_refresh and refresh_delta is not None:
                        last_updated = capital_obj.last_updated
                        if last_updated is None or (datetime.utcnow() - last_updated) >= refresh_delta:
                            should_refresh = True

                    if not should_refresh and capital_obj and capital_obj.allocated_capital is None:
                        should_refresh = True

                    if should_refresh and sa.account_id not in refreshed_accounts:
                        analytics_service.auto_allocate_capital_for_account(sa.account_id)
                        refreshed_accounts.add(sa.account_id)
                        capital_obj = StrategyCapital.query.filter_by(strategy_account_id=sa.id).first()
                    elif should_refresh:
                        capital_obj = StrategyCapital.query.filter_by(strategy_account_id=sa.id).first()

                    account_info = {
                        "account_id": sa.account.id,  # 통일된 명명: account_id만 사용
                        "name": sa.account.name,
                        "exchange": sa.account.exchange,
                        "weight": sa.weight,
                        "leverage": sa.leverage,
                        "max_symbols": sa.max_symbols
                    }

                    # 미리 확보된 또는 방금 계산된 strategy_capital 사용
                    if capital_obj:
                        account_info["allocated_capital"] = capital_obj.allocated_capital
                        account_info["current_pnl"] = capital_obj.current_pnl
                        total_allocated_capital += capital_obj.allocated_capital
                    else:
                        account_info["allocated_capital"] = 0
                        account_info["current_pnl"] = 0

                    connected_accounts.append(account_info)
                    
                    # 미리 로드된 strategy_positions 사용하여 position_count 계산
                    position_count += len([pos for pos in sa.strategy_positions if pos.quantity != 0])
                
                strategies_data.append({
                    "id": strategy.id,
                    "name": strategy.name,
                    "description": strategy.description,
                    "group_name": strategy.group_name,
                    "market_type": strategy.market_type,
                    "is_public": getattr(strategy, "is_public", False),
                    "is_active": strategy.is_active,
                    "created_at": strategy.created_at.isoformat(),
                    "connected_accounts": connected_accounts,
                    "total_allocated_capital": total_allocated_capital,
                    "position_count": position_count  # 최적화된 포지션 카운트
                })
            
            return strategies_data
            
        except Exception as e:
            logger.error(f"전략 목록 조회 오류: {str(e)}")
            raise StrategyError(f"전략 목록 조회 실패: {str(e)}")
    def get_accessible_strategies(self, user_id: int) -> List[Dict[str, Any]]:
        """사용자가 접근 가능한 전략 (최적화된 단일 쿼리)"""
        try:
            # 단일 쿼리로 소유 전략과 구독 전략을 모두 조회 (최적화)
            from sqlalchemy import or_, and_
            
            strategies = (
                Strategy.query
                .join(StrategyAccount, Strategy.id == StrategyAccount.strategy_id, isouter=True)
                .join(Account, StrategyAccount.account_id == Account.id, isouter=True)
                .options(
                    selectinload(Strategy.strategy_accounts).options(
                        joinedload(StrategyAccount.account),
                        joinedload(StrategyAccount.strategy_capital),
                        selectinload(StrategyAccount.strategy_positions)
                    )
                )
                .filter(
                    or_(
                        Strategy.user_id == user_id,  # 내가 소유한 전략
                        and_(
                            Strategy.is_public == True,  # 공개 전략이고
                            Account.user_id == user_id   # 내 계좌가 연결된 전략
                        )
                    )
                )
                .distinct()
                .all()
            )
            
            strategy_data = {}
            refreshed_accounts = set()
            refresh_interval_seconds = int(current_app.config.get('CAPITAL_AUTO_REFRESH_SECONDS', 300) or 0)
            refresh_delta = timedelta(seconds=refresh_interval_seconds) if refresh_interval_seconds > 0 else None
            
            for strategy in strategies:
                if strategy.id not in strategy_data:
                    strategy_data[strategy.id] = {
                        "id": strategy.id,
                        "name": strategy.name,
                        "description": strategy.description,
                        "group_name": strategy.group_name if strategy.user_id == user_id else None,
                        "market_type": strategy.market_type,
                        "is_active": strategy.is_active,
                        "is_public": getattr(strategy, "is_public", False),
                        "created_at": strategy.created_at.isoformat(),
                        "connected_accounts": [],
                        "position_count": 0,
                        "ownership": "owner" if strategy.user_id == user_id else "subscriber"
                    }
                
                entry = strategy_data[strategy.id]
                
                # 내 계좌만 포함 (미리 로드된 데이터 사용)
                for sa in strategy.strategy_accounts:
                    if sa.account and sa.account.user_id == user_id:
                        capital_obj = sa.strategy_capital
                        should_refresh = capital_obj is None

                        if not should_refresh and refresh_delta is not None:
                            last_updated = capital_obj.last_updated
                            if last_updated is None or (datetime.utcnow() - last_updated) >= refresh_delta:
                                should_refresh = True

                        if not should_refresh and capital_obj and capital_obj.allocated_capital is None:
                            should_refresh = True

                        if should_refresh and sa.account_id not in refreshed_accounts:
                            analytics_service.auto_allocate_capital_for_account(sa.account_id)
                            refreshed_accounts.add(sa.account_id)
                            capital_obj = StrategyCapital.query.filter_by(strategy_account_id=sa.id).first()
                        elif should_refresh:
                            capital_obj = StrategyCapital.query.filter_by(strategy_account_id=sa.id).first()

                        account_info = {
                            "account_id": sa.account.id,  # 통일된 명명: account_id만 사용
                            "name": sa.account.name,
                            "exchange": sa.account.exchange,
                            "weight": sa.weight,
                            "leverage": sa.leverage,
                            "max_symbols": sa.max_symbols,
                            "is_active": getattr(sa, "is_active", True)
                        }
                        
                        # 미리 로드된 strategy_capital 사용
                        if capital_obj:
                            account_info["allocated_capital"] = capital_obj.allocated_capital
                            account_info["current_pnl"] = capital_obj.current_pnl
                        else:
                            account_info["allocated_capital"] = 0
                            account_info["current_pnl"] = 0
                        
                        entry["connected_accounts"].append(account_info)
                        # 미리 로드된 strategy_positions 사용
                        entry["position_count"] += len([pos for pos in sa.strategy_positions if pos.quantity != 0])
            
            return list(strategy_data.values())
            
        except Exception as e:
            logger.error(f"접근 가능한 전략 조회 오류: {str(e)}")
            raise StrategyError(f"접근 가능한 전략 조회 실패: {str(e)}")
    def create_strategy(self, user_id: int, strategy_data: Dict[str, Any]) -> Dict[str, Any]:
        """새 전략 생성"""
        try:
            # 🆕 포괄적인 전략 데이터 검증
            self._validate_strategy_data(strategy_data)
            
            # 필수 필드 확인
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
                is_active=strategy_data.get('is_active', True),
                is_public=strategy_data.get('is_public', False)
            )
            
            self.session.add(strategy)
            self.session.flush()  # ID 생성을 위해 flush
            
            # 계좌 연결 정보가 있는 경우 처리
            connected_accounts = []
            if strategy_data.get('accounts'):
                for account_data in strategy_data['accounts']:
                    # 🆕 포괄적인 계좌 데이터 검증
                    self._validate_account_data(account_data)
                    
                    account = Account.query.filter_by(
                        id=account_data['account_id'], 
                        user_id=user_id
                    ).first()
                    
                    if not account:
                        self.session.rollback()
                        raise StrategyError(f'계좌 ID {account_data["account_id"]}를 찾을 수 없습니다.')
                    
                    strategy_account = StrategyAccount(
                        strategy_id=strategy.id,
                        account_id=account.id,
                        weight=account_data.get('weight', 1.0),
                        leverage=account_data.get('leverage', 1.0),
                        max_symbols=account_data.get('max_symbols')  # 🆕 검증된 최대 보유 심볼 수 설정
                    )
                    
                    self.session.add(strategy_account)
                    connected_accounts.append(account.id)
            
            self.session.commit()
            
            # 연결된 계좌들에 대해 자동 자본 할당 실행
            for account_id in connected_accounts:
                analytics_service.auto_allocate_capital_for_account(account_id)
            
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
        """전략 정보 수정 - 경쟁 조건 방지를 위한 데이터베이스 잠금 적용"""
        try:
            # 🆕 포괄적인 업데이트 데이터 검증
            self._validate_update_data(update_data)

            strategy = Strategy.query.filter_by(id=strategy_id, user_id=user_id).first()

            if not strategy:
                raise StrategyError("전략을 찾을 수 없습니다.")

            updatable_fields = ["name", "description", "is_active", "is_public"]
            for field in updatable_fields:
                if field in update_data:
                    setattr(strategy, field, update_data[field])

            strategy.updated_at = datetime.utcnow()
            self.session.commit()

            logger.info(f"전략 수정: {strategy.name} (ID: {strategy.id})")
            
            return {
                "strategy_id": strategy.id,
                "name": strategy.name,
                "description": strategy.description,
                "is_active": strategy.is_active,
                "is_public": strategy.is_public
            }
            
        except StrategyError:
            self.session.rollback()
            raise
        except Exception as e:
            logger.error(f"전략 수정 오류: {str(e)}")
            self.session.rollback()
            raise StrategyError(f"전략 수정 실패: {str(e)}")
    def subscribe_to_strategy(self, strategy_id: int, user_id: int, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """공개 전략 구독: 현재 사용자 소유 계좌를 전략에 연결한다.
        소유자는 공개 여부와 관계없이 자신의 전략에 계좌를 연결할 수 있다.
        """
        try:
            # 🆕 포괄적인 계좌 데이터 검증
            self._validate_account_data(account_data)
            
            # 트랜잭션 내에서 배타적 잠금으로 전략 및 계좌 조회
            with self.session.begin():
                strategy = Strategy.query.filter_by(id=strategy_id).with_for_update().first()
                if not strategy:
                    raise StrategyError("전략을 찾을 수 없습니다.")

                if not strategy.is_public and strategy.user_id != user_id:
                    raise StrategyError("공개되지 않은 전략입니다.")

                account = Account.query.filter_by(id=account_data["account_id"], user_id=user_id).with_for_update().first()
                if not account:
                    raise StrategyError("계좌를 찾을 수 없습니다.")

                existing_connection = StrategyAccount.query.filter_by(
                    strategy_id=strategy.id,
                    account_id=account.id
                ).first()

                if existing_connection:
                    raise StrategyError("이미 연결된 계좌입니다.")

                strategy_account = StrategyAccount(
                    strategy_id=strategy.id,
                    account_id=account.id,
                    weight=account_data.get("weight", 1.0),
                    leverage=account_data.get("leverage", 1.0),
                    max_symbols=account_data.get("max_symbols")
                )

                self.session.add(strategy_account)
                # 트랜잭션은 with 블록 종료 시 자동 커밋됨

            # 자본 자동 배분
            analytics_service.auto_allocate_capital_for_account(account.id)

            logger.info(f"공개 전략 구독: 전략 {strategy.name} - 계좌 {account.name}")

            return {
                "strategy_id": strategy.id,
                "account_id": account.id,
                "weight": strategy_account.weight,
                "leverage": strategy_account.leverage,
                "max_symbols": strategy_account.max_symbols
            }

        except StrategyError:
            raise
        except Exception as e:
            logger.error(f"공개 전략 구독 오류: {str(e)}")
            raise StrategyError(f"공개 전략 구독 실패: {str(e)}")

    def connect_account_to_strategy(self, strategy_id: int, user_id: int, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """전략에 계좌 연결"""
        try:
            # 🆕 포괄적인 계좌 데이터 검증
            self._validate_account_data(account_data)
            
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
            
            strategy_account = StrategyAccount(
                strategy_id=strategy.id,
                account_id=account.id,
                weight=account_data.get('weight', 1.0),
                leverage=account_data.get('leverage', 1.0),
                max_symbols=account_data.get('max_symbols')  # 🆕 검증된 최대 보유 심볼 수 설정
            )
            
            self.session.add(strategy_account)
            self.session.commit()
            
            # 자동 자본 할당 실행
            analytics_service.auto_allocate_capital_for_account(account.id)
            
            logger.info(f'전략-계좌 연결: 전략 {strategy.name} - 계좌 {account.name}' + 
                       (f' (최대 심볼: {account_data.get("max_symbols")})' if account_data.get("max_symbols") else ''))
            
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
            # 🆕 포괄적인 계좌 데이터 검증
            self._validate_account_data(account_data)
            
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
            
            # 설정 업데이트
            strategy_account.weight = account_data.get('weight', strategy_account.weight)
            strategy_account.leverage = account_data.get('leverage', strategy_account.leverage)
            strategy_account.max_symbols = account_data.get('max_symbols', strategy_account.max_symbols)
            
            self.session.commit()
            
            # 자동 자본 할당 실행 (설정 변경으로 인한 재할당)
            analytics_service.auto_allocate_capital_for_account(account.id)
            
            logger.info(f'전략-계좌 설정 업데이트: 전략 {strategy.name} - 계좌 {account.name}' + 
                       (f' (최대 심볼: {account_data.get("max_symbols")})' if account_data.get("max_symbols") else ''))
            
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
            analytics_service.auto_allocate_capital_for_account(account_id)

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

# 전역 인스턴스 생성
strategy_service = StrategyService()
