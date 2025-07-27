"""
텔레그램 알림 서비스 모듈
오류 발생 시 관리자에게 알림 전송
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
import os

logger = logging.getLogger(__name__)

class TelegramService:
    """텔레그램 알림 서비스 클래스"""
    
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.bot = None
        
        if self.bot_token:
            self.bot = Bot(token=self.bot_token)
        else:
            logger.debug("텔레그램 봇 토큰이 설정되지 않았습니다. 알림 기능이 비활성화됩니다.")
    
    def is_enabled(self) -> bool:
        """텔레그램 알림이 활성화되어 있는지 확인"""
        return (self.bot is not None and 
                self.chat_id is not None and 
                self.chat_id.strip() != "")
    
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
    
    def send_error_alert(self, error_type: str, error_message: str, 
                        context: Optional[Dict[str, Any]] = None) -> bool:
        """오류 알림 전송"""
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
    
    def send_webhook_error(self, webhook_data: dict, error_message: str) -> bool:
        """웹훅 처리 오류 알림 전송"""
        if not self.is_enabled():
            return False
        
        message = f"""
🚨 웹훅 처리 오류

"전략": {webhook_data.get('group_name', 'Unknown')},
"거래소": {webhook_data.get('exchange', webhook_data.get('platform', 'Unknown'))},
"오류": {error_message}
"시간": {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        return self.send_message(message)
    
    def send_exchange_error(self, account_id: int, exchange: str, error_message: str) -> bool:
        """거래소 연결 오류 알림 전송"""
        if not self.is_enabled():
            return False
        
        message = f"""
⚠️ 거래소 연결 오류

"계좌 ID": {account_id},
"거래소": {exchange}
"오류": {error_message}
"시간": {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        return self.send_message(message)
    
    def send_trading_error(self, strategy_name: str, symbol: str, error_message: str) -> bool:
        """거래 실행 오류 알림"""
        context = {
            "전략": strategy_name,
            "심볼": symbol
        }
        
        return self.send_error_alert("거래 실행 오류", error_message, context)
    
    def send_system_status(self, status: str, details: Optional[str] = None) -> bool:
        """시스템 상태 알림"""
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
    
    def send_daily_summary(self, summary_data: Dict[str, Any]) -> bool:
        """일일 트레이딩 요약 보고서 전송"""
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

# 전역 인스턴스
telegram_service = TelegramService() 