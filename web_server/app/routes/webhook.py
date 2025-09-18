import json
import time
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app import db, csrf
from app.models import WebhookLog
from app.services.webhook_service import webhook_service, WebhookError
from app.services.telegram_service import telegram_service
from app.utils.response_formatter import (
    create_success_response, create_error_response, exception_to_error_response,
    ErrorCode, adaptive_response
)

bp = Blueprint('webhook', __name__, url_prefix='/api')

@bp.route('/webhook', methods=['POST'])
@csrf.exempt  # 웹훅은 외부에서 오므로 CSRF 보호 제외
def webhook():
    """트레이딩뷰 웹훅 수신 엔드포인트"""
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
        
        # 웹훅 서비스를 통해 웹훅 처리
        result = webhook_service.process_webhook(data)
        
        # 🆕 처리 결과 상세 로깅
        action = result.get('action', 'unknown')
        strategy = result.get('strategy', 'unknown')
        results = result.get('results', [])
        summary = result.get('summary', {})
        
        if action == 'trading_signal':
            successful_count = summary.get('successful_trades', 0)
            failed_count = summary.get('failed_trades', 0)
            total_accounts = summary.get('total_accounts', 0)
            
            if successful_count > 0:
                current_app.logger.info(f'✅ 웹훅 처리 성공: 전략 {strategy}, {successful_count}/{total_accounts} 계좌에서 거래 성공')
            else:
                current_app.logger.error(f'❌ 웹훅 처리 실패: 전략 {strategy}, {total_accounts}개 계좌 중 성공한 거래 없음')
        else:
            current_app.logger.info(f'✅ 웹훅 처리 완료: {action} - {strategy}')
        
        current_app.logger.debug(f'웹훅 처리 상세 결과: {result}')
        
        # 성능 요약 정보 수집
        performance_summary = {}
        webhook_timing = result.get('webhook_timing', {})
        
        if webhook_timing.get('received_at'):
            # 총 처리 시간 계산 (밀리초)
            total_processing_time_ms = round((time.time() - webhook_timing['received_at']) * 1000, 2)
            performance_summary['total_processing_time_ms'] = total_processing_time_ms
            
            # 구현 타입별 통계 수집
            implementation_stats = {'custom': 0, 'ccxt': 0, 'unknown': 0}
            total_order_time_ms = 0
            order_count = 0
            
            # results가 리스트인 경우 (trading_signal)
            if isinstance(results, list):
                for trade_result in results:
                    if isinstance(trade_result, dict) and trade_result.get('success'):
                        perf = trade_result.get('performance', {})
                        impl_type = perf.get('implementation', 'unknown')
                        order_time = perf.get('order_execution_time_ms', 0)
                        
                        if impl_type in implementation_stats:
                            implementation_stats[impl_type] += 1
                        total_order_time_ms += order_time
                        order_count += 1
            
            performance_summary.update({
                'average_order_execution_time_ms': round(total_order_time_ms / order_count, 2) if order_count > 0 else 0,
                'implementation_usage': implementation_stats,
                'total_orders_processed': order_count,
                'received_at': webhook_timing.get('received_timestamp')
            })
        
        return create_success_response(
            data={
                'result': result,
                'performance_summary': performance_summary
            },
            message="웹훅 처리 성공"
        )
        
    except WebhookError as e:
        current_app.logger.error(f'❌ 웹훅 처리 오류: {str(e)}')
        
        # 텔레그램 오류 알림 전송 (비활성화 상태면 조용히 무시)
        try:
            if telegram_service.is_enabled():
                telegram_service.send_webhook_error(data if 'data' in locals() else {}, str(e))
        except Exception:
            pass  # 텔레그램 알림 실패는 조용히 무시
        
        return create_error_response(
            error_code=ErrorCode.WEBHOOK_PROCESSING_ERROR,
            message="웹훅 처리 오류",
            details=str(e)
        )
        
    except Exception as e:
        current_app.logger.error(f'💥 웹훅 처리 중 예상치 못한 오류: {str(e)}')
        
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
            message="내부 서버 오류",
            details=str(e)
        ) 