/**
 * 실시간 포지션/주문 업데이트 관리자
 * Server-Sent Events (SSE)를 사용하여 서버로부터 실시간 이벤트 수신
 */

class RealtimeUpdatesManager {
    constructor(options = {}) {
        this.eventSource = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
        this.reconnectInterval = options.reconnectInterval || 3000;
        this.reconnectTimer = null;
        
        // 이벤트 핸들러들
        this.eventHandlers = {
            position_update: [],
            order_update: [],
            connection: [],
            error: [],
            heartbeat: []
        };
        
        // 로깅
        this.logger = window.logger || console;
        
        this.logger.info('RealtimeUpdatesManager 초기화 완료');
    }
    
    /**
     * SSE 연결 시작
     */
    connect() {
        if (this.eventSource && this.eventSource.readyState !== EventSource.CLOSED) {
            this.logger.warn('이미 연결되어 있거나 연결 중입니다.');
            return;
        }
        
        try {
            this.logger.info('SSE 연결 시작...');
            
            this.eventSource = new EventSource('/api/events/stream');
            
            // 연결 성공
            this.eventSource.onopen = (event) => {
                this.logger.success('SSE 연결 성공');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.clearReconnectTimer();
                this.updateConnectionStatus(true);
            };
            
            // 메시지 수신
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleEvent(data);
                } catch (error) {
                    this.logger.error('이벤트 데이터 파싱 실패:', error);
                }
            };
            
            // 연결 오류
            this.eventSource.onerror = (event) => {
                this.logger.error('SSE 연결 오류:', event);
                this.isConnected = false;
                this.updateConnectionStatus(false);
                
                if (this.eventSource.readyState === EventSource.CLOSED) {
                    this.scheduleReconnect();
                }
            };
            
        } catch (error) {
            this.logger.error('SSE 연결 실패:', error);
            this.scheduleReconnect();
        }
    }
    
    /**
     * SSE 연결 종료
     */
    disconnect() {
        this.logger.info('SSE 연결 종료 요청');
        
        this.clearReconnectTimer();
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.updateConnectionStatus(false);
    }
    
    /**
     * 이벤트 처리
     */
    handleEvent(eventData) {
        const { type, data } = eventData;
        
        this.logger.debug(`이벤트 수신: ${type}`, data);
        
        switch (type) {
            case 'connection':
                this.handleConnectionEvent(data);
                break;
                
            case 'position_update':
                this.handlePositionEvent(data);
                break;
                
            case 'order_update':
                this.handleOrderEvent(data);
                break;
                
            case 'heartbeat':
                this.handleHeartbeat(data);
                break;
                
            case 'error':
                this.handleErrorEvent(data);
                break;
                
            default:
                this.logger.warn('알 수 없는 이벤트 타입:', type);
        }
        
        // 등록된 핸들러 실행
        this.executeHandlers(type, data);
    }
    
    /**
     * 연결 이벤트 처리
     */
    handleConnectionEvent(data) {
        this.logger.info('연결 상태 이벤트:', data);
        
        if (data.status === 'connected') {
            this.updateConnectionStatus(true);
        }
    }
    
    /**
     * 포지션 업데이트 이벤트 처리
     */
    handlePositionEvent(data) {
        this.logger.debug('포지션 이벤트:', data);
        
        try {
            const { event_type, position_id, symbol, quantity, entry_price } = data;
            
            switch (event_type) {
                case 'position_updated':
                    this.updatePositionInTable(position_id, {
                        quantity: quantity,
                        entry_price: entry_price,
                        symbol: symbol
                    });
                    this.showNotification(`포지션 업데이트: ${symbol}`, 'info');
                    break;
                    
                case 'position_closed':
                    this.removePositionFromTable(position_id);
                    this.showNotification(`포지션 청산: ${symbol}`, 'success');
                    break;
            }
            
        } catch (error) {
            this.logger.error('포지션 이벤트 처리 실패:', error);
        }
    }
    
    /**
     * 주문 업데이트 이벤트 처리
     */
    handleOrderEvent(data) {
        this.logger.debug('주문 이벤트:', data);
        
        try {
            const { event_type, order_id, symbol, side, quantity, price, status } = data;
            
            switch (event_type) {
                case 'order_created':
                    this.addOrderToTable({
                        order_id: order_id,
                        symbol: symbol,
                        side: side,
                        quantity: quantity,
                        price: price,
                        status: status
                    });
                    this.showNotification(`새 주문: ${symbol} ${side.toUpperCase()}`, 'info');
                    break;
                    
                case 'order_filled':
                    this.removeOrderFromTable(order_id);
                    this.showNotification(`주문 체결: ${symbol} ${side.toUpperCase()}`, 'success');
                    break;
                    
                case 'order_cancelled':
                    this.removeOrderFromTable(order_id);
                    this.showNotification(`주문 취소: ${symbol} ${side.toUpperCase()}`, 'warning');
                    break;
            }
            
        } catch (error) {
            this.logger.error('주문 이벤트 처리 실패:', error);
        }
    }
    
    /**
     * 하트비트 처리
     */
    handleHeartbeat(data) {
        this.logger.debug('하트비트 수신:', data.timestamp);
        // 연결 상태 유지 확인
        this.updateConnectionStatus(true);
    }
    
    /**
     * 오류 이벤트 처리
     */
    handleErrorEvent(data) {
        this.logger.error('서버 오류 이벤트:', data);
        this.showNotification(`서버 오류: ${data.message || '알 수 없는 오류'}`, 'error');
    }
    
    /**
     * 재연결 스케줄링
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            this.logger.error(`재연결 최대 시도 횟수(${this.maxReconnectAttempts})에 도달했습니다.`);
            this.showNotification('실시간 업데이트 연결에 실패했습니다. 페이지를 새로고침해주세요.', 'error');
            return;
        }
        
        this.reconnectAttempts++;
        this.logger.info(`${this.reconnectInterval/1000}초 후 재연결 시도 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        this.reconnectTimer = setTimeout(() => {
            this.connect();
        }, this.reconnectInterval);
    }
    
    /**
     * 재연결 타이머 클리어
     */
    clearReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }
    
    /**
     * 포지션 테이블 업데이트
     */
    updatePositionInTable(positionId, data) {
        const row = document.querySelector(`tr[data-position-id="${positionId}"]`);
        if (!row) {
            this.logger.warn(`포지션 ID ${positionId}에 해당하는 행을 찾을 수 없습니다.`);
            return;
        }
        
        // 수량 업데이트
        const quantityCell = row.querySelector('.position-quantity');
        if (quantityCell) {
            quantityCell.textContent = parseFloat(Math.abs(data.quantity)).toLocaleString();
        }
        
        // 진입가 업데이트
        const entryPriceCell = row.querySelector('.entry-price');
        if (entryPriceCell) {
            entryPriceCell.textContent = `$${parseFloat(data.entry_price).toFixed(4)}`;
        }
        
        // 포지션 방향 업데이트
        const directionCell = row.querySelector('.position-direction');
        if (directionCell) {
            const isLong = data.quantity > 0;
            directionCell.innerHTML = isLong 
                ? '<span class="badge badge-success">롱</span>'
                : '<span class="badge badge-error">숏</span>';
        }
        
        // 행 하이라이트
        this.highlightRow(row, 'updated');
    }
    
    /**
     * 포지션 테이블에서 제거
     */
    removePositionFromTable(positionId) {
        const row = document.querySelector(`tr[data-position-id="${positionId}"]`);
        if (row) {
            this.highlightRow(row, 'removed', () => {
                row.remove();
                this.checkEmptyPositions();
            });
        }
    }
    
    /**
     * 주문 테이블에 추가
     */
    addOrderToTable(orderData) {
        // 이미 존재하는 주문인지 확인
        const existingRow = document.querySelector(`tr[data-order-id="${orderData.order_id}"]`);
        if (existingRow) {
            return;
        }
        
        // 주문 목록을 새로 로드하는 것이 더 안전
        setTimeout(() => {
            if (typeof refreshOpenOrders === 'function') {
                refreshOpenOrders();
            }
        }, 500);
    }
    
    /**
     * 주문 테이블에서 제거
     */
    removeOrderFromTable(orderId) {
        const row = document.querySelector(`tr[data-order-id="${orderId}"]`);
        if (row) {
            this.highlightRow(row, 'removed', () => {
                row.remove();
                this.updateOpenOrdersCount();
            });
        }
    }
    
    /**
     * 행 하이라이트 효과
     */
    highlightRow(row, type, callback) {
        const className = type === 'updated' ? 'realtime-updated' : 'realtime-removed';
        
        row.classList.add(className);
        
        setTimeout(() => {
            row.classList.remove(className);
            if (callback) callback();
        }, type === 'removed' ? 1500 : 1000);
    }
    
    /**
     * 빈 포지션 상태 확인
     */
    checkEmptyPositions() {
        const positionRows = document.querySelectorAll('tr[data-position-id]');
        if (positionRows.length === 0) {
            // 포지션이 모두 없어진 경우 페이지 새로고침 또는 빈 상태 표시
            setTimeout(() => {
                if (typeof refreshPositions === 'function') {
                    refreshPositions();
                }
            }, 1000);
        }
    }
    
    /**
     * 열린 주문 개수 업데이트
     */
    updateOpenOrdersCount() {
        const rows = document.querySelectorAll('tr[data-order-id]');
        const count = rows.length;
        
        const countElement = document.getElementById('open-orders-count');
        if (countElement) {
            countElement.textContent = count + '개';
            countElement.className = count > 0 ? 'ml-2 badge badge-warning' : 'ml-2 badge badge-secondary';
        }
    }
    
    /**
     * 연결 상태 업데이트
     */
    updateConnectionStatus(connected) {
        // 실시간 연결 상태 표시기 업데이트
        const indicator = document.getElementById('realtime-indicator');
        if (indicator) {
            if (connected) {
                indicator.className = 'ml-2 badge badge-success realtime-indicator';
                indicator.textContent = '실시간 연결됨';
            } else {
                indicator.className = 'ml-2 badge badge-warning realtime-indicator';
                indicator.textContent = '연결 시도 중';
            }
        }
    }
    
    /**
     * 알림 표시
     */
    showNotification(message, type = 'info') {
        // 간단한 토스트 알림 (기존 알림 시스템이 있다면 그것을 사용)
        if (typeof showToast === 'function') {
            showToast(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
    
    /**
     * 이벤트 핸들러 등록
     */
    on(eventType, handler) {
        if (this.eventHandlers[eventType]) {
            this.eventHandlers[eventType].push(handler);
        }
    }
    
    /**
     * 이벤트 핸들러 제거
     */
    off(eventType, handler) {
        if (this.eventHandlers[eventType]) {
            const index = this.eventHandlers[eventType].indexOf(handler);
            if (index > -1) {
                this.eventHandlers[eventType].splice(index, 1);
            }
        }
    }
    
    /**
     * 등록된 핸들러 실행
     */
    executeHandlers(eventType, data) {
        if (this.eventHandlers[eventType]) {
            this.eventHandlers[eventType].forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    this.logger.error(`이벤트 핸들러 실행 실패 (${eventType}):`, error);
                }
            });
        }
    }
    
    /**
     * 연결 상태 조회
     */
    getConnectionStatus() {
        return {
            connected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts,
            maxReconnectAttempts: this.maxReconnectAttempts
        };
    }
}

// 전역 인스턴스 (포지션 페이지에서 사용)
let realtimeUpdates = null;

/**
 * 실시간 업데이트 초기화
 */
function initializeRealtimeUpdates() {
    if (realtimeUpdates) {
        realtimeUpdates.disconnect();
    }
    
    realtimeUpdates = new RealtimeUpdatesManager({
        maxReconnectAttempts: 5,
        reconnectInterval: 3000
    });
    
    // 연결 시작
    realtimeUpdates.connect();
    
    return realtimeUpdates;
}

/**
 * 실시간 업데이트 종료
 */
function disconnectRealtimeUpdates() {
    if (realtimeUpdates) {
        realtimeUpdates.disconnect();
        realtimeUpdates = null;
    }
}

/**
 * 실시간 업데이트 매니저 조회
 */
function getRealtimeUpdatesManager() {
    return realtimeUpdates;
} 