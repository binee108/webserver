# @FEAT:telegram-notification @COMP:service @TYPE:core
"""
통합 텔레그램 서비스

Telegram 알림 관련 모든 기능 통합
1인 사용자를 위한 단순하고 효율적인 알림 관리 서비스입니다.
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
import os
from app.utils.logging_security import get_secure_logger

logger = get_secure_logger(__name__)


# @FEAT:telegram-notification @COMP:service @TYPE:core
class TelegramService:
    """
    통합 텔레그램 서비스

    기존 서비스들 통합:
    - telegram_service.py (완전 통합)
    """

    # @FEAT:telegram-notification @COMP:service @TYPE:config
    def __init__(self):
        # DB 설정 우선, 환경변수는 폴백
        self.bot_token = None
        self.chat_id = None
        self.bot = None
        self._initialize_global_settings()
        logger.info("✅ 통합 텔레그램 서비스 초기화 완료")

    # @FEAT:telegram-notification @COMP:service @TYPE:config
    def _initialize_global_settings(self):
        """전역 설정 초기화 - DB 우선, 환경변수 폴백"""
        try:
            from app.models import SystemSetting

            # DB에서 설정 조회
            self.bot_token = SystemSetting.get_setting('TELEGRAM_BOT_TOKEN')
            self.chat_id = SystemSetting.get_setting('TELEGRAM_CHAT_ID')

            # DB 설정이 없으면 환경변수 사용
            if not self.bot_token:
                self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            if not self.chat_id:
                self.chat_id = os.getenv('TELEGRAM_CHAT_ID')

            # 봇 인스턴스 생성 (설정이 있을 때만)
            if self.bot_token and self.bot_token.strip():
                try:
                    self.bot = Bot(token=self.bot_token)
                    logger.info("전역 텔레그램 봇이 초기화되었습니다.")
                except Exception as bot_error:
                    logger.warning(f"전역 텔레그램 봇 생성 실패: {str(bot_error)}")
                    self.bot = None
            else:
                logger.info("전역 텔레그램 봇 토큰이 설정되지 않았습니다.")
                self.bot = None

        except Exception as e:
            # DB 접근 실패 시 환경변수 사용
            logger.warning(f"DB 설정 조회 실패, 환경변수로 폴백: {str(e)}")
            self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            self.chat_id = os.getenv('TELEGRAM_CHAT_ID')

            if self.bot_token and self.bot_token.strip():
                try:
                    self.bot = Bot(token=self.bot_token)
                    logger.info("환경변수로 전역 텔레그램 봇이 초기화되었습니다.")
                except Exception as bot_error:
                    logger.warning(f"환경변수 봇 생성 실패: {str(bot_error)}")
                    self.bot = None
            else:
                logger.info("환경변수에도 전역 텔레그램 설정이 없습니다.")
                self.bot = None

    # === 설정 관리 ===

    # @FEAT:telegram-notification @COMP:service @TYPE:helper
    def get_global_settings(self) -> dict:
        """전역 텔레그램 설정 조회"""
        try:
            from app.models import SystemSetting
            return {
                'bot_token': SystemSetting.get_setting('TELEGRAM_BOT_TOKEN'),
                'chat_id': SystemSetting.get_setting('TELEGRAM_CHAT_ID')
            }
        except Exception as e:
            logger.error(f"전역 설정 조회 실패: {str(e)}")
            return {'bot_token': None, 'chat_id': None}

    # @FEAT:telegram-notification @COMP:service @TYPE:helper
    def update_global_settings(self, bot_token: str = None, chat_id: str = None) -> bool:
        """전역 텔레그램 설정 업데이트"""
        try:
            from app.models import SystemSetting

            if bot_token is not None:
                SystemSetting.set_setting(
                    'TELEGRAM_BOT_TOKEN',
                    bot_token,
                    '시스템 오류 및 상태 알림을 위한 전역 텔레그램 봇 토큰'
                )
                self.bot_token = bot_token

            if chat_id is not None:
                SystemSetting.set_setting(
                    'TELEGRAM_CHAT_ID',
                    chat_id,
                    '시스템 오류 및 상태 알림을 위한 전역 텔레그램 Chat ID'
                )
                self.chat_id = chat_id

            # 봇 인스턴스 재생성
            if self.bot_token:
                self.bot = Bot(token=self.bot_token)
            else:
                self.bot = None

            logger.info("전역 텔레그램 설정이 업데이트되었습니다.")
            return True

        except Exception as e:
            logger.error(f"전역 설정 업데이트 실패: {str(e)}")
            return False

    # === 연결 테스트 ===

    # @FEAT:telegram-notification @COMP:service @TYPE:validation
    def test_global_settings(self) -> Dict[str, Any]:
        """저장된 전역 텔레그램 설정 테스트"""
        if not self.bot_token or not self.chat_id:
            return {
                'success': False,
                'message': '전역 텔레그램 설정이 완료되지 않았습니다.'
            }

        test_message = f"🧪 전역 텔레그램 연결 테스트\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        if self.send_message(test_message):
            return {
                'success': True,
                'message': '전역 텔레그램 연결 테스트 성공'
            }
        else:
            return {
                'success': False,
                'message': '전역 텔레그램 메시지 전송 실패'
            }

    # @FEAT:telegram-notification @COMP:service @TYPE:validation
    def test_with_params(self, bot_token: str, chat_id: str) -> Dict[str, Any]:
        """주어진 파라미터로 텔레그램 연결 테스트"""
        if not bot_token or not chat_id:
            return {
                'success': False,
                'message': '텔레그램 봇 토큰과 Chat ID를 모두 입력해야 테스트할 수 있습니다.'
            }

        if bot_token.strip() == "" or chat_id.strip() == "":
            return {
                'success': False,
                'message': '텔레그램 봇 토큰과 Chat ID에 빈 값이 포함되어 있습니다.'
            }

        try:
            # 임시 봇 생성하여 테스트
            temp_bot = Bot(token=bot_token.strip())
            test_message = f"🧪 전역 텔레그램 연결 테스트\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            # 동기적으로 메시지 전송 테스트
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(temp_bot.send_message(
                chat_id=chat_id.strip(),
                text=test_message,
                parse_mode='HTML'
            ))
            loop.close()

            logger.info(f"전역 텔레그램 테스트 성공: Chat ID={chat_id}")
            return {
                'success': True,
                'message': '전역 텔레그램 연결 테스트 성공'
            }

        except TelegramError as e:
            logger.warning(f"전역 텔레그램 테스트 실패 (Telegram API): {str(e)}")
            return {
                'success': False,
                'message': f'텔레그램 API 오류: {str(e)}'
            }
        except Exception as e:
            logger.error(f"전역 텔레그램 테스트 실패 (일반 오류): {str(e)}")
            return {
                'success': False,
                'message': f'테스트 실패: {str(e)}'
            }

    # === 사용자별 봇 관리 ===

    # @FEAT:telegram-notification @COMP:service @TYPE:helper
    def get_user_bot(self, user_telegram_bot_token: str) -> Optional[Bot]:
        """사용자별 봇 인스턴스 생성"""
        if not user_telegram_bot_token or user_telegram_bot_token.strip() == "":
            return None

        try:
            return Bot(token=user_telegram_bot_token.strip())
        except Exception as e:
            logger.error(f"사용자 봇 생성 실패: {str(e)}")
            return None

    # @FEAT:telegram-notification @COMP:service @TYPE:helper
    def get_effective_bot_and_chat(self, user_telegram_bot_token: str = None,
                                  user_telegram_id: str = None) -> tuple[Optional[Bot], Optional[str]]:
        """사용자별 또는 전역 봇과 채팅 ID 반환 (우선순위: 사용자 > 전역)"""
        # 빈 문자열을 None으로 정규화
        if user_telegram_bot_token and user_telegram_bot_token.strip() == "":
            user_telegram_bot_token = None
        if user_telegram_id and user_telegram_id.strip() == "":
            user_telegram_id = None

        # 사용자별 봇 토큰이 있으면 사용자 봇 우선
        if user_telegram_bot_token and user_telegram_id:
            logger.debug(f"사용자별 봇 토큰 시도: 토큰={user_telegram_bot_token[:20]}..., Chat ID={user_telegram_id}")
            user_bot = self.get_user_bot(user_telegram_bot_token)
            if user_bot:
                logger.debug("사용자별 봇 사용")
                return user_bot, user_telegram_id
            else:
                logger.warning("사용자별 봇 생성 실패, 전역 봇으로 폴백")

        # 사용자별 봇이 없으면 전역 봇 사용
        if user_telegram_id and self.bot:
            logger.debug(f"전역 봇 사용, 사용자 Chat ID={user_telegram_id}")
            return self.bot, user_telegram_id
        elif self.bot and self.chat_id:
            logger.debug(f"전역 봇과 전역 Chat ID 사용: {self.chat_id}")
            return self.bot, self.chat_id
        else:
            logger.warning("사용 가능한 봇과 채팅 ID가 없습니다")
            return None, None

    # === 메시지 전송 ===

    # @FEAT:telegram-notification @COMP:service @TYPE:helper
    def is_enabled(self) -> bool:
        """전역 텔레그램 알림이 활성화되어 있는지 확인"""
        is_active = (self.bot is not None and
                    self.bot_token is not None and
                    self.bot_token.strip() != "" and
                    self.chat_id is not None and
                    self.chat_id.strip() != "")

        if not is_active:
            logger.debug("전역 텔레그램 설정이 완료되지 않았습니다.")

        return is_active

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    async def send_message_async(self, message: str, parse_mode: str = 'HTML') -> bool:
        """비동기 메시지 전송"""
        if not self.is_enabled():
            logger.debug("텔레그램 알림이 비활성화되어 있습니다.")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            logger.info("텔레그램 메시지 전송 성공")
            return True

        except TelegramError as e:
            logger.error(f"텔레그램 메시지 전송 실패: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"텔레그램 메시지 전송 중 예상치 못한 오류: {str(e)}")
            return False

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """동기 메시지 전송 (새 이벤트 루프 생성)"""
        if not self.is_enabled():
            return False

        try:
            # 새 이벤트 루프 생성하여 비동기 함수 실행
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.send_message_async(message, parse_mode))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"동기 메시지 전송 실패: {str(e)}")
            return False

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_message_to_user(self, user_telegram_id: str, message: str,
                            parse_mode: str = 'HTML', user_telegram_bot_token: str = None) -> bool:
        """특정 사용자에게 메시지 전송 (사용자별 봇 토큰 지원)"""
        # 사용자별 설정 완전 검증 - 둘 다 있어야만 전송
        if not user_telegram_bot_token or not user_telegram_id:
            logger.info("사용자 텔레그램 설정 미완료 - 봇 토큰과 Chat ID 모두 필요합니다.")
            return False

        if user_telegram_bot_token.strip() == "" or user_telegram_id.strip() == "":
            logger.info("사용자 텔레그램 설정 미완료 - 빈 값이 포함되어 있습니다.")
            return False

        # 사용자 봇 생성 시도
        user_bot = self.get_user_bot(user_telegram_bot_token)
        if not user_bot:
            logger.warning("사용자 텔레그램 봇 생성 실패 - 토큰이 유효하지 않습니다.")
            return False

        try:
            # 새 이벤트 루프 생성하여 비동기 함수 실행
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._send_message_to_user_async(
                user_telegram_id, message, parse_mode, user_bot))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"사용자별 메시지 전송 실패: {str(e)}")
            return False

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    async def _send_message_to_user_async(self, user_telegram_id: str, message: str,
                                         parse_mode: str = 'HTML', bot: Bot = None) -> bool:
        """특정 사용자에게 비동기 메시지 전송"""
        # 봇이 지정되지 않으면 기본 봇 사용
        if bot is None:
            bot = self.bot

        if bot is None:
            logger.error("사용 가능한 봇이 없습니다.")
            return False

        try:
            await bot.send_message(
                chat_id=user_telegram_id,
                text=message,
                parse_mode=parse_mode
            )
            logger.info(f"사용자({user_telegram_id})에게 텔레그램 메시지 전송 성공")
            return True

        except TelegramError as e:
            logger.error(f"사용자({user_telegram_id}) 텔레그램 메시지 전송 실패: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"사용자({user_telegram_id}) 텔레그램 메시지 전송 중 예상치 못한 오류: {str(e)}")
            return False

    # === 알림 메시지들 ===

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_order_adjustment_notification(self, user_id: int, adjustment_info: Dict[str, Any]) -> bool:
        """주문 수량 자동 조정 알림 전송"""
        try:
            # 사용자 정보 조회
            from app.models import User
            user = User.query.get(user_id)
            if not user:
                logger.warning(f"사용자를 찾을 수 없습니다: {user_id}")
                return False

            # 사용자별 텔레그램 설정 확인
            effective_bot, effective_chat_id = self.get_effective_bot_and_chat(
                user.telegram_bot_token,
                user.telegram_id
            )

            if not effective_bot or not effective_chat_id:
                logger.debug(f"사용자 {user_id}의 텔레그램 설정이 없습니다.")
                return False

            # 알림 메시지 구성
            message = f"""
📊 <b>주문 수량 자동 조정 알림</b>

심볼: {adjustment_info['symbol']}
거래소: {adjustment_info['exchange']} ({adjustment_info['market_type']})

❌ <b>원래 요청</b>:
  • 수량: {adjustment_info['original_amount']:.8f}
  • 금액: {adjustment_info['original_cost']:.2f} USDT

⚠️ <b>최소 요구사항</b>:
  • 최소 수량: {adjustment_info['min_amount']:.8f}
  • 최소 금액: {adjustment_info['min_cost']:.2f} USDT
  • 거래소 최소: {adjustment_info['exchange_min_cost']:.2f} USDT

✅ <b>자동 조정됨</b>:
  • 수량: {adjustment_info['adjusted_amount']:.8f}
  • 금액: {adjustment_info['adjusted_cost']:.2f} USDT

📝 사유: {adjustment_info['reason']}
"""

            # 메시지 전송
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(effective_bot.send_message(
                chat_id=effective_chat_id,
                text=message,
                parse_mode='HTML'
            ))
            loop.close()

            logger.info(f"주문 조정 알림 전송 성공 - 사용자: {user_id}")
            return True

        except Exception as e:
            logger.error(f"주문 조정 알림 전송 실패: {str(e)}")
            return False

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_error_alert(self, error_type: str, error_message: str,
                        context: Optional[Dict[str, Any]] = None) -> bool:
        """오류 알림 전송"""
        if not self.is_enabled():
            logger.info("전역 텔레그램 설정이 미완료되어 오류 알림을 전송하지 않습니다.")
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = f"""
🚨 <b>트레이딩 시스템 오류 발생</b>

⏰ <b>시간:</b> {timestamp}
🔴 <b>오류 유형:</b> {error_type}
📝 <b>오류 메시지:</b> {error_message}
"""

        if context:
            message += "\n📊 <b>추가 정보:</b>\n"
            for key, value in context.items():
                message += f"• {key}: {value}\n"

        message += "\n⚠️ 즉시 확인이 필요합니다!"

        return self.send_message(message)

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_webhook_error(self, webhook_data: dict, error_message: str) -> bool:
        """웹훅 처리 오류 알림 전송"""
        if not self.is_enabled():
            logger.info("전역 텔레그램 설정이 미완료되어 웹훅 오류 알림을 전송하지 않습니다.")
            return False

        message = f"""
🚨 웹훅 처리 오류

"전략": {webhook_data.get('group_name', 'Unknown')},
"거래소": {webhook_data.get('exchange', webhook_data.get('platform', 'Unknown'))},
"오류": {error_message}
"시간": {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """

        return self.send_message(message)

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_exchange_error(self, account_id: int, exchange: str, error_message: str) -> bool:
        """거래소 연결 오류 알림 전송"""
        if not self.is_enabled():
            logger.info("전역 텔레그램 설정이 미완료되어 거래소 오류 알림을 전송하지 않습니다.")
            return False

        message = f"""
⚠️ 거래소 연결 오류

"계좌 ID": {account_id},
"거래소": {exchange}
"오류": {error_message}
"시간": {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """

        return self.send_message(message)

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_trading_error(self, strategy_name: str, symbol: str, error_message: str) -> bool:
        """거래 실행 오류 알림"""
        context = {
            "전략": strategy_name,
            "심볼": symbol
        }

        return self.send_error_alert("거래 실행 오류", error_message, context)

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_system_status(self, status: str, details: Optional[str] = None) -> bool:
        """시스템 상태 알림"""
        if not self.is_enabled():
            logger.info("전역 텔레그램 설정이 미완료되어 시스템 상태 알림을 전송하지 않습니다.")
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if status == "startup":
            message = f"""
✅ <b>트레이딩 시스템 시작</b>

⏰ <b>시간:</b> {timestamp}
🟢 <b>상태:</b> 정상 가동 중
"""
        elif status == "shutdown":
            message = f"""
🔴 <b>트레이딩 시스템 종료</b>

⏰ <b>시간:</b> {timestamp}
⚠️ <b>상태:</b> 시스템 종료됨
"""
        else:
            message = f"""
ℹ️ <b>시스템 상태 업데이트</b>

⏰ <b>시간:</b> {timestamp}
📊 <b>상태:</b> {status}
"""

        if details:
            message += f"\n📝 <b>세부사항:</b> {details}"

        return self.send_message(message)

    # @FEAT:telegram-notification @COMP:service @TYPE:core @DEPS:order-queue
    def send_order_failure_alert(
        self,
        strategy: 'Strategy',
        account: 'Account',
        symbol: str,
        error_type: str,
        error_message: str
    ) -> bool:
        """
        복구 불가능한 주문 실패 시 텔레그램 알림 발송

        Args:
            strategy: 전략 객체
            account: 계정 객체
            symbol: 심볼
            error_type: 실패 유형
            error_message: 에러 메시지

        Returns:
            bool: 알림 발송 성공 여부
        """
        # 에러 유형 한글 변환
        error_type_kr = {
            'insufficient_balance': '잔고 부족',
            'invalid_symbol': '잘못된 심볼',
            'limit_exceeded': '제한 초과',
            'rate_limit': '요청 제한 초과',
            'network_error': '네트워크 오류',
            'unknown': '알 수 없는 오류'
        }.get(error_type, error_type)

        message = f"""
⚠️ <b>주문 실패 알림 (복구 불가능)</b>

<b>전략:</b> {strategy.name}
<b>계정:</b> {account.name}
<b>심볼:</b> {symbol}
<b>실패 유형:</b> {error_type_kr}

<b>오류 상세:</b>
{error_message}

<b>조치 필요:</b>
• 잔고 부족: 계정 잔고 확인 필요
• 잘못된 심볼: 웹훅 설정 확인
• 제한 초과: 주문 수량 조정 필요
        """.strip()

        try:
            # 사용자별 텔레그램 설정 확인
            from app.models import User
            user = User.query.get(strategy.user_id)
            if not user:
                logger.warning(f"사용자를 찾을 수 없습니다: {strategy.user_id}")
                return False

            # 사용자별 봇으로 메시지 전송
            if user.telegram_bot_token and user.telegram_id:
                result = self.send_message_to_user(
                    user_telegram_id=user.telegram_id,
                    message=message,
                    parse_mode='HTML',
                    user_telegram_bot_token=user.telegram_bot_token
                )
            else:
                # 전역 봇으로 메시지 전송
                result = self.send_message(message, parse_mode='HTML')

            if result:
                logger.info(f"📱 주문 실패 알림 발송 완료 - user_id: {strategy.user_id}")
            return result
        except Exception as e:
            logger.error(f"텔레그램 알림 발송 실패: {e}")
            return False

    # @FEAT:telegram-notification @COMP:service @TYPE:core
    def send_daily_summary(self, summary_data: Dict[str, Any]) -> bool:
        """일일 트레이딩 요약 보고서 전송"""
        if not self.is_enabled():
            logger.info("전역 텔레그램 설정이 미완료되어 일일 요약 보고서를 전송하지 않습니다.")
            return False

        date_str = summary_data.get('date', datetime.now().strftime('%Y-%m-%d'))

        # 기본 정보
        total_volume = summary_data.get('total_volume', 0)
        total_pnl = summary_data.get('total_pnl', 0)
        total_unrealized_pnl = summary_data.get('total_unrealized_pnl', 0)
        trade_count = summary_data.get('trade_count', 0)
        success_rate = summary_data.get('success_rate', 0)

        # 시스템 상태
        active_strategies = summary_data.get('active_strategies', 0)
        active_accounts = summary_data.get('active_accounts', 0)
        open_positions = summary_data.get('open_positions', 0)
        open_orders = summary_data.get('open_orders', 0)

        # 변화율
        volume_change = summary_data.get('volume_change', 0)
        pnl_change = summary_data.get('pnl_change', 0)

        # 이모지 설정
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        volume_emoji = "⬆️" if volume_change >= 0 else "⬇️"
        pnl_change_emoji = "⬆️" if pnl_change >= 0 else "⬇️"

        message = f"""
📊 <b>일일 트레이딩 요약 - {date_str}</b>

💰 <b>거래 성과</b>
• 총 거래량: {total_volume:,.2f} USDT {volume_emoji} ({volume_change:+.1f}%)
• 실현 손익: {total_pnl:+,.2f} USDT {pnl_emoji} ({pnl_change:+.1f}%)
• 미실현 손익: {total_unrealized_pnl:+,.2f} USDT
• 총 손익: {(total_pnl + total_unrealized_pnl):+,.2f} USDT

📈 <b>거래 통계</b>
• 거래 횟수: {trade_count}회
• 성공률: {success_rate:.1f}%"""

        # trade_count가 0보다 클 때만 평균 거래량 계산
        if trade_count > 0:
            avg_volume = total_volume / trade_count
            message += f"\n• 평균 거래량: {avg_volume:,.2f} USDT (거래당)"
        else:
            message += f"\n• 평균 거래량: 0.00 USDT (거래 없음)"

        message += f"""

🎯 <b>시스템 현황</b>
• 활성 전략: {active_strategies}개
• 연결된 계좌: {active_accounts}개
• 열린 포지션: {open_positions}개
• 미체결 주문: {open_orders}개
"""

        # 오류가 있는 경우 추가 정보
        if 'error' in summary_data:
            message += f"\n⚠️ <b>주의사항:</b> 데이터 수집 중 일부 오류 발생\n• {summary_data['error']}"

        # 성과 평가 코멘트
        if total_pnl > 0:
            if success_rate >= 70:
                message += "\n\n🎉 <b>우수한 성과!</b> 높은 성공률과 수익을 기록했습니다."
            elif success_rate >= 50:
                message += "\n\n👍 <b>양호한 성과!</b> 안정적인 수익을 기록했습니다."
            else:
                message += "\n\n⚠️ <b>주의 필요!</b> 수익은 있지만 성공률이 낮습니다."
        elif total_pnl < 0:
            message += "\n\n🔍 <b>검토 필요!</b> 손실이 발생했습니다. 전략을 점검해보세요."
        else:
            message += "\n\n📊 <b>보합세!</b> 큰 변동 없이 안정적인 하루였습니다."

        return self.send_message(message)

    # === 사용자별 기능 ===

    # @FEAT:telegram-notification @COMP:service @TYPE:validation
    def test_user_connection(self, user_telegram_id: str, user_telegram_bot_token: str = None) -> Dict[str, Any]:
        """특정 사용자의 텔레그램 연결 테스트 (사용자별 봇 토큰 지원)"""
        # 사용자별 설정 완전 검증 - 둘 다 필요
        if not user_telegram_bot_token or not user_telegram_id:
            return {
                'success': False,
                'message': '텔레그램 봇 토큰과 Chat ID를 모두 입력해야 테스트할 수 있습니다.'
            }

        if user_telegram_bot_token.strip() == "" or user_telegram_id.strip() == "":
            return {
                'success': False,
                'message': '텔레그램 봇 토큰과 Chat ID에 빈 값이 포함되어 있습니다.'
            }

        # 사용자 봇 생성 시도
        user_bot = self.get_user_bot(user_telegram_bot_token)
        if not user_bot:
            return {
                'success': False,
                'message': '입력하신 텔레그램 봇 토큰이 유효하지 않습니다. 토큰을 확인해주세요.'
            }

        test_message = f"🧪 개인 텔레그램 연결 테스트\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        if self.send_message_to_user(user_telegram_id, test_message,
                                   parse_mode='HTML', user_telegram_bot_token=user_telegram_bot_token):
            return {
                'success': True,
                'message': '텔레그램 연결 테스트 성공'
            }
        else:
            return {
                'success': False,
                'message': '텔레그램 메시지 전송 실패'
            }

    # @FEAT:telegram-notification @COMP:service @TYPE:helper
    def send_user_notification(self, user_telegram_id: str, title: str, message: str,
                              context: Optional[Dict[str, Any]] = None,
                              user_telegram_bot_token: str = None) -> bool:
        """사용자별 알림 전송 (사용자별 봇 토큰 지원)"""
        if not user_telegram_id:
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        notification = f"""
📢 <b>{title}</b>

⏰ <b>시간:</b> {timestamp}
📝 <b>내용:</b> {message}
"""

        if context:
            notification += "\n📊 <b>상세 정보:</b>\n"
            for key, value in context.items():
                notification += f"• {key}: {value}\n"

        return self.send_message_to_user(user_telegram_id, notification,
                                       parse_mode='HTML', user_telegram_bot_token=user_telegram_bot_token)

    # === 유틸리티 ===

    # @FEAT:telegram-notification @COMP:service @TYPE:validation
    def test_connection(self) -> Dict[str, Any]:
        """텔레그램 연결 테스트"""
        if not self.is_enabled():
            return {
                'success': False,
                'message': '텔레그램 설정이 완료되지 않았습니다.'
            }

        test_message = f"🧪 텔레그램 연결 테스트\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        if self.send_message(test_message):
            return {
                'success': True,
                'message': '텔레그램 연결 테스트 성공'
            }
        else:
            return {
                'success': False,
                'message': '텔레그램 메시지 전송 실패'
            }

    # @FEAT:telegram-notification @COMP:service @TYPE:helper
    def get_stats(self) -> Dict[str, Any]:
        """서비스 통계"""
        return {
            'global_enabled': self.is_enabled(),
            'has_bot_token': bool(self.bot_token),
            'has_chat_id': bool(self.chat_id),
            'bot_initialized': self.bot is not None
        }

    # @FEAT:telegram-notification @COMP:service @TYPE:helper
    def is_available(self) -> bool:
        """서비스 사용 가능 여부"""
        return True  # 텔레그램 서비스는 항상 사용 가능 (설정이 없어도 동작)


# 싱글톤 인스턴스
telegram_service = TelegramService()
