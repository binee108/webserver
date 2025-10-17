/**
 * Server-Sent Events (SSE) Manager
 * 서버로부터 실시간 이벤트를 수신하고 관리하는 모듈
 */

class SSEManager {
    constructor(options = {}) {
        // Configuration
        this.url = options.url || '/api/events/stream';
        this.strategyId = options.strategyId || null;  // NEW: strategyId option for SSE connection
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
        this.reconnectInterval = options.reconnectInterval || 3000;
        this.heartbeatTimeout = options.heartbeatTimeout || 60000; // 60 seconds
        this.skipAuthCheck = options.skipAuthCheck || false; // Option to skip auth check
        
        // State
        this.eventSource = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.lastHeartbeat = null;
        this.heartbeatTimer = null;
        this.loginCheckInProgress = false;
        
        // Get utilities from RealtimeCore
        this.logger = window.RealtimeCore ? window.RealtimeCore.logger : console;
        this.eventBus = window.RealtimeCore ? window.RealtimeCore.eventBus : null;
        
        // Connection manager
        this.connectionManager = new (window.RealtimeCore?.ConnectionManager || function(){})('SSE');
        
        // Event handlers map
        this.eventHandlers = new Map();
        
        // Register default event handlers
        this.registerDefaultHandlers();
    }
    
    /**
     * Register default event handlers
     */
    registerDefaultHandlers() {
        // Heartbeat handler
        this.on('heartbeat', (data) => {
            this.handleHeartbeat(data);
        });

        // Connection handler
        this.on('connection', (data) => {
            this.logger.info('SSE connection confirmed:', data);
            if (this.eventBus) {
                this.eventBus.emit('sse-connected', data);
            }
        });

        // Force disconnect handler
        this.on('force_disconnect', (data) => {
            this.handleForceDisconnect(data);
        });

        // Error handler
        this.on('error', (data) => {
            this.logger.error('SSE error event:', data);
            if (this.eventBus) {
                this.eventBus.emit('sse-error', data);
            }
        });
    }
    
    /**
     * Check login status before connecting
     */
    async checkLoginStatus() {
        if (this.loginCheckInProgress) {
            this.logger.info('Login check already in progress, skipping...');
            return false;
        }
        
        this.loginCheckInProgress = true;
        
        try {
            this.logger.info('🔍 로그인 상태 확인 시작...');
            
            const response = await fetch('/api/auth/check', {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (!response.ok) {
                // If auth check endpoint doesn't exist, assume logged in
                if (response.status === 404) {
                    this.logger.warn('Auth check endpoint not found, assuming logged in');
                    return true;
                }
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            const isLoggedIn = data.logged_in || data.is_authenticated || false;
            
            this.logger.info(`🔍 로그인 상태 확인 완료: ${isLoggedIn}`);
            return isLoggedIn;
            
        } catch (error) {
            this.logger.error('로그인 상태 확인 실패:', error);
            // On error, try to connect anyway (positions page likely requires auth already)
            this.logger.warn('Proceeding with SSE connection despite auth check failure');
            return true;
        } finally {
            this.loginCheckInProgress = false;
        }
    }
    
    /**
     * Connect to SSE endpoint
     */
    async connect() {
        // Check if already connected
        if (this.eventSource && this.eventSource.readyState === EventSource.OPEN) {
            this.logger.warn('SSE already connected');
            return;
        }
        
        // Check login status first (unless skipped)
        if (!this.skipAuthCheck) {
            const isLoggedIn = await this.checkLoginStatus();
            if (!isLoggedIn) {
                this.logger.warn('User not logged in, skipping SSE connection');
                this.connectionManager.setStatus(window.RealtimeCore?.ConnectionStatus.DISCONNECTED);
                return;
            }
        } else {
            this.logger.info('Skipping auth check, proceeding with SSE connection');
        }
        
        try {
            this.logger.info('SSE 연결 시작...');
            this.connectionManager.setStatus(window.RealtimeCore?.ConnectionStatus.CONNECTING);

            // Build URL with strategy_id query parameter
            let fullUrl = this.url.startsWith('http') ? this.url : `${window.location.origin}${this.url}`;

            if (this.strategyId) {
                const separator = fullUrl.includes('?') ? '&' : '?';
                fullUrl += `${separator}strategy_id=${this.strategyId}`;
                this.logger.info('SSE URL with strategy_id:', fullUrl);
            } else {
                this.logger.warn('⚠️ No strategyId provided - backend may reject connection');
                this.logger.info('SSE URL:', fullUrl);
            }

            this.eventSource = new EventSource(fullUrl);
            this.logger.info('EventSource 생성됨 - readyState:', this.eventSource.readyState);

            // Set up event handlers
            this.setupEventHandlers();

        } catch (error) {
            this.logger.error('SSE 연결 실패:', error);
            this.connectionManager.setStatus(window.RealtimeCore?.ConnectionStatus.ERROR);
            this.handleReconnect();
        }
    }
    
    /**
     * Set up EventSource event handlers
     */
    setupEventHandlers() {
        if (!this.eventSource) return;
        
        // Connection opened
        this.eventSource.onopen = (event) => {
            this.logger.info('🟢 SSE 연결 성공!');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.connectionManager.setStatus(window.RealtimeCore?.ConnectionStatus.CONNECTED);
            
            // Start heartbeat monitoring
            this.startHeartbeatMonitor();
            
            // Emit connected event
            if (this.eventBus) {
                this.eventBus.emit('sse-connected', { timestamp: Date.now() });
            }
        };
        
        // Message received
        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (error) {
                this.logger.error('Failed to parse SSE message:', error, event.data);
            }
        };
        
        // Custom event types
        const eventTypes = [
            'position_update',
            'order_update',
            'heartbeat',
            'connection',
            'error',
            'trade_update',
            'balance_update',
            'strategy_update',
            'force_disconnect'
        ];
        
        eventTypes.forEach(eventType => {
            this.eventSource.addEventListener(eventType, (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.logger.info(`🎯 SSE 이벤트 처리: ${eventType}`, data);
                    this.handleEvent(eventType, data);
                } catch (error) {
                    this.logger.error(`Failed to handle ${eventType} event:`, error);
                }
            });
        });
        
        // Error handling
        this.eventSource.onerror = (error) => {
            this.logger.error('❌ SSE 연결 오류:', error);
            this.isConnected = false;
            this.connectionManager.setStatus(window.RealtimeCore?.ConnectionStatus.ERROR);
            
            // EventSource automatically reconnects, but we handle it manually
            if (this.eventSource.readyState === EventSource.CLOSED) {
                this.handleReconnect();
            }
        };
    }
    
    /**
     * Handle incoming message
     */
    handleMessage(data) {
        // Check if data has event_type field
        if (data.event_type) {
            this.handleEvent(data.event_type, data);
        } else if (data.type) {
            this.handleEvent(data.type, data);
        } else {
            this.logger.warn('Unknown message format:', data);
        }
    }
    
    /**
     * Handle specific event type
     */
    handleEvent(eventType, data) {
        // Update heartbeat for any event
        this.lastHeartbeat = Date.now();
        
        // Call registered handlers
        const handlers = this.eventHandlers.get(eventType);
        if (handlers && handlers.size > 0) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    this.logger.error(`Error in handler for ${eventType}:`, error);
                }
            });
        }
        
        // Emit to event bus
        if (this.eventBus) {
            this.eventBus.emit(`sse:${eventType}`, data);
        }
    }
    
    /**
     * Register event handler
     */
    on(eventType, handler) {
        if (!this.eventHandlers.has(eventType)) {
            this.eventHandlers.set(eventType, new Set());
        }
        this.eventHandlers.get(eventType).add(handler);
        return this; // For chaining
    }
    
    /**
     * Unregister event handler
     */
    off(eventType, handler) {
        const handlers = this.eventHandlers.get(eventType);
        if (handlers) {
            handlers.delete(handler);
        }
        return this;
    }
    
    /**
     * Handle heartbeat event
     */
    handleHeartbeat(data) {
        this.logger.debug('💓 Heartbeat received:', data);
        this.lastHeartbeat = Date.now();

        // Reset heartbeat timer
        this.resetHeartbeatTimer();
    }

    /**
     * Handle force_disconnect event from server
     */
    handleForceDisconnect(data) {
        this.logger.warn('🚫 SSE 강제 종료:', data);

        const reason = data.data?.reason || data.reason || 'unknown';
        const message = data.data?.message || data.message || '연결이 종료되었습니다.';
        const strategyId = data.data?.strategy_id || data.strategy_id;

        // 사용자에게 알림 표시
        if (window.showToast) {
            window.showToast(message, 'warning', 5000);
        } else {
            alert(message);
        }

        // EventBus로 이벤트 발행
        if (this.eventBus) {
            this.eventBus.emit('sse-force-disconnect', { reason, message, strategyId });
        }

        // 로그에 이유별 상세 정보 기록
        switch (reason) {
            case 'strategy_deleted':
                this.logger.error('전략이 삭제되어 연결이 종료되었습니다.');
                break;
            case 'permission_revoked':
                this.logger.error('전략 접근 권한이 제거되어 연결이 종료되었습니다.');
                break;
            case 'account_deactivated':
                this.logger.error('계정이 비활성화되어 연결이 종료되었습니다.');
                break;
            case 'session_expired':
                this.logger.error('세션이 만료되어 연결이 종료되었습니다.');
                window.location.href = '/login';  // 로그인 페이지로 리다이렉트
                return;
            default:
                this.logger.warn(`알 수 없는 이유로 연결이 종료되었습니다: ${reason}`);
        }

        // SSE 연결 종료
        this.disconnect();

        // 전략 삭제 또는 권한 제거 시 전략 목록 페이지로 리다이렉트
        if (reason === 'strategy_deleted' || reason === 'permission_revoked') {
            setTimeout(() => {
                this.logger.info('Redirecting to strategies page...');
                window.location.href = '/strategies';
            }, 3000);  // 3초 후 리다이렉트 (사용자가 메시지 읽을 시간)
        }
    }

    /**
     * Start heartbeat monitoring
     */
    startHeartbeatMonitor() {
        this.lastHeartbeat = Date.now();
        this.resetHeartbeatTimer();
    }
    
    /**
     * Reset heartbeat timer
     */
    resetHeartbeatTimer() {
        // Clear existing timer
        if (this.heartbeatTimer) {
            clearTimeout(this.heartbeatTimer);
        }
        
        // Set new timer
        this.heartbeatTimer = setTimeout(() => {
            const timeSinceLastHeartbeat = Date.now() - this.lastHeartbeat;
            if (timeSinceLastHeartbeat > this.heartbeatTimeout) {
                this.logger.warn('Heartbeat timeout, reconnecting...');
                this.reconnect();
            }
        }, this.heartbeatTimeout);
    }
    
    /**
     * Stop heartbeat monitoring
     */
    stopHeartbeatMonitor() {
        if (this.heartbeatTimer) {
            clearTimeout(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }
    
    /**
     * Handle reconnection
     */
    handleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            this.logger.error('Max reconnection attempts reached');
            this.connectionManager.setStatus(window.RealtimeCore?.ConnectionStatus.DISCONNECTED);
            
            // Emit disconnected event
            if (this.eventBus) {
                this.eventBus.emit('sse-disconnected', { 
                    reason: 'max_attempts_reached',
                    attempts: this.reconnectAttempts 
                });
            }
            return;
        }
        
        this.reconnectAttempts++;
        this.connectionManager.setStatus(window.RealtimeCore?.ConnectionStatus.RECONNECTING);
        
        const delay = this.reconnectInterval * Math.min(this.reconnectAttempts, 3);
        this.logger.info(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        
        setTimeout(() => {
            this.connect();
        }, delay);
    }
    
    /**
     * Reconnect to SSE
     */
    reconnect() {
        this.disconnect();
        this.connect();
    }
    
    /**
     * Disconnect from SSE
     */
    disconnect() {
        this.logger.info('Disconnecting SSE...');
        
        // Stop heartbeat monitoring
        this.stopHeartbeatMonitor();
        
        // Close EventSource
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        this.isConnected = false;
        this.connectionManager.setStatus(window.RealtimeCore?.ConnectionStatus.DISCONNECTED);
        
        // Emit disconnected event
        if (this.eventBus) {
            this.eventBus.emit('sse-disconnected', { reason: 'manual' });
        }
    }
    
    /**
     * Get connection status
     */
    getStatus() {
        return {
            connected: this.isConnected,
            readyState: this.eventSource ? this.eventSource.readyState : null,
            reconnectAttempts: this.reconnectAttempts,
            lastHeartbeat: this.lastHeartbeat,
            url: this.url
        };
    }
    
    /**
     * Destroy the manager
     */
    destroy() {
        this.disconnect();
        this.eventHandlers.clear();
    }
}

// ========================================
// Global SSE Manager Instance
// ========================================

let globalSSEManager = null;

/**
 * Get or create global SSE manager instance
 */
function getSSEManager(options = {}) {
    if (!globalSSEManager) {
        globalSSEManager = new SSEManager(options);
    }
    return globalSSEManager;
}

/**
 * Initialize SSE manager
 */
function initializeSSE(options = {}) {
    const manager = getSSEManager(options);
    manager.connect();
    return manager;
}

/**
 * Disconnect SSE manager
 */
function disconnectSSE() {
    if (globalSSEManager) {
        globalSSEManager.disconnect();
    }
}

// ========================================
// Export to Global Scope
// ========================================

window.SSEManager = SSEManager;
window.getSSEManager = getSSEManager;
window.initializeSSE = initializeSSE;
window.disconnectSSE = disconnectSSE;