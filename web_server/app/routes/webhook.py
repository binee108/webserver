# @FEAT:webhook-order @COMP:route @TYPE:core
"""
트레이딩뷰 웹훅 수신 엔드포인트

이 모듈은 외부 웹훅 요청을 받아 검증하고 처리하는 Flask 라우트를 제공합니다.
"""

import json
import time
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app import db, csrf
from app.models import WebhookLog
from app.services.webhook_service import webhook_service, WebhookError
from app.services.telegram import telegram_service
from app.utils.response_formatter import (
    create_success_response, create_error_response, exception_to_error_response,
    ErrorCode
)

# @FEAT:webhook-order @COMP:route @TYPE:core
# Phase 4: 타임아웃 핸들러 (@FEAT:immediate-execution @COMP:route @TYPE:core)
#
# 타임아웃 전략 (10초):
# ====================
# - 제한 시간: 10초 (plan-reviewer 권장)
#   ├─ 계산: 배치 30개 × 500ms(평균) = 15초 → 10초 제한으로 조기 차단
#
# - 메커니즘: threading.Timer (크로스 플랫폼, 멀티스레드 안전)
#   ├─ Phase 4 버그 수정 (feature-tester 발견):
#   │   이전: signal.alarm() → ValueError (Flask 워커 스레드에서 작동 불가)
#   │   수정: threading.Timer → 멀티스레드 환경에서 정상 작동
#   ├─ 호출: TimeoutContext.__enter__() → Timer 시작
#   ├─ 발생: 10초 경과 → timeout_callback() → timed_out = True
#   └─ 종료: TimeoutContext.__exit__() → Timer 취소 + timed_out 확인
#
# - 응답 정책:
#   ├─ HTTP 200 OK + error + timeout: true
#   └─ TradingView 재전송 방지 (상태코드 에러 아님)
#
# 타임아웃 메커니즘:
# ==================
# 1. TimeoutContext.__enter__(): 10초 Timer 시작
# 2. process_webhook() 실행
# 3. 10초 경과 시: Timer 콜백 → timed_out = True
# 4. TimeoutContext.__exit__(): Timer 취소
# 5. timed_out 확인 → HTTP 200 OK + error response
#
# 예시:
#   주문 100개 전송 → 10초 초과 → timed_out = True → TimeoutError
#   응답: {'success': False, 'error': 'Webhook processing timeout (10s)', 'timeout': True}
#   HTTP Status: 200 OK (TradingView 재전송 방지)

class TimeoutContext:
    """
    멀티스레드 안전 타임아웃 컨텍스트 (threading.Timer 기반).

    Flask 워커 스레드에서 안전하게 동작하며, 크로스 플랫폼 지원 (Windows, Unix).

    Phase 4 버그 수정:
    - 이전: signal.alarm() → ValueError (Flask 워커 스레드 비호환)
    - 수정: threading.Timer → 멀티스레드 환경에서 정상 작동

    사용법:
        with TimeoutContext(10) as timeout_ctx:
            # 10초 제한 작업
            result = some_long_operation()
            if timeout_ctx.timed_out:
                raise TimeoutError("Operation timed out")

    속성:
        seconds (int): 타임아웃 시간 (초)
        timed_out (bool): 타임아웃 발생 여부
        timer (threading.Timer): 내부 타이머 객체
    """
    def __init__(self, seconds):
        self.seconds = seconds
        self.timer = None
        self.timed_out = False

    def __enter__(self):
        """타임아웃 타이머 시작"""
        def timeout_callback():
            self.timed_out = True

        self.timer = threading.Timer(self.seconds, timeout_callback)
        self.timer.start()
        return self

    def __exit__(self, *args):
        """타임아웃 타이머 정리"""
        if self.timer:
            self.timer.cancel()

bp = Blueprint('webhook', __name__, url_prefix='/api')

# @FEAT:webhook-order @COMP:route @TYPE:core
@bp.route('/webhook', methods=['POST'])
@csrf.exempt  # 웹훅은 외부에서 오므로 CSRF 보호 제외
def webhook():
    """
    트레이딩뷰 웹훅 수신 엔드포인트 (Phase 4: 즉시 실행 + 타임아웃 처리)

    외부 시스템에서 전송된 주문 신호를 받아 검증하고 처리합니다.

    Phase 4 변경사항:
    - Queue 진입 제거, 모든 주문 즉시 실행
    - 10초 타임아웃 (threading.Timer, 멀티스레드 안전)
    - 배치 크기 30개 제한
    """
    # 웹훅 수신 시점 기록 (표준화된 명명 규칙)
    webhook_received_at = time.time()

    # Phase 4: 10초 타임아웃 설정 (30개 배치 기준 안전 마진)
    # threading.Timer 사용 (signal.alarm 대체, 멀티스레드 안전)
    with TimeoutContext(10) as timeout_ctx:
        try:
            # JSON 데이터 파싱
            if not request.is_json:
                return create_error_response(
                    error_code=ErrorCode.INVALID_FORMAT,
                    message="Content-Type must be application/json"
                )

            # JSON 파싱 오류를 명시적으로 처리
            try:
                data = request.get_json()
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON syntax: {str(e)}"
                current_app.logger.error(f'❌ JSON 파싱 오류: {error_msg}')
                return create_error_response(
                    error_code=ErrorCode.INVALID_JSON,
                    message="Invalid JSON syntax",
                    details=str(e)
                )
            except Exception as e:
                error_msg = f"JSON parsing error: {str(e)}"
                current_app.logger.error(f'❌ JSON 파싱 예상치 못한 오류: {error_msg}')
                return create_error_response(
                    error_code=ErrorCode.BAD_REQUEST,
                    message="JSON parsing error",
                    details=str(e)
                )

            if not data:
                return create_error_response(
                    error_code=ErrorCode.MISSING_REQUIRED_FIELD,
                    message="No JSON data provided"
                )

            current_app.logger.info(f'🔔 웹훅 수신: {json.dumps(data, ensure_ascii=False)}')

            # 웹훅 서비스를 통해 웹훅 처리 (표준화된 타이밍 전달)
            result = webhook_service.process_webhook(data, webhook_received_at)

            # Phase 4: 타임아웃 확인
            if timeout_ctx.timed_out:
                webhook_timeout_at = time.time()
                processing_time = round((webhook_timeout_at - webhook_received_at) * 1000, 2)
                current_app.logger.error(f'⏱️ 웹훅 타임아웃 (처리 시간: {processing_time}ms)')
                return create_success_response(
                    data={
                        'success': False,
                        'error': 'Webhook processing timeout (10s)',
                        'timeout': True,
                        'processing_time_ms': processing_time
                    },
                    message="웹훅 타임아웃"
                )

            # 🆕 처리 결과 상세 로깅
            action = result.get('action', 'unknown')
            strategy = result.get('strategy', 'unknown')
            results = result.get('results', [])
            summary = result.get('summary', {})

            # unknown action에 대한 경고
            if action == 'unknown':
                current_app.logger.warning(f'⚠️  Action 필드가 설정되지 않음: {strategy} - 처리 결과 분석 불가')

            if action == 'trading_signal':
                # @FEAT:webhook-order @COMP:route @TYPE:core
                # @DATA:successful_orders,failed_orders - HTTP 응답 필드명 (Phase 2: 2025-10-30)
                successful_count = summary.get('successful_orders', 0)
                failed_count = summary.get('failed_orders', 0)
                total_accounts = summary.get('total_accounts', 0)

                if successful_count > 0:
                    current_app.logger.info(f'✅ 웹훅 처리 성공: 전략 {strategy}, {successful_count}/{total_accounts} 계좌에서 거래 성공')
                else:
                    current_app.logger.error(f'❌ 웹훅 처리 실패: 전략 {strategy}, {total_accounts}개 계좌 중 성공한 거래 없음')
            else:
                current_app.logger.info(f'✅ 웹훅 처리 완료: {action} - {strategy}')

            current_app.logger.debug(f'웹훅 처리 상세 결과: {result}')

            # 웹훅 처리 완료 시점 기록
            webhook_completed_at = time.time()

            # 간소화된 성능 메트릭 (사용자에게 필요한 정보만)
            performance_metrics = result.get('performance_metrics', {})
            if not performance_metrics:
                # 기본 총 처리 시간 계산
                performance_metrics = {
                    'total_processing_time_ms': round((webhook_completed_at - webhook_received_at) * 1000, 2)
                }

            # 간소화된 응답 구조 생성
            response_data = {
                'success': True,
                'action': result.get('action', 'unknown'),
                'strategy': result.get('strategy', 'unknown'),
                'message': '웹훅 처리 성공',
                'performance_metrics': performance_metrics,
                'results': results,
                'summary': summary
            }

            # 디버그 정보 추가 (개발 환경에서만)
            if current_app.debug:
                response_data['debug'] = {
                    'original_result': result,
                    'request_size_bytes': len(request.get_data()),
                    'response_size_estimate': len(str(response_data))
                }

            return create_success_response(
                data=response_data,
                message="웹훅 처리 성공"
            )

        except WebhookError as e:
            webhook_error_at = time.time()
            processing_time = round((webhook_error_at - webhook_received_at) * 1000, 2)

            current_app.logger.error(f'❌ 웹훅 처리 오류 (처리 시간: {processing_time}ms): {str(e)}')

            # 텔레그램 오류 알림 전송 (비활성화 상태면 조용히 무시)
            try:
                if telegram_service.is_enabled():
                    telegram_service.send_webhook_error(data if 'data' in locals() else {}, str(e))
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시

            return create_error_response(
                error_code=ErrorCode.WEBHOOK_PROCESSING_ERROR,
                message=f"웹훅 처리 오류 (처리 시간: {processing_time}ms)",
                details=str(e)
            )

        except Exception as e:
            webhook_error_at = time.time()
            processing_time = round((webhook_error_at - webhook_received_at) * 1000, 2)

            current_app.logger.error(f'💥 웹훅 처리 중 예상치 못한 오류 (처리 시간: {processing_time}ms): {str(e)}')

            # 텔레그램 오류 알림 전송 (비활성화 상태면 조용히 무시)
            try:
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "웹훅 처리 시스템 오류",
                        str(e),
                        {"요청 데이터": str(data) if 'data' in locals() else "파싱 실패"}
                    )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시

            return create_error_response(
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message=f"내부 서버 오류 (처리 시간: {processing_time}ms)",
                details=str(e)
            )
