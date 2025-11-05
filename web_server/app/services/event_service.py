# @FEAT:event-sse @COMP:service @TYPE:core
"""
실시간 포지션/주문 업데이트 이벤트 서비스
Server-Sent Events (SSE)를 사용하여 효율적인 실시간 알림 제공
"""

import json
import logging
import threading
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import defaultdict, deque
from flask import Response
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# @FEAT:event-sse @COMP:model @TYPE:core
@dataclass
class PositionEvent:
    """포지션 이벤트 데이터 클래스"""
    event_type: str  # 'position_created', 'position_updated', 'position_closed'
    position_id: int
    symbol: str
    strategy_id: int
    user_id: int
    quantity: float
    entry_price: float
    timestamp: str
    previous_quantity: Optional[float] = None
    # 계좌 정보 (중첩 구조)
    account: Optional[Dict[str, Any]] = None
    account_name: Optional[str] = None
    exchange: Optional[str] = None

# @FEAT:event-sse @COMP:model @TYPE:core
@dataclass
class OrderEvent:
    """주문 이벤트 데이터 클래스"""
    event_type: str  # 'order_created', 'order_filled', 'order_cancelled'
    order_id: str
    symbol: str
    strategy_id: int
    user_id: int
    side: str
    quantity: float
    price: float
    status: str
    timestamp: str
    order_type: str = 'LIMIT'  # 주문 타입 (기본값으로 하위 호환성 보장)
    stop_price: float = None  # Stop 가격 (STOP 주문 전용, 선택적 필드)
    # 계좌 정보 (중첩 구조)
    account: Dict[str, Any] = None
    suppress_toast: bool = False  # Suppress individual toast for batch orders

# @FEAT:event-sse @COMP:model @TYPE:core
@dataclass
class OrderBatchEvent:
    """Batch order update event for SSE

    Phase 2: Backend Batch SSE - Aggregate multiple order actions
    """
    summaries: List[Dict[str, Any]]  # [{order_type, created, cancelled}, ...]
    strategy_id: int
    user_id: int
    timestamp: str

# @FEAT:event-sse @COMP:service @TYPE:core
class EventService:
    """실시간 이벤트 서비스 클래스"""

    def __init__(self):
        # (user_id, strategy_id) 튜플을 키로 사용 - defaultdict로 안전성 확보
        self.clients = defaultdict(set)  # Dict[(user_id, strategy_id), set] - 자동 set 생성
        self.event_queues = defaultdict(lambda: deque(maxlen=100))  # 자동 deque 생성
        self.lock = threading.RLock()
        self._cleanup_interval = 60  # 60초마다 정리
        self._last_cleanup = time.time()

        logger.info("이벤트 서비스 초기화 완료 (전략별 격리 모드)")

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def add_client(self, user_id: int, strategy_id: int, client_generator):
        """클라이언트 연결 추가 (전략별)

        Args:
            user_id: 사용자 ID
            strategy_id: 전략 ID (필수)
            client_generator: Queue 객체
        """
        with self.lock:
            key = (user_id, strategy_id)
            # defaultdict이므로 자동으로 set 생성됨
            self.clients[key].add(client_generator)
            logger.info(f"클라이언트 연결 추가 - 사용자: {user_id}, 전략: {strategy_id}, 총: {len(self.clients[key])}개")

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def remove_client(self, user_id: int, strategy_id: int, client_generator):
        """클라이언트 연결 제거 (전략별)

        Args:
            user_id: 사용자 ID
            strategy_id: 전략 ID (필수)
            client_generator: Queue 객체
        """
        with self.lock:
            key = (user_id, strategy_id)
            if key in self.clients:
                self.clients[key].discard(client_generator)
                if not self.clients[key]:
                    del self.clients[key]
                logger.info(f"클라이언트 연결 제거 - 사용자: {user_id}, 전략: {strategy_id}")

    # @FEAT:event-sse @COMP:service @TYPE:core
    def emit_position_event(self, position_event: PositionEvent):
        """포지션 이벤트 발송 (전략별)"""
        try:
            # strategy_id 검증 강화: None 또는 0 이하 차단
            if not hasattr(position_event, 'strategy_id') or position_event.strategy_id is None or position_event.strategy_id <= 0:
                logger.warning(
                    f"포지션 이벤트 검증 실패 - 사용자: {getattr(position_event, 'user_id', 'N/A')}, "
                    f"전략: {getattr(position_event, 'strategy_id', 'N/A')}, "
                    f"사유: 유효하지 않은 strategy_id (None 또는 0 이하)"
                )
                return

            event_data = {
                'type': 'position_update',
                'data': asdict(position_event)
            }

            self._emit_to_user(position_event.user_id, position_event.strategy_id, event_data)
            logger.debug(f"포지션 이벤트 발송: {position_event.event_type} - {position_event.symbol} (전략: {position_event.strategy_id})")

        except Exception as e:
            logger.error(f"포지션 이벤트 발송 실패: {str(e)}")

    # @FEAT:event-sse @COMP:service @TYPE:core
    def emit_order_event(self, order_event: OrderEvent):
        """주문 이벤트 발송 (전략별)"""
        try:
            # strategy_id 검증 강화: None 또는 0 이하 차단
            if not hasattr(order_event, 'strategy_id') or order_event.strategy_id is None or order_event.strategy_id <= 0:
                logger.warning(
                    f"주문 이벤트 검증 실패 - 사용자: {getattr(order_event, 'user_id', 'N/A')}, "
                    f"전략: {getattr(order_event, 'strategy_id', 'N/A')}, "
                    f"사유: 유효하지 않은 strategy_id (None 또는 0 이하)"
                )
                return

            event_data = {
                'type': 'order_update',
                'data': asdict(order_event)
            }

            self._emit_to_user(order_event.user_id, order_event.strategy_id, event_data)
            logger.info(f"📤 주문 이벤트 발송: {order_event.event_type} - {order_event.symbol} (전략: {order_event.strategy_id})")

        except Exception as e:
            logger.error(f"주문 이벤트 발송 실패: {str(e)}")

    # @FEAT:event-sse @COMP:service @TYPE:core
    def emit_order_batch_event(self, batch_event: OrderBatchEvent):
        """Emit batch order update SSE event

        Phase 2: Backend Batch SSE - Send aggregated order events

        Args:
            batch_event: OrderBatchEvent with summaries and metadata

        Example:
            summaries = [
                {'order_type': 'LIMIT', 'created': 5, 'cancelled': 3},
                {'order_type': 'STOP_LIMIT', 'created': 2, 'cancelled': 0}
            ]
        """
        if not batch_event.strategy_id or batch_event.strategy_id == 0:
            logger.warning('Invalid strategy_id - batch SSE blocked')
            return

        if not batch_event.summaries:
            logger.debug('Empty summaries - batch SSE skipped')
            return

        event_data = {
            'type': 'order_batch_update',
            'data': {
                'summaries': batch_event.summaries,
                'timestamp': batch_event.timestamp
            }
        }

        self._emit_to_user(batch_event.user_id, batch_event.strategy_id, event_data)
        logger.info(f'📦 Batch SSE sent - {len(batch_event.summaries)} summaries')

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def _emit_to_user(self, user_id: int, strategy_id: int, event_data: Dict[str, Any]):
        """특정 사용자의 특정 전략에게 이벤트 발송

        Args:
            user_id: 사용자 ID
            strategy_id: 전략 ID (필수)
            event_data: 이벤트 데이터
        """
        with self.lock:
            key = (user_id, strategy_id)

            # 전략 존재 확인 (Phase 3 추가)
            from app.models import Strategy
            strategy = Strategy.query.filter_by(id=strategy_id).first()
            if not strategy or not strategy.is_active:
                logger.warning(
                    f"이벤트 발송 스킵 (전략 없음/비활성) - 사용자: {user_id}, 전략: {strategy_id}"
                )
                return

            # 이벤트 큐에 추가 (defaultdict가 자동으로 deque 생성)
            self.event_queues[key].append(event_data)

            # 해당 전략을 구독 중인 클라이언트에게만 이벤트 전송
            dead_clients = set()

            for client in self.clients.get(key, set()):
                try:
                    client.put(event_data, timeout=1.0)
                except:
                    dead_clients.add(client)

            # 죽은 클라이언트 제거
            if dead_clients:
                self.clients[key] -= dead_clients
                logger.debug(f"사용자 {user_id}, 전략 {strategy_id}의 죽은 클라이언트 {len(dead_clients)}개 제거")

    # @FEAT:event-sse @COMP:service @TYPE:core
    def get_event_stream(self, user_id: int, strategy_id: int):
        """SSE 이벤트 스트림 생성 (전략별)

        Args:
            user_id: 사용자 ID
            strategy_id: 전략 ID (필수)

        Returns:
            Flask Response (SSE 스트림)
        """
        from queue import Queue, Empty

        logger.info(f"🚀 SSE 스트림 생성 시작 - 사용자: {user_id}, 전략: {strategy_id}")
        client_queue = Queue(maxsize=50)

        # @FEAT:event-sse @COMP:service @TYPE:core
        def event_generator():
            """SSE 이벤트 스트림 생성"""
            try:
                logger.info(f"📡 SSE 이벤트 제너레이터 시작 - 사용자: {user_id}, 전략: {strategy_id}")

                # 클라이언트 등록 (전략별)
                self.add_client(user_id, strategy_id, client_queue)

                # 연결 확인 이벤트 전송
                connection_message = {
                    'type': 'connection',
                    'data': {
                        'status': 'connected',
                        'timestamp': datetime.utcnow().isoformat(),
                        'user_id': user_id,
                        'strategy_id': strategy_id  # 전략 ID 추가
                    }
                }
                logger.info(f"📤 연결 확인 메시지 전송 - 사용자: {user_id}, 전략: {strategy_id}")
                connection_msg = self._format_sse_message(connection_message)
                yield connection_msg

                # 즉시 추가 데이터 전송하여 연결 안정화
                yield ": keepalive\n\n"

                # 실시간 이벤트 처리
                while True:
                    try:
                        event = client_queue.get(timeout=10)
                        logger.info(f"📤 실시간 이벤트 전송 - 사용자: {user_id}, 전략: {strategy_id}, 타입: {event.get('type')}")
                        event_msg = self._format_sse_message(event)
                        yield event_msg

                    except Empty:
                        # 타임아웃 시 keep-alive 메시지 전송
                        heartbeat_message = {
                            'type': 'heartbeat',
                            'data': {
                                'timestamp': datetime.utcnow().isoformat()
                            }
                        }
                        logger.debug(f"💓 하트비트 전송 - 사용자: {user_id}, 전략: {strategy_id}")
                        heartbeat_msg = self._format_sse_message(heartbeat_message)
                        yield heartbeat_msg

                        # 주기적 정리
                        self._periodic_cleanup()

            except GeneratorExit:
                logger.debug(f"이벤트 스트림 종료 - 사용자: {user_id}, 전략: {strategy_id}")
            except Exception as e:
                logger.error(f"이벤트 스트림 오류 - 사용자: {user_id}, 전략: {strategy_id}, 오류: {str(e)}")
            finally:
                # 클라이언트 제거 (전략별)
                self.remove_client(user_id, strategy_id, client_queue)

        response = Response(
            event_generator(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Cache-Control',
                'X-Accel-Buffering': 'no'  # Nginx 버퍼링 비활성화
            }
        )
        response.timeout = None  # 타임아웃 비활성화
        return response

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def cleanup_strategy_clients(self, strategy_id: int) -> int:
        """특정 전략의 모든 SSE 클라이언트 정리

        전략 삭제/비활성화 시 호출하여:
        1. force_disconnect 이벤트를 모든 클라이언트에게 발송
        2. 해당 전략의 모든 클라이언트 연결 제거
        3. 이벤트 큐 정리

        Args:
            strategy_id: 정리할 전략 ID

        Returns:
            int: 정리된 클라이언트 수
        """
        cleaned_count = 0

        with self.lock:
            # 해당 전략의 모든 (user_id, strategy_id) 키 찾기
            keys_to_remove = [
                key for key in self.clients.keys()
                if key[1] == strategy_id  # key[1]은 strategy_id
            ]

            logger.info(f"🧹 전략 {strategy_id} SSE 정리 시작 - 대상 키: {len(keys_to_remove)}개")

            for key in keys_to_remove:
                user_id, strat_id = key
                clients = self.clients.get(key, set()).copy()  # 복사본으로 순회

                # 각 클라이언트에게 force_disconnect 이벤트 전송
                disconnect_event = {
                    'type': 'force_disconnect',
                    'data': {
                        'reason': 'strategy_deleted',
                        'message': '전략이 삭제되었습니다. 연결을 종료합니다.',
                        'strategy_id': strategy_id,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                }

                for client in clients:
                    try:
                        client.put(disconnect_event, timeout=0.5)
                        cleaned_count += 1
                        logger.debug(f"강제 종료 이벤트 전송 - 사용자: {user_id}, 전략: {strat_id}")
                    except Exception as e:
                        logger.warning(f"강제 종료 이벤트 전송 실패 - 사용자: {user_id}, 오류: {str(e)}")

                # 클라이언트 및 큐 제거
                if key in self.clients:
                    del self.clients[key]
                if key in self.event_queues:
                    del self.event_queues[key]

                logger.info(f"전략 {strategy_id} 클라이언트 정리 완료 - 사용자: {user_id}, 클라이언트 수: {len(clients)}")

        logger.info(f"✅ 전략 {strategy_id} SSE 정리 완료 - 총 {cleaned_count}개 클라이언트 정리됨")
        return cleaned_count

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def disconnect_client(self, user_id: int, strategy_id: int, reason: str = 'permission_revoked') -> int:
        """특정 사용자의 특정 전략 SSE 클라이언트 강제 종료

        권한 변경 시 호출하여:
        1. force_disconnect 이벤트를 해당 클라이언트에게 발송
        2. (user_id, strategy_id) 클라이언트 연결 제거
        3. 이벤트 큐 정리

        Args:
            user_id: 사용자 ID
            strategy_id: 전략 ID
            reason: 종료 사유 ('permission_revoked', 'account_deactivated' 등)

        Returns:
            int: 정리된 클라이언트 수
        """
        cleaned_count = 0
        key = (user_id, strategy_id)

        with self.lock:
            clients = self.clients.get(key, set()).copy()

            if not clients:
                logger.debug(f"강제 종료 대상 없음 - 사용자: {user_id}, 전략: {strategy_id}")
                return 0

            logger.info(f"🚫 SSE 강제 종료 시작 - 사용자: {user_id}, 전략: {strategy_id}, 사유: {reason}")

            # force_disconnect 이벤트 생성
            disconnect_event = {
                'type': 'force_disconnect',
                'data': {
                    'reason': reason,
                    'message': self._get_disconnect_message(reason),
                    'strategy_id': strategy_id,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }

            # 각 클라이언트에게 이벤트 전송
            for client in clients:
                try:
                    client.put(disconnect_event, timeout=0.5)
                    cleaned_count += 1
                    logger.debug(f"강제 종료 이벤트 전송 - 사용자: {user_id}, 전략: {strategy_id}")
                except Exception as e:
                    logger.warning(f"강제 종료 이벤트 전송 실패 - 사용자: {user_id}, 오류: {str(e)}")

            # 클라이언트 및 큐 제거
            if key in self.clients:
                del self.clients[key]
            if key in self.event_queues:
                del self.event_queues[key]

            logger.info(f"✅ SSE 강제 종료 완료 - 사용자: {user_id}, 전략: {strategy_id}, 클라이언트: {cleaned_count}개")

        return cleaned_count

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def _get_disconnect_message(self, reason: str) -> str:
        """종료 사유에 따른 메시지 반환"""
        messages = {
            'permission_revoked': '전략 접근 권한이 제거되었습니다. 연결을 종료합니다.',
            'account_deactivated': '계정이 비활성화되었습니다. 연결을 종료합니다.',
            'strategy_deleted': '전략이 삭제되었습니다. 연결을 종료합니다.',
            'session_expired': '세션이 만료되었습니다. 다시 로그인해주세요.'
        }
        return messages.get(reason, '연결이 종료되었습니다.')

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def _format_sse_message(self, data: Dict[str, Any]) -> str:
        """SSE 메시지 포맷팅"""
        try:
            json_data = json.dumps(data.get('data', data), ensure_ascii=False)

            # Extract event type if available
            event_type = data.get('type', None)

            # Format SSE message with event type
            if event_type:
                return f"event: {event_type}\ndata: {json_data}\n\n"
            else:
                return f"data: {json_data}\n\n"
        except Exception as e:
            logger.error(f"SSE 메시지 포맷팅 실패: {str(e)}")
            return f"data: {{}}\n\n"

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def _periodic_cleanup(self):
        """주기적으로 죽은 연결 정리"""
        current_time = time.time()

        if current_time - self._last_cleanup > self._cleanup_interval:
            with self.lock:
                # 빈 클라이언트 집합 제거
                empty_users = [user_id for user_id, clients in self.clients.items() if not clients]
                for user_id in empty_users:
                    del self.clients[user_id]

                # 오래된 이벤트 큐 정리
                old_users = [user_id for user_id in self.event_queues.keys() if user_id not in self.clients]
                for user_id in old_users:
                    del self.event_queues[user_id]

                if empty_users or old_users:
                    logger.info(f"정리 완료: 빈 사용자 {len(empty_users)}개, 오래된 큐 {len(old_users)}개 제거")

            self._last_cleanup = current_time

    # @FEAT:event-sse @COMP:service @TYPE:helper
    def get_statistics(self) -> Dict[str, Any]:
        """서비스 통계 조회"""
        with self.lock:
            return {
                'total_users': len(self.clients),
                'total_connections': sum(len(clients) for clients in self.clients.values()),
                'queued_events': sum(len(queue) for queue in self.event_queues.values()),
                'users_with_events': len(self.event_queues),
                'timestamp': datetime.utcnow().isoformat()
            }

# 전역 인스턴스
event_service = EventService()
