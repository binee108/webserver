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

@dataclass
class PositionEvent:
    """포지션 이벤트 데이터 클래스"""
    event_type: str  # 'position_updated', 'position_closed'
    position_id: int
    symbol: str
    strategy_id: int
    user_id: int
    quantity: float
    entry_price: float
    timestamp: str
    # 계좌 정보 (중첩 구조)
    account: Dict[str, Any] = None

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
    # 계좌 정보 (중첩 구조)
    account: Dict[str, Any] = None

class EventService:
    """실시간 이벤트 서비스 클래스"""
    
    def __init__(self):
        self.clients = defaultdict(set)  # user_id -> set of client connections
        self.event_queues = defaultdict(lambda: deque(maxlen=100))  # user_id -> event queue
        self.lock = threading.RLock()
        self._cleanup_interval = 60  # 60초마다 정리
        self._last_cleanup = time.time()
        
        logger.info("이벤트 서비스 초기화 완료")
    
    def add_client(self, user_id: int, client_generator):
        """클라이언트 연결 추가"""
        with self.lock:
            self.clients[user_id].add(client_generator)
            logger.info(f"사용자 {user_id} 클라이언트 연결 추가 (총 {len(self.clients[user_id])}개)")
    
    def remove_client(self, user_id: int, client_generator):
        """클라이언트 연결 제거"""
        with self.lock:
            self.clients[user_id].discard(client_generator)
            if not self.clients[user_id]:
                del self.clients[user_id]
            logger.info(f"사용자 {user_id} 클라이언트 연결 제거")
    
    def emit_position_event(self, position_event: PositionEvent):
        """포지션 이벤트 발송"""
        try:
            event_data = {
                'type': 'position_update',
                'data': asdict(position_event)
            }
            
            self._emit_to_user(position_event.user_id, event_data)
            logger.debug(f"포지션 이벤트 발송: {position_event.event_type} - {position_event.symbol}")
            
        except Exception as e:
            logger.error(f"포지션 이벤트 발송 실패: {str(e)}")
    
    def emit_order_event(self, order_event: OrderEvent):
        """주문 이벤트 발송"""
        try:
            event_data = {
                'type': 'order_update',
                'data': asdict(order_event)
            }
            
            self._emit_to_user(order_event.user_id, event_data)
            logger.debug(f"주문 이벤트 발송: {order_event.event_type} - {order_event.symbol}")
            
        except Exception as e:
            logger.error(f"주문 이벤트 발송 실패: {str(e)}")
    
    def _emit_to_user(self, user_id: int, event_data: Dict[str, Any]):
        """특정 사용자에게 이벤트 발송"""
        with self.lock:
            # 이벤트 큐에 추가
            self.event_queues[user_id].append(event_data)
            
            # 연결된 클라이언트들에게 이벤트 전송
            dead_clients = set()
            
            for client in self.clients.get(user_id, set()):
                try:
                    client.put(event_data, timeout=1.0)  # 1초 타임아웃 추가
                except:
                    dead_clients.add(client)
            
            # 죽은 클라이언트 제거
            if dead_clients:
                self.clients[user_id] -= dead_clients
                logger.debug(f"사용자 {user_id}의 죽은 클라이언트 {len(dead_clients)}개 제거")
    
    def get_event_stream(self, user_id: int):
        """SSE 이벤트 스트림 생성"""
        from queue import Queue, Empty
        
        logger.info(f"🚀 SSE 스트림 생성 시작 - 사용자: {user_id}")
        client_queue = Queue(maxsize=50)
        
        def event_generator():
            try:
                logger.info(f"📡 SSE 이벤트 제너레이터 시작 - 사용자: {user_id}")
                
                # 클라이언트 등록
                self.add_client(user_id, client_queue)
                
                # 연결 확인 이벤트 전송
                connection_message = {
                    'type': 'connection',
                    'data': {
                        'status': 'connected',
                        'timestamp': datetime.utcnow().isoformat(),
                        'user_id': user_id
                    }
                }
                logger.info(f"📤 연결 확인 메시지 전송 - 사용자: {user_id}")
                connection_msg = self._format_sse_message(connection_message)
                logger.debug(f"연결 메시지 내용: {connection_msg.strip()}")
                yield connection_msg
                
                # 즉시 추가 데이터 전송하여 연결 안정화
                yield ": keepalive\n\n"  # SSE 주석 (브라우저에서 무시됨)
                
                # 새로운 연결에서는 과거 이벤트를 재전송하지 않음
                # 실시간 이벤트만 전송하여 중복 처리 방지
                
                # 실시간 이벤트 처리
                while True:
                    try:
                        # 10초 타임아웃으로 이벤트 대기 (응답성 향상)
                        event = client_queue.get(timeout=10)
                        logger.info(f"📤 실시간 이벤트 전송 - 사용자: {user_id}, 타입: {event.get('type')}")
                        event_msg = self._format_sse_message(event)
                        logger.debug(f"이벤트 메시지 내용: {event_msg.strip()}")
                        yield event_msg
                        
                    except Empty:
                        # 타임아웃 시 keep-alive 메시지 전송
                        heartbeat_message = {
                            'type': 'heartbeat',
                            'data': {
                                'timestamp': datetime.utcnow().isoformat()
                            }
                        }
                        logger.debug(f"💓 하트비트 전송 - 사용자: {user_id}")
                        heartbeat_msg = self._format_sse_message(heartbeat_message)
                        yield heartbeat_msg
                        
                        # 주기적 정리
                        self._periodic_cleanup()
                        
            except GeneratorExit:
                logger.debug(f"사용자 {user_id} 이벤트 스트림 종료")
            except Exception as e:
                logger.error(f"사용자 {user_id} 이벤트 스트림 오류: {str(e)}")
            finally:
                # 클라이언트 제거
                self.remove_client(user_id, client_queue)
        
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