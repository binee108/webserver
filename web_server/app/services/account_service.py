"""
계좌 관리 서비스 모듈
계좌 생성, 조회, 수정, 삭제 등 계좌 관련 비즈니스 로직
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app import db
from app.models import Account, StrategyAccount
from app.services.exchange_service import exchange_service

logger = logging.getLogger(__name__)

class AccountError(Exception):
    """계좌 관련 오류"""
    pass

class AccountService:
    """계좌 서비스 클래스"""
    
    def __init__(self):
        self.session = db.session
    
    def get_accounts_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """사용자의 계좌 목록 조회"""
        try:
            accounts = Account.query.filter_by(user_id=user_id).all()
            accounts_data = []
            
            for account in accounts:
                # 계좌 잔고 조회 (캐시된 데이터 사용)
                try:
                    # TODO: exchange_service 수정 후 활성화
                    # balance = exchange_service.get_balance(account.exchange, account.public_api, account.secret_api)
                    # total_balance = balance.get('total', {}).get('USDT', 0)
                    total_balance = 0  # 임시로 0으로 설정
                except:
                    total_balance = 0
                
                accounts_data.append({
                    'id': account.id,
                    'name': account.name,
                    'exchange': account.exchange,
                    'public_api': account.public_api[:8] + '...' if account.public_api else '',  # 보안을 위해 일부만 표시
                    'is_active': account.is_active,
                    'updated_at': account.updated_at.isoformat() if account.updated_at else None,
                    'total_balance': total_balance,
                    'created_at': account.created_at.isoformat(),
                    'strategy_count': len(account.strategy_accounts)
                })
            
            return accounts_data
            
        except Exception as e:
            logger.error(f'계좌 목록 조회 오류: {str(e)}')
            raise AccountError(f'계좌 목록 조회 실패: {str(e)}')
    
    def create_account(self, user_id: int, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """새 계좌 생성"""
        try:
            # 입력 데이터 검증
            required_fields = ['name', 'exchange', 'public_api', 'secret_api']
            for field in required_fields:
                if not account_data.get(field):
                    raise AccountError(f'{field} 필드가 필요합니다.')
            
            # 거래소 검증
            supported_exchanges = ['binance', 'bybit', 'okx']
            if account_data['exchange'] not in supported_exchanges:
                raise AccountError(f'지원하지 않는 거래소입니다. 지원 거래소: {", ".join(supported_exchanges)}')
            
            # 거래소별 passphrase 요구사항 검증
            if account_data['exchange'].lower() == 'okx':
                if not account_data.get('passphrase'):
                    raise AccountError('OKX 거래소는 passphrase가 필수입니다.')
            
            # API 키 중복 확인
            existing_account = Account.query.filter_by(
                user_id=user_id,
                exchange=account_data['exchange'],
                public_api=account_data['public_api']
            ).first()
            
            if existing_account:
                raise AccountError('이미 등록된 API 키입니다.')
            
            # 계좌 생성
            account = Account(
                user_id=user_id,
                name=account_data['name'],
                exchange=account_data['exchange'],
                public_api=account_data['public_api'],
                secret_api=account_data['secret_api'],
                passphrase=account_data.get('passphrase', ''),  # passphrase 처리
                is_testnet=account_data.get('is_testnet', False),  # 테스트넷 여부
                is_active=account_data.get('is_active', True)
            )
            
            self.session.add(account)
            self.session.commit()
            
            logger.info(f'새 계좌 생성: {account.name} ({account.exchange})')
            
            return {
                'account_id': account.id,
                'name': account.name,
                'exchange': account.exchange,
                'is_active': account.is_active
            }
            
        except AccountError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'계좌 생성 오류: {str(e)}')
            raise AccountError(f'계좌 생성 실패: {str(e)}')
    
    def get_account_by_id(self, account_id: int, user_id: int) -> Optional[Account]:
        """ID로 계좌 조회 (권한 확인 포함)"""
        return Account.query.filter_by(id=account_id, user_id=user_id).first()
    
    def update_account(self, account_id: int, user_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """계좌 정보 수정"""
        try:
            account = self.get_account_by_id(account_id, user_id)
            if not account:
                raise AccountError('계좌를 찾을 수 없습니다.')
            
            # 수정 가능한 필드들
            updatable_fields = ['name', 'public_api', 'secret_api', 'passphrase', 'is_testnet', 'is_active']
            
            for field in updatable_fields:
                if field in update_data:
                    setattr(account, field, update_data[field])
            
            account.updated_at = datetime.utcnow()
            self.session.commit()
            
            logger.info(f'계좌 수정: {account.name} (ID: {account.id})')
            
            return {
                'account_id': account.id,
                'name': account.name,
                'exchange': account.exchange,
                'is_active': account.is_active
            }
            
        except AccountError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'계좌 수정 오류: {str(e)}')
            raise AccountError(f'계좌 수정 실패: {str(e)}')
    
    def delete_account(self, account_id: int, user_id: int) -> bool:
        """계좌 삭제"""
        try:
            account = self.get_account_by_id(account_id, user_id)
            if not account:
                raise AccountError('계좌를 찾을 수 없습니다.')
            
            # 연결된 전략이 있는지 확인
            if account.strategy_accounts:
                raise AccountError('전략에 연결된 계좌는 삭제할 수 없습니다.')
            
            self.session.delete(account)
            self.session.commit()
            
            logger.info(f'계좌 삭제: {account.name} (ID: {account.id})')
            return True
            
        except AccountError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f'계좌 삭제 오류: {str(e)}')
            raise AccountError(f'계좌 삭제 실패: {str(e)}')
    
    def test_account_connection(self, account_id: int, user_id: int) -> Dict[str, Any]:
        """계좌 연결 테스트"""
        try:
            account = self.get_account_by_id(account_id, user_id)
            if not account:
                raise AccountError('계좌를 찾을 수 없습니다.')
            
            # 거래소 연결 테스트
            try:
                balance = exchange_service.get_balance(account)
                return {
                    'success': True,
                    'message': '계좌 연결이 정상입니다.',
                    'balance_info': {
                        'total_usdt': balance.get('total', {}).get('USDT', 0),
                        'free_usdt': balance.get('free', {}).get('USDT', 0)
                    }
                }
            except Exception as e:
                logger.error(f'계좌 연결 테스트 실패: {str(e)}')
                return {
                    'success': False,
                    'message': f'계좌 연결 실패: {str(e)}'
                }
                
        except AccountError:
            raise
        except Exception as e:
            logger.error(f'계좌 연결 테스트 오류: {str(e)}')
            raise AccountError(f'계좌 연결 테스트 실패: {str(e)}')
    
    def get_account_balance(self, account_id: int, user_id: int) -> Dict[str, Any]:
        """계좌 잔고 조회"""
        try:
            account = self.get_account_by_id(account_id, user_id)
            if not account:
                raise AccountError('계좌를 찾을 수 없습니다.')
            
            if not account.is_active:
                raise AccountError('비활성화된 계좌입니다.')
            
            balance = exchange_service.get_balance(account)
            
            return {
                'account_id': account.id,
                'name': account.name,
                'exchange': account.exchange,
                'balance': balance,
                'total_usdt': balance.get('total', {}).get('USDT', 0),
                'free_usdt': balance.get('free', {}).get('USDT', 0),
                'used_usdt': balance.get('used', {}).get('USDT', 0)
            }
            
        except AccountError:
            raise
        except Exception as e:
            logger.error(f'계좌 잔고 조회 오류: {str(e)}')
            raise AccountError(f'계좌 잔고 조회 실패: {str(e)}')

# 전역 인스턴스 생성
account_service = AccountService() 