/**
 * Real-time Open Orders Manager
 * 열린 주문 관련 실시간 업데이트를 처리하는 모듈
 * SSE를 통한 주문 이벤트 처리 및 DOM 업데이트
 */

class RealtimeOpenOrdersManager {
    constructor() {
        // Get utilities from RealtimeCore
        this.logger = window.RealtimeCore ? window.RealtimeCore.logger : console;
        this.DOM = window.RealtimeCore ? window.RealtimeCore.DOM : null;
        this.format = window.RealtimeCore ? window.RealtimeCore.format : null;
        this.eventBus = window.RealtimeCore ? window.RealtimeCore.eventBus : null;
        this.api = window.RealtimeCore ? window.RealtimeCore.api : null;
        
        // SSE Manager reference
        this.sseManager = null;
        
        // State
        this.openOrders = new Map(); // orderId -> orderData
        this.isInitialized = false;
    }
    
    /**
     * Initialize the open orders manager
     */
    initialize(options = {}) {
        if (this.isInitialized) {
            this.logger.warn('Open orders manager already initialized');
            return;
        }
        
        this.logger.info('Initializing realtime open orders manager...');
        
        // Get SSE manager
        this.sseManager = window.getSSEManager ? window.getSSEManager() : null;
        if (!this.sseManager) {
            this.logger.error('SSE Manager not found');
            return;
        }
        
        // Register SSE event handlers
        this.registerEventHandlers();
        
        // Load initial orders if needed
        if (options.loadOnInit) {
            this.loadOpenOrders();
        }
        
        this.isInitialized = true;
        this.logger.info('✅ Realtime open orders manager initialized');
    }
    
    /**
     * Register SSE event handlers
     */
    registerEventHandlers() {
        if (!this.sseManager) return;
        
        // Order events
        this.sseManager.on('order_update', (data) => {
            this.handleOrderUpdate(data);
        });
        
        // Listen to event bus events
        if (this.eventBus) {
            this.eventBus.on('sse:order_update', (data) => {
                this.handleOrderUpdate(data);
            });
        }
    }
    
    /**
     * Load open orders from API
     */
    async loadOpenOrders() {
        try {
            const response = await fetch('/api/open-orders');
            const data = await response.json();
            
            if (data.success) {
                this.renderOpenOrders(data.open_orders);
                this.updateOpenOrdersCount(data.total_count);
            } else {
                this.showOpenOrdersError('데이터 로딩 실패: ' + data.error);
            }
        } catch (error) {
            this.logger.error('Error loading open orders:', error);
            this.showOpenOrdersError('열린 주문을 불러오는 중 오류가 발생했습니다.');
        }
    }
    
    /**
     * Handle order update from SSE
     */
    handleOrderUpdate(data) {
        try {
            this.logger.info('주문 업데이트 처리:', data);
            
            // Check for market orders (should not appear in open orders)
            if (data.order_type && data.order_type.toUpperCase() === 'MARKET') {
                this.logger.warn('⚠️ Market order received in open orders (unexpected):', data);
            }
            
            // Determine event type from data.event_type
            const eventType = data.event_type;
            
            if (!eventType) {
                this.logger.error('Event type is missing from order data');
                return;
            }
            
            switch (eventType) {
                case 'order_created':
                    this.upsertOrder(data);
                    break;
                    
                case 'order_filled':
                case 'order_cancelled':
                    this.removeOrder(data.order_id);
                    break;
                    
                case 'order_updated':
                    this.upsertOrder(data);
                    break;
                    
                default:
                    this.logger.warn('Unknown order event type:', eventType);
            }
            
            // Update order count
            this.updateOpenOrdersCount();
            
            // Show notification
            this.showOrderNotification(eventType, data);
            
        } catch (error) {
            this.logger.error('Failed to handle order update:', error);
        }
    }
    
    /**
     * Upsert (insert or update) an order
     */
    upsertOrder(orderData) {
        const orderId = orderData.order_id;
        
        if (!orderId) {
            this.logger.error('Order ID is missing');
            return;
        }
        
        // Check if order exists
        const existingOrder = this.openOrders.get(orderId);
        
        // Update order in memory
        this.openOrders.set(orderId, orderData);
        
        // Update DOM
        this.upsertOrderRow(orderData, !existingOrder);
    }
    
    /**
     * Remove an order
     */
    removeOrder(orderId) {
        if (!orderId) {
            this.logger.error('Order ID is missing');
            return;
        }
        
        // Remove from memory
        this.openOrders.delete(orderId);
        
        // Remove from DOM
        this.removeOrderRow(orderId);
        
        // Check if table is empty
        this.checkEmptyOrders();
    }
    
    /**
     * Upsert order row in the table
     */
    upsertOrderRow(orderData, isNew = false) {
        this.logger.info(`📊 주문 ${isNew ? '생성' : '업데이트'}:`, orderData);
        
        // Ensure table exists
        this.ensureOrderTableExists();
        
        const orderTable = document.querySelector('#openOrdersTable tbody');
        if (!orderTable) {
            this.logger.error('Order table tbody not found');
            return;
        }
        
        // Remove empty state if exists
        this.removeEmptyOrdersState();
        
        const orderId = orderData.order_id;
        const existingRow = document.querySelector(`tr[data-order-id="${orderId}"]`);
        
        // Create new row
        const newRow = this.createOrderRow(orderData);
        
        if (existingRow) {
            // Replace existing row
            existingRow.replaceWith(newRow);
            // Add update animation
            if (this.DOM) {
                this.DOM.addTemporaryClass(newRow, 'highlight-update', 2000);
            }
        } else {
            // Add new row
            orderTable.appendChild(newRow);
            // Add new item animation
            if (this.DOM) {
                this.DOM.addTemporaryClass(newRow, 'highlight-new', 2000);
            }
        }
    }
    
    /**
     * Create order row element
     */
    createOrderRow(orderData) {
        const row = document.createElement('tr');
        row.className = 'order-row';
        row.setAttribute('data-order-id', orderData.order_id);
        
        // Standardize side value
        const side = (orderData.side || '').toUpperCase();
        const isBuy = side === 'BUY';
        const quantity = Math.abs(parseFloat(orderData.quantity || 0));
        const price = parseFloat(orderData.price || 0);
        
        // Account info
        const accountName = orderData.account_name || orderData.account?.name || 'Unknown';
        const exchange = orderData.exchange || orderData.account?.exchange || 'unknown';
        const exchangeInitial = exchange.toUpperCase().charAt(0);
        
        // Format values
        const formattedQuantity = this.format ? this.format.formatQuantity(quantity) : quantity.toFixed(8);
        const formattedPrice = this.format ? this.format.formatPrice(price) : `$${price.toFixed(4)}`;
        
        row.innerHTML = `
            <td>
                <div class="account-info">
                    <div class="account-avatar">
                        <span>${exchangeInitial}</span>
                    </div>
                    <div class="account-details">
                        <div class="account-name">${accountName}</div>
                        <div class="account-exchange">${exchange.toUpperCase()}</div>
                    </div>
                </div>
            </td>
            <td>
                <div class="order-symbol">${orderData.symbol}</div>
            </td>
            <td>
                <span class="badge ${isBuy ? 'badge-success' : 'badge-error'}">
                    <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="${isBuy
                            ? 'M5.293 7.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 5.414V17a1 1 0 11-2 0V5.414L6.707 7.707a1 1 0 01-1.414 0z'
                            : 'M14.707 12.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 14.586V3a1 1 0 112 0v11.586l2.293-2.293a1 1 0 011.414 0z'
                        }" clip-rule="evenodd"></path>
                    </svg>
                    ${side}
                </span>
            </td>
            <td class="text-sm text-primary">
                ${formattedQuantity}
            </td>
            <td class="text-sm text-primary">
                ${formattedPrice}
            </td>
            <td>
                <span class="badge badge-warning realtime-status">${orderData.status || 'NEW'}</span>
            </td>
            <td>
                <button data-order-id="${orderData.order_id}" 
                        data-symbol="${orderData.symbol}"
                        class="cancel-order-btn btn btn-warning btn-sm">
                    <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                    취소
                </button>
            </td>
        `;
        
        // Add cancel button event listener
        const cancelBtn = row.querySelector('.cancel-order-btn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                const orderId = cancelBtn.getAttribute('data-order-id');
                const symbol = cancelBtn.getAttribute('data-symbol');
                this.handleCancelOrder(orderId, symbol);
            });
        }
        
        return row;
    }
    
    /**
     * Remove order row from table
     */
    removeOrderRow(orderId) {
        const orderRow = document.querySelector(`tr[data-order-id="${orderId}"]`);
        if (!orderRow) {
            this.logger.warn('Order row not found:', orderId);
            return;
        }
        
        // Add removal animation
        orderRow.style.transition = 'all 0.3s ease-out';
        orderRow.style.opacity = '0.5';
        orderRow.style.transform = 'translateX(-10px)';
        
        setTimeout(() => {
            orderRow.remove();
            this.logger.info('Order row removed:', orderId);
        }, 300);
    }
    
    /**
     * Render all open orders
     */
    renderOpenOrders(orders) {
        const container = document.getElementById('open-orders-content');
        if (!container) return;
        
        if (!orders || orders.length === 0) {
            this.showEmptyOrdersState();
            return;
        }
        
        // Create table structure
        this.createOrderTable(container);
        const tbody = container.querySelector('tbody');
        
        // Clear existing orders
        this.openOrders.clear();
        
        // Add each order
        orders.forEach(order => {
            const orderData = {
                order_id: order.exchange_order_id,
                symbol: order.symbol,
                side: order.side,
                quantity: order.quantity,
                price: order.price,
                status: order.status,
                created_at: order.created_at,
                account: order.account
            };
            
            this.openOrders.set(orderData.order_id, orderData);
            const orderRow = this.createOrderRow(orderData);
            tbody.appendChild(orderRow);
        });
    }
    
    /**
     * Ensure order table exists
     */
    ensureOrderTableExists() {
        const container = document.getElementById('open-orders-content');
        if (!container) return;
        
        let orderTable = container.querySelector('#openOrdersTable');
        if (!orderTable) {
            this.createOrderTable(container);
        }
    }
    
    /**
     * Create order table structure
     */
    createOrderTable(container) {
        const tableHtml = `
            <div class="overflow-x-auto">
                <table id="openOrdersTable" class="table">
                    <thead>
                        <tr>
                            <th>계좌</th>
                            <th>심볼</th>
                            <th>주문방향</th>
                            <th>수량</th>
                            <th>주문가격</th>
                            <th>상태</th>
                            <th>액션</th>
                        </tr>
                    </thead>
                    <tbody>
                    </tbody>
                </table>
            </div>
        `;
        container.innerHTML = tableHtml;
    }
    
    /**
     * Check if orders table is empty
     */
    checkEmptyOrders() {
        const orderRows = document.querySelectorAll('tr[data-order-id]');
        if (orderRows.length === 0) {
            this.showEmptyOrdersState();
        }
    }
    
    /**
     * Show empty orders state
     */
    showEmptyOrdersState() {
        const container = document.getElementById('open-orders-content');
        if (!container) return;
        
        container.innerHTML = `
            <div class="empty-state">
                <svg class="empty-state-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <h3>열린 주문이 없습니다</h3>
                <p>현재 대기 중인 주문이 없습니다.</p>
            </div>
        `;
    }
    
    /**
     * Remove empty orders state
     */
    removeEmptyOrdersState() {
        const container = document.getElementById('open-orders-content');
        if (!container) return;
        
        const emptyState = container.querySelector('.empty-state');
        if (emptyState) {
            this.ensureOrderTableExists();
        }
    }
    
    /**
     * Show open orders error
     */
    showOpenOrdersError(message) {
        const container = document.getElementById('open-orders-content');
        if (!container) return;
        
        container.innerHTML = `
            <div class="text-center py-8">
                <div class="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
                    <svg class="w-8 h-8 text-error" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                </div>
                <p class="text-error">${message}</p>
                <button onclick="loadOpenOrders()" class="btn btn-primary btn-sm mt-3">다시 시도</button>
            </div>
        `;
    }
    
    /**
     * Update open orders count
     */
    updateOpenOrdersCount(count) {
        // If count not provided, calculate from current orders
        if (count === undefined) {
            count = this.openOrders.size;
        }
        
        const countElement = document.getElementById('open-orders-count');
        if (countElement) {
            countElement.textContent = count + '개';
            countElement.className = count > 0 ? 'ml-2 badge badge-warning' : 'ml-2 badge badge-secondary';
        }
    }
    
    /**
     * Show order notification
     */
    showOrderNotification(eventType, data) {
        const eventTypeMap = {
            'order_created': '새 주문',
            'order_filled': '주문 체결',
            'order_cancelled': '주문 취소',
            'order_updated': '주문 업데이트'
        };
        
        const eventTypeText = eventTypeMap[eventType] || '주문 업데이트';
        const toastType = eventType === 'order_filled' ? 'success' : 
                         eventType === 'order_cancelled' ? 'warning' : 'info';
        
        const side = (data.side || '').toUpperCase();
        const quantity = Math.abs(data.quantity || 0);
        const message = `${eventTypeText}: ${data.symbol} ${side} ${quantity}`;
        
        if (window.showToast) {
            window.showToast(message, toastType, 2000);
        }
    }
    
    /**
     * Handle cancel order button click
     */
    async handleCancelOrder(orderId, symbol) {
        if (!confirm(`${symbol} 주문 (ID: ${orderId})을 취소하시겠습니까?`)) {
            return;
        }
        
        try {
            const csrfToken = window.getCSRFToken ? window.getCSRFToken() : '';
            
            const response = await fetch(`/api/open-orders/${orderId}/cancel`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                if (window.showToast) {
                    window.showToast('주문이 성공적으로 취소되었습니다.', 'success');
                }
                // Order will be removed via SSE event
            } else {
                if (window.showToast) {
                    window.showToast('주문 취소 실패: ' + data.error, 'error');
                }
            }
        } catch (error) {
            if (window.showToast) {
                window.showToast('주문 취소 중 오류가 발생했습니다: ' + error.message, 'error');
            }
        }
    }
    
    /**
     * Cancel all open orders
     */
    async cancelAllOpenOrders() {
        if (!confirm('정말로 모든 열린 주문을 취소하시겠습니까?')) {
            return;
        }
        
        try {
            const csrfToken = window.getCSRFToken ? window.getCSRFToken() : '';
            
            const response = await fetch('/api/open-orders/cancel-all', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({})
            });
            
            const data = await response.json();
            
            if (data.success) {
                const successCount = data.cancelled_orders ? data.cancelled_orders.length : 0;
                const failedCount = data.failed_orders ? data.failed_orders.length : 0;
                
                if (window.showToast) {
                    window.showToast(`일괄 취소 완료: ${successCount}개 성공, ${failedCount}개 실패`, 'success');
                }
                // Orders will be removed via SSE events
            } else {
                if (window.showToast) {
                    window.showToast('일괄 취소 실패: ' + data.error, 'error');
                }
            }
        } catch (error) {
            if (window.showToast) {
                window.showToast('일괄 취소 중 오류가 발생했습니다: ' + error.message, 'error');
            }
        }
    }
    
    /**
     * Get order by ID
     */
    getOrder(orderId) {
        return this.openOrders.get(orderId);
    }
    
    /**
     * Get all orders
     */
    getAllOrders() {
        return Array.from(this.openOrders.values());
    }
    
    /**
     * Clear all orders
     */
    clearOrders() {
        this.openOrders.clear();
        this.showEmptyOrdersState();
        this.updateOpenOrdersCount(0);
    }
    
    /**
     * Destroy the manager
     */
    destroy() {
        this.clearOrders();
        this.isInitialized = false;
    }
}

// ========================================
// Global Instance Management
// ========================================

let globalOpenOrdersManager = null;

/**
 * Get or create global open orders manager
 */
function getRealtimeOpenOrdersManager() {
    if (!globalOpenOrdersManager) {
        globalOpenOrdersManager = new RealtimeOpenOrdersManager();
    }
    return globalOpenOrdersManager;
}

/**
 * Initialize realtime open orders
 */
function initializeRealtimeOpenOrders(options = {}) {
    const manager = getRealtimeOpenOrdersManager();
    manager.initialize(options);
    return manager;
}

// ========================================
// Export to Global Scope
// ========================================

window.RealtimeOpenOrdersManager = RealtimeOpenOrdersManager;
window.getRealtimeOpenOrdersManager = getRealtimeOpenOrdersManager;
window.initializeRealtimeOpenOrders = initializeRealtimeOpenOrders;

// Export individual functions for backward compatibility
window.handleOrderUpdate = (data) => {
    const manager = getRealtimeOpenOrdersManager();
    if (manager.isInitialized) {
        manager.handleOrderUpdate(data);
    }
};

window.loadOpenOrders = () => {
    const manager = getRealtimeOpenOrdersManager();
    if (manager.isInitialized) {
        manager.loadOpenOrders();
    }
};

window.refreshOpenOrders = () => {
    const manager = getRealtimeOpenOrdersManager();
    if (manager.isInitialized) {
        manager.loadOpenOrders();
    }
};

window.cancelAllOpenOrders = () => {
    const manager = getRealtimeOpenOrdersManager();
    if (manager.isInitialized) {
        manager.cancelAllOpenOrders();
    }
};

window.cancelOpenOrder = (orderId, symbol) => {
    const manager = getRealtimeOpenOrdersManager();
    if (manager.isInitialized) {
        manager.handleCancelOrder(orderId, symbol);
    }
};

window.upsertOrderRow = (data) => {
    const manager = getRealtimeOpenOrdersManager();
    if (manager.isInitialized) {
        manager.upsertOrder(data);
    }
};

window.updateOpenOrdersCount = (count) => {
    const manager = getRealtimeOpenOrdersManager();
    if (manager.isInitialized) {
        manager.updateOpenOrdersCount(count);
    }
};