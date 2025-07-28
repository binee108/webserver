#!/usr/bin/env python3
"""
웹훅 API 테스트 스크립트 - BTCUSDT 거래 테스트

이 스크립트는 실행 중인 거래 시스템(python run.py start)에 대해 
BTCUSDT 심볼로 웹훅 API를 테스트합니다.

사용법:
1. 웹 인터페이스에서 계좌와 전략을 등록
2. 아래 GROUP_NAME을 등록한 전략의 group_name으로 수정
3. python run.py start로 서비스 실행
4. 이 테스트 파일 실행: python test_webhook_api.py

주의사항:
- 실제 거래소 연결을 통해 실제 주문이 실행됩니다
- 테스트용 소액으로 설정하여 실행하세요
- 테스트 전 충분한 잔고가 있는지 확인하세요
"""

import requests
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, List

# ==================== 설정 섹션 ====================
# 사용자가 수정해야 하는 부분

# 테스트할 전략의 group_name (웹 인터페이스에서 등록한 전략명)
GROUP_NAME = "test"  # 👈 여기를 수정하세요!

# 서버 설정
SERVER_URL = "https://localhost:443"  # SSL 사용시
# SERVER_URL = "http://localhost:5001"  # SSL 미사용시

# 테스트 설정
SYMBOL = "BTCUSDT"              # 테스트할 심볼
EXCHANGE = "BINANCE"            # 거래소
MARKET = "FUTURE"                 # 시장 타입 (SPOT/FUTURE)  
CURRENCY = "USDT"               # 결제 통화
TEST_QUANTITY_PERCENT = 10       # 테스트용 수량 비율 (%)
REQUEST_TIMEOUT = 30            # 요청 타임아웃 (초)

# ==================== 로깅 설정 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'webhook_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# ==================== 테스트 클래스 ====================
class WebhookTester:
    """웹훅 API 테스트 클래스"""
    
    def __init__(self, base_url: str, group_name: str):
        self.base_url = base_url
        self.webhook_url = f"{base_url}/api/webhook"
        self.group_name = group_name
        self.headers = {"Content-Type": "application/json"}
        self.session = requests.Session()
        
        # SSL 인증서 검증 비활성화 (개발 환경용)
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session.verify = False
        
        # Connection pooling 비활성화
        adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        self.test_results = []
        
    def log_test_start(self, test_name: str):
        """테스트 시작 로그"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 테스트 시작: {test_name}")
        logger.info(f"{'='*60}")
        
    def log_test_result(self, test_name: str, success: bool, response_data: Dict[str, Any] = None, error: str = None):
        """테스트 결과 로그"""
        status = "✅ 성공" if success else "❌ 실패"
        logger.info(f"{status}: {test_name}")
        
        if response_data:
            logger.info(f"응답 데이터: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
        
        if error:
            logger.error(f"오류: {error}")
            
        self.test_results.append({
            'test_name': test_name,
            'success': success,
            'response': response_data,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"{'='*60}\n")
        
    def send_webhook(self, data: Dict[str, Any]) -> tuple[bool, Dict[str, Any], str]:
        """웹훅 전송"""
        try:
            logger.info(f"📤 웹훅 전송 데이터: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            response = self.session.post(
                self.webhook_url,
                headers=self.headers,
                json=data,
                timeout=REQUEST_TIMEOUT
            )
            
            logger.info(f"📥 응답 상태 코드: {response.status_code}")
            
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = {"raw_response": response.text}
                
            if response.status_code == 200:
                return True, response_data, None
            else:
                return False, response_data, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, {}, "요청 타임아웃"
        except requests.exceptions.ConnectionError:
            return False, {}, "연결 오류 - 서버가 실행 중인지 확인하세요"
        except Exception as e:
            return False, {}, f"예상치 못한 오류: {str(e)}"
    
    def test_market_buy(self, qty_percent: int = TEST_QUANTITY_PERCENT):
        """시장가 매수 테스트"""
        test_name = f"시장가 매수 ({qty_percent}%)"
        self.log_test_start(test_name)
        
        data = {
            "group_name": self.group_name,
            "exchange": EXCHANGE,
            "market": MARKET,
            "currency": CURRENCY,
            "symbol": SYMBOL,
            "orderType": "MARKET",
            "side": "buy",
            "qty_per": qty_percent
        }
        
        success, response, error = self.send_webhook(data)
        self.log_test_result(test_name, success, response, error)
        return success
        
    def test_market_sell(self, qty_percent: int = TEST_QUANTITY_PERCENT):
        """시장가 매도 테스트"""
        test_name = f"시장가 매도 ({qty_percent}%)"
        self.log_test_start(test_name)
        
        data = {
            "group_name": self.group_name,
            "exchange": EXCHANGE,
            "market": MARKET,
            "currency": CURRENCY,
            "symbol": SYMBOL,
            "orderType": "MARKET",
            "side": "sell",
            "qty_per": qty_percent
        }
        
        success, response, error = self.send_webhook(data)
        self.log_test_result(test_name, success, response, error)
        return success
        
    def test_limit_buy(self, price: float, qty_percent: int = TEST_QUANTITY_PERCENT):
        """지정가 매수 테스트"""
        test_name = f"지정가 매수 (가격: {price}, 수량: {qty_percent}%)"
        self.log_test_start(test_name)
        
        data = {
            "group_name": self.group_name,
            "exchange": EXCHANGE,
            "market": MARKET,
            "currency": CURRENCY,
            "symbol": SYMBOL,
            "orderType": "LIMIT",
            "side": "buy",
            "price": price,
            "qty_per": qty_percent
        }
        
        success, response, error = self.send_webhook(data)
        self.log_test_result(test_name, success, response, error)
        return success
        
    def test_limit_sell(self, price: float, qty_percent: int = TEST_QUANTITY_PERCENT):
        """지정가 매도 테스트"""
        test_name = f"지정가 매도 (가격: {price}, 수량: {qty_percent}%)"
        self.log_test_start(test_name)
        
        data = {
            "group_name": self.group_name,
            "exchange": EXCHANGE,
            "market": MARKET,
            "currency": CURRENCY,
            "symbol": SYMBOL,
            "orderType": "LIMIT",
            "side": "sell",
            "price": price,
            "qty_per": qty_percent
        }
        
        success, response, error = self.send_webhook(data)
        self.log_test_result(test_name, success, response, error)
        return success
        
    def test_cancel_all_orders(self, symbol: str = None):
        """모든 주문 취소 테스트"""
        test_name = f"모든 주문 취소" + (f" ({symbol})" if symbol else "")
        self.log_test_start(test_name)
        
        data = {
            "group_name": self.group_name,
            "orderType": "CANCEL_ALL_ORDER"
        }
        
        if symbol:
            data["symbol"] = symbol
            
        data["exchange"] = EXCHANGE
        data["market"] = MARKET
        
        success, response, error = self.send_webhook(data)
        self.log_test_result(test_name, success, response, error)
        return success
        
    def test_invalid_request(self):
        """잘못된 요청 테스트 (오류 시나리오)"""
        test_name = "잘못된 요청 (필수 필드 누락)"
        self.log_test_start(test_name)
        
        data = {
            "group_name": self.group_name,
            "symbol": SYMBOL,
            "side": "buy"
            # exchange, market, currency, orderType 누락
        }
        
        success, response, error = self.send_webhook(data)
        # 이 테스트는 실패가 예상되는 테스트이므로 실패하면 성공으로 간주
        if not success and response.get("success") == False:
            self.log_test_result(test_name, True, response, "예상된 오류 (정상)")
            return True
        else:
            self.log_test_result(test_name, False, response, "오류가 발생해야 하는데 성공함")
            return False
        
    def test_nonexistent_strategy(self):
        """존재하지 않는 전략 테스트"""
        test_name = "존재하지 않는 전략"
        self.log_test_start(test_name)
        
        data = {
            "group_name": "nonexistent_strategy_12345",
            "exchange": EXCHANGE,
            "market": MARKET,
            "currency": CURRENCY,
            "symbol": SYMBOL,
            "orderType": "MARKET",
            "side": "buy",
            "qty_per": 1
        }
        
        success, response, error = self.send_webhook(data)
        # 이 테스트는 실패가 예상되는 테스트이므로 실패하면 성공으로 간주
        if not success and response.get("success") == False:
            self.log_test_result(test_name, True, response, "예상된 오류 (정상)")
            return True
        else:
            self.log_test_result(test_name, False, response, "오류가 발생해야 하는데 성공함")
            return False
            
    def print_summary(self):
        """테스트 결과 요약 출력"""
        logger.info(f"\n{'='*80}")
        logger.info(f"🏁 테스트 완료 - 전체 결과 요약")
        logger.info(f"{'='*80}")
        
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - successful_tests
        
        logger.info(f"📊 전체 테스트: {total_tests}개")
        logger.info(f"✅ 성공: {successful_tests}개")
        logger.info(f"❌ 실패: {failed_tests}개")
        logger.info(f"📈 성공률: {(successful_tests/total_tests*100):.1f}%")
        
        if failed_tests > 0:
            logger.info(f"\n❌ 실패한 테스트 상세:")
            for result in self.test_results:
                if not result['success']:
                    logger.error(f"  - {result['test_name']}: {result['error']}")
        
        logger.info(f"\n💡 팁:")
        logger.info(f"  - 실패한 테스트가 있다면 서버 로그를 확인하세요")
        logger.info(f"  - 전략명 '{self.group_name}'이 올바른지 확인하세요")
        logger.info(f"  - 계좌가 전략에 연결되어 있는지 확인하세요")
        logger.info(f"  - 계좌에 충분한 잔고가 있는지 확인하세요")
        
        logger.info(f"{'='*80}\n")

# ==================== 메인 테스트 실행 ====================
def main():
    """메인 테스트 실행 함수"""
    logger.info(f"🚀 웹훅 API 테스트 시작")
    logger.info(f"📋 테스트 설정:")
    logger.info(f"  - 서버 URL: {SERVER_URL}")
    logger.info(f"  - 전략명: {GROUP_NAME}")
    logger.info(f"  - 심볼: {SYMBOL}")
    logger.info(f"  - 거래소: {EXCHANGE}")
    logger.info(f"  - 시장: {MARKET}")
    logger.info(f"  - 테스트 수량: {TEST_QUANTITY_PERCENT}%")
    
    # 테스터 초기화
    tester = WebhookTester(SERVER_URL, GROUP_NAME)
    
    print(f"\n⚠️  주의사항:")
    print(f"이 테스트는 실제 거래소에서 실제 주문을 실행합니다!")
    print(f"테스트용 소액으로 설정되어 있지만, 실제 거래가 발생할 수 있습니다.")
    print(f"계속하시겠습니까? (y/N): ", end="")
    
    if input().lower() != 'y':
        print("테스트가 취소되었습니다.")
        return
    
    try:
        # 실제 시세에서 +/-5% 정도로 설정 (사용자가 수동으로 조정 필요)
        btc_buy_price = 114039.5000   # 현재가보다 낮은 가격
        btc_sell_price = 120039.5000  # 현재가보다 높은 가격
        
        logger.info(f"💡 지정가 주문 가격을 현재 시세에 맞게 조정하세요!")
        logger.info(f"현재 설정: 매수 ${btc_buy_price}, 매도 ${btc_sell_price}")
        
        # 1. 지정가 매수 테스트
        logger.info(f"\n🎯 1단계: 지정가 매수 테스트")
        time.sleep(1)
        tester.test_limit_buy(btc_buy_price, TEST_QUANTITY_PERCENT)
        time.sleep(2)  # 주문간 간격
        
        # 2. 지정가 매도 테스트
        logger.info(f"\n🎯 2단계: 지정가 매도 테스트")
        time.sleep(1)
        tester.test_limit_sell(btc_sell_price, TEST_QUANTITY_PERCENT)
        time.sleep(2)
        
        # 3. 열린 주문 모두 취소 테스트
        logger.info(f"\n🔄 3단계: 열린 주문 모두 취소 테스트")
        time.sleep(1)
        tester.test_cancel_all_orders(SYMBOL)
        time.sleep(2)
        
        # 4. 시장가 매수 테스트
        logger.info(f"\n🔥 4단계: 시장가 매수 테스트")
        time.sleep(1)
        tester.test_market_buy(TEST_QUANTITY_PERCENT)
        time.sleep(2)
        
        # 5. 시장가 매도 테스트
        logger.info(f"\n🔥 5단계: 시장가 매도 테스트")
        time.sleep(1)
        tester.test_market_sell(-1)
        
    except KeyboardInterrupt:
        logger.info(f"\n⏹️  사용자에 의해 테스트가 중단되었습니다.")
    except Exception as e:
        logger.error(f"\n💥 예상치 못한 오류 발생: {str(e)}")
    finally:
        # 최종 결과 요약
        tester.print_summary()

if __name__ == "__main__":
    main()