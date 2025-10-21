/**
 * @fileoverview Real-time Open Orders Manager
 *
 * 열린 주문 관련 실시간 업데이트를 처리하는 모듈
 * SSE를 통한 주문 이벤트 처리 및 DOM 업데이트
 *
 * @FEAT:open-orders-sorting (Phase 1-2 Implemented)
 * Implements client-side sorting for the "Open Orders" table with:
 * - 5-level default sort priority (symbol → status → order_type → side → price)
 * - Column-click sorting (Phase 2 - Implemented 2025-10-18)
 * - Real-time SSE update integration (Phase 3 - Planned)
 *
 * Sort Priority:
 * 1. Symbol (desc) - Alphabetical order, descending
 * 2. Status (desc) - NEW > PENDING_QUEUE (대기열)
 * 3. Order Type (desc) - STOP_MARKET(3) > STOP_LIMIT(2) > LIMIT(1)
 * 4. Side (desc) - SELL > BUY
 * 5. Price (desc) - Highest price first
 *
 * @see .plan/open_orders_sorting_plan.md
 */

/**
 * Toast System - DEBUG 모드 사용 예시
 *
 * 브라우저 콘솔에서 디버그 모드 활성화:
 *   enableDebugMode()
 *
 * 또는 URL 파라미터 사용:
 *   https://yoursite.com/positions?debug=true
 *
 * 예상 로그 출력 (배치 주문 처리 시):
 *   🔍 Toast-Batch Batch aggregation started { summaryCount: 3, uniqueTypes: 2 }
 *   🔍 Toast-FIFO Checking FIFO removal { currentCount: 5, maxToasts: 5, needsRemoval: true }
 *   🔍 Toast-FIFO Removing oldest toast { toastType: 'info' }
 *   🔍 Toast Container already exists (from toast.js)
 *   🔍 Toast Toast triggered { type: 'info', duration: 3000, message: '📦 LIMIT 주문 생성 2건 | STOP_LIMIT 주문 생성 1건' }
 *   🔍 Toast Toast displayed { type: 'info', count: 5, elapsed: '1.45ms' } (from toast.js)
 *   🔍 Toast-FIFO FIFO removal complete { remaining: 4 }
 *
 * Phase 1 (toast.js): 7개 로그 포인트 - 기본 생명주기 추적
 * Phase 2 (realtime-openorders.js): 5개 로그 포인트 - FIFO/배치 집계 추적
 * 통합: 12개 로그 포인트로 전체 토스트 시스템 디버깅
 */

// Phase 1: Toast UI Improvement - Configuration constants
const MAX_TOASTS = 10;  // Maximum number of visible toasts
const TOAST_FADE_DURATION_MS = 300;  // Must match .toast.fade-out transition in CSS

class RealtimeOpenOrdersManager {
    constructor() {
        // Logger 참조 (logger.js 미로드 시 no-op 폴백으로 프로덕션 안전 보장)
        this.logger = window.RealtimeCore ? window.RealtimeCore.logger : {
            debug: () => {},
            info: () => {},
            warn: () => {},
            error: () => {}
        };
        this.DOM = window.RealtimeCore ? window.RealtimeCore.DOM : null;
        this.format = window.RealtimeCore ? window.RealtimeCore.format : null;
        this.eventBus = window.RealtimeCore ? window.RealtimeCore.eventBus : null;
        this.api = window.RealtimeCore ? window.RealtimeCore.api : null;

        // SSE Manager reference
        this.sseManager = null;

        // State
        this.openOrders = new Map(); // orderId -> orderData
        this.isInitialized = false;

        // Sorting state (@FEAT:open-orders-sorting @COMP:service @TYPE:core)
        this.sortConfig = {
            column: null,        // 현재 정렬 컬럼 ('symbol', 'status', 'order_type', 'side', 'price')
            direction: 'asc'     // 정렬 방향 ('asc', 'desc')
        };
        this.defaultSortOrder = [
            { column: 'symbol', direction: 'desc' },
            { column: 'status', direction: 'desc' },      // new > queued (대기열)
            { column: 'order_type', direction: 'desc' },   // stop_market > stop_limit > limit
            { column: 'side', direction: 'desc' },         // sell > buy
            { column: 'price', direction: 'desc' }
        ];
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
     * Get strategy ID from URL (same logic as in positions template)
     */
    getStrategyIdFromUrl() {
        const pathParts = window.location.pathname.split('/');
        const strategiesIndex = pathParts.indexOf('strategies');
        if (strategiesIndex !== -1 && pathParts[strategiesIndex + 1]) {
            return parseInt(pathParts[strategiesIndex + 1]);
        }
        return null;
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

        // @FEAT:batch-sse @PHASE:3 @COMP:integration @TYPE:core
        // Batch order update event listener - Phase 3 integration
        this.sseManager.on('order_batch_update', (data) => {
            this.handleBatchOrderUpdate(data);
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
            // Get strategy ID from URL (same as positions use)
            const strategyId = this.getStrategyIdFromUrl();
            if (!strategyId) {
                this.showOpenOrdersError('전략 ID를 찾을 수 없습니다.');
                return;
            }

            // Use strategy-specific endpoint for proper data isolation
            const response = await fetch(`/api/strategies/${strategyId}/my/open-orders`);
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

            // Account 정보 평탄화 (Backend에서 중첩 구조로 보내므로)
            if (data.account) {
                data.account_name = data.account.name;
                data.exchange = data.account.exchange;
            }

            // PendingOrder 여부 판단 (status 또는 order_id prefix 기반)
            const isPendingOrder = data.status === 'PENDING_QUEUE' ||
                                  (data.order_id && data.order_id.startsWith('p_'));

            // source 필드 추가 (UI에서 구분하기 위함)
            if (isPendingOrder) {
                data.source = 'pending_order';
                this.logger.info('📥 PendingOrder 이벤트 감지:', data.order_id);
            } else {
                data.source = 'open_order';
            }

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

            // Order List SSE는 토스트 스킵 (CLAUDE.md SSE 정책)
            if (data.source !== 'pending_order') {
                this.showOrderNotification(eventType, data);
            }

        } catch (error) {
            this.logger.error('Failed to handle order update:', error);
        }
    }

    /**
     * Handle batch order update from SSE
     * @FEAT:batch-sse @PHASE:3 @COMP:integration @TYPE:core
     *
     * @description
     * Phase 3: Integrates Phase 1 createBatchToast() with Phase 2 backend SSE event
     * - Receives order_batch_update SSE events with aggregated order summaries
     * - Validates event data with null-safe checks
     * - Delegates toast rendering to Phase 1 createBatchToast()
     *
     * @param {Object} data - Event data from SSE
     * @param {Array} data.summaries - Array of {order_type, created, cancelled}
     * @param {string} data.timestamp - ISO 8601 timestamp
     *
     * @example
     * // SSE event from Phase 2 backend:
     * // {summaries: [{order_type: 'LIMIT', created: 5, cancelled: 0}, ...]}
     */
    handleBatchOrderUpdate(data) {
        // Null-safe validation
        if (!data || !data.summaries || data.summaries.length === 0) {
            this.logger.debug('Empty batch update, skipping');
            return;
        }

        try {
            this.logger.info(`📦 Batch order update: ${data.summaries.length} order types`);

            // Phase 1 integration: Delegate to createBatchToast for rendering
            this.createBatchToast(data.summaries);
        } catch (error) {
            this.logger.error('Failed to handle batch order update:', error);
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
     * Insert or update an order row in the table at the correct sorted position
     * @FEAT:open-orders-sorting @PHASE:3 @COMP:ui @TYPE:core
     *
     * @description
     * Phase 3: SSE Real-time Update Integration
     * - Updates in-memory state (this.openOrders)
     * - Sorts all orders using Phase 1 logic (this.sortOrders)
     * - Finds correct insertion index (Array.findIndex)
     * - Inserts at sorted position (insertBefore vs appendChild)
     * - Maintains sort order during SSE real-time updates
     *
     * Algorithm Complexity: O(n log n)
     * - Sort: O(n log n) via this.sortOrders()
     * - Find index: O(n) via findIndex()
     * - DOM insertion: O(1) via insertBefore()
     * Performance: 100 orders → ~5ms
     *
     * @param {Object} orderData - Order data from SSE event
     * @param {boolean} isNew - True if new order (highlight-new), false if update (highlight-update)
     */
    upsertOrderRow(orderData, isNew = false) {
        this.logger.info(`📊 주문 ${isNew ? '생성' : '업데이트'}:`, orderData);

        const orderId = orderData.order_id;

        // Ensure table exists
        this.ensureOrderTableExists();

        const orderTable = document.getElementById('openOrdersTable');
        if (!orderTable) {
            this.logger.error('Order table not found');
            return;
        }

        const tbody = orderTable.querySelector('tbody');
        if (!tbody) {
            this.logger.error('Order table tbody not found');
            return;
        }

        // Remove empty state if exists
        this.removeEmptyOrdersState();

        // Step 1: Update in-memory state
        this.openOrders.set(orderId, orderData);

        // Step 2: Remove existing row if this is an update
        const existingRow = document.querySelector(`tr[data-order-id="${orderId}"]`);
        if (existingRow) {
            existingRow.remove();
        }

        // Step 3: Sort all orders using Phase 1 logic
        const currentOrders = Array.from(this.openOrders.values());
        const sortedOrders = this.sortOrders(currentOrders);

        // Step 4: Find target index in sorted array
        const targetIndex = sortedOrders.findIndex(order => order.order_id === orderId);

        if (targetIndex === -1) {
            this.logger.error(`Order ${orderId} not found in sorted array after insertion`);
            return;
        }

        // Step 5: Create new row
        const newRow = this.createOrderRow(orderData);

        // Step 6: Insert at correct sorted position
        if (targetIndex === 0) {
            // Insert at top
            tbody.insertBefore(newRow, tbody.firstChild);
        } else if (targetIndex >= sortedOrders.length - 1) {
            // Insert at bottom
            tbody.appendChild(newRow);
        } else {
            // Insert in middle - find the DOM node at target position
            const nextOrder = sortedOrders[targetIndex + 1];
            const nextRow = nextOrder ? document.querySelector(`tr[data-order-id="${nextOrder.order_id}"]`) : null;

            if (nextRow) {
                tbody.insertBefore(newRow, nextRow);
            } else {
                // Fallback: nextRow not found in DOM, append to end
                this.logger.warn(`Next row not found for order ${orderId}, appending to end`);
                tbody.appendChild(newRow);
            }
        }

        // Step 7: Apply animation
        if (this.DOM) {
            this.DOM.addTemporaryClass(newRow, isNew ? 'highlight-new' : 'highlight-update', 2000);
        }

        this.logger.debug(`✅ Order ${orderId} inserted at position ${targetIndex}/${sortedOrders.length}`);
    }
    
    /**
     * Create order row element
     */
    createOrderRow(orderData) {
        const row = document.createElement('tr');

        // Determine if this is a pending order (multiple checks for robustness)
        const isPendingOrder = orderData.source === 'pending_order' ||
                              orderData.status === 'PENDING_QUEUE' ||
                              (orderData.order_id && orderData.order_id.startsWith('p_'));
        const rowClass = isPendingOrder ? 'order-row order-row-pending' : 'order-row';

        row.className = rowClass;
        row.setAttribute('data-order-id', orderData.order_id);

        // Add tooltip for pending orders
        if (isPendingOrder) {
            row.setAttribute('title', '거래소 제출 대기 중');
        }

        // Standardize side value
        const side = (orderData.side || '').toUpperCase();
        const isBuy = side === 'BUY';
        const quantity = Math.abs(parseFloat(orderData.quantity || 0));

        // Safe price parsing (handle null/undefined values)
        const price = orderData.price !== null && orderData.price !== undefined ? parseFloat(orderData.price) : 0;
        const stopPrice = orderData.stop_price !== null && orderData.stop_price !== undefined ? parseFloat(orderData.stop_price) : 0;
        const orderType = (orderData.order_type || 'LIMIT').toUpperCase();

        // Account info
        const accountName = orderData.account_name || orderData.account?.name || 'Unknown';
        const exchange = orderData.exchange || orderData.account?.exchange || 'unknown';
        const exchangeInitial = exchange.toUpperCase().charAt(0);

        // Format values with null/NaN checks
        const formattedQuantity = this.format ? this.format.formatQuantity(quantity) : quantity.toFixed(8);
        const formattedPrice = (price > 0 && !isNaN(price)) ? (this.format ? this.format.formatPrice(price) : `$${price.toFixed(4)}`) : '-';
        const formattedStopPrice = (stopPrice > 0 && !isNaN(stopPrice)) ? (this.format ? this.format.formatPrice(stopPrice) : `$${stopPrice.toFixed(4)}`) : '-';

        // Order type badge styling
        const orderTypeBadgeClass = {
            'MARKET': 'badge-info',
            'LIMIT': 'badge-primary',
            'STOP_LIMIT': 'badge-warning',
            'STOP_MARKET': 'badge-error'
        }[orderType] || 'badge-secondary';

        // Status badge - different for pending orders
        const statusBadge = isPendingOrder
            ? `<span class="badge badge-secondary">
                 <svg class="w-3 h-3 mr-1 inline-block" fill="currentColor" viewBox="0 0 20 20">
                   <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"></path>
                 </svg>
                 대기열
               </span>`
            : `<span class="badge badge-warning realtime-status">${orderData.status || 'NEW'}</span>`;

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
                <span class="badge ${orderTypeBadgeClass}">${orderType}</span>
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
            <td class="text-sm text-primary">
                ${formattedStopPrice}
            </td>
            <td>
                ${statusBadge}
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
     * Sort orders by multiple criteria
     *
     * @description
     * Applies 5-level default sort priority:
     * 1. Symbol (desc) - Alphabetical order
     * 2. Status (desc) - NEW > PENDING_QUEUE
     * 3. Order Type (desc) - STOP_MARKET > STOP_LIMIT > LIMIT
     * 4. Side (desc) - SELL > BUY
     * 5. Price (desc) - Highest first
     *
     * User-selected sort column (if provided) takes precedence over default priority.
     *
     * @example
     * // Default sorting (no user selection):
     * const sorted = this.sortOrders(orders);
     *
     * @example
     * // User clicked "price" column (ascending):
     * const sorted = this.sortOrders(orders, { column: 'price', direction: 'asc' });
     *
     * @param {Array<Object>} orders - Array of order objects to sort
     * @param {Object|null} sortConfig - Optional sort configuration
     * @param {string} sortConfig.column - Column name ('symbol'|'status'|'order_type'|'side'|'price')
     * @param {string} sortConfig.direction - Sort direction ('asc'|'desc')
     * @returns {Array<Object>} Sorted orders (new array, does not mutate original)
     * @FEAT:open-orders-sorting @COMP:service @TYPE:core
     */
    sortOrders(orders, sortConfig = null) {
        const ordersCopy = [...orders];  // 원본 배열 보호
        const config = sortConfig || this.sortConfig;
        const defaultOrder = this.defaultSortOrder;

        return ordersCopy.sort((a, b) => {
            // 1순위: 사용자 선택 정렬 (있을 경우)
            if (config.column) {
                const result = this.compareByColumn(a, b, config.column, config.direction);
                if (result !== 0) return result;
            }

            // 2순위: 기본 정렬 우선순위 (5단계)
            for (const { column, direction } of defaultOrder) {
                // 사용자가 이미 선택한 컬럼은 스킵
                if (config.column === column) continue;

                const result = this.compareByColumn(a, b, column, direction);
                if (result !== 0) return result;
            }

            return 0;
        });
    }

    /**
     * Compare two orders by specified column
     * @param {Object} a - First order
     * @param {Object} b - Second order
     * @param {String} column - Column name to compare
     * @param {String} direction - Sort direction ('asc' or 'desc')
     * @returns {Number} Comparison result (-1, 0, 1)
     * @FEAT:open-orders-sorting @COMP:service @TYPE:core
     */
    compareByColumn(a, b, column, direction) {
        let aVal, bVal;

        switch (column) {
            case 'symbol':
                aVal = a.symbol || '';
                bVal = b.symbol || '';
                break;
            case 'status':
                // new > queued (PENDING_QUEUE)
                aVal = this.getStatusPriority(a);
                bVal = this.getStatusPriority(b);
                break;
            case 'order_type':
                aVal = this.getOrderTypePriority(a.order_type);
                bVal = this.getOrderTypePriority(b.order_type);
                break;
            case 'side':
                // sell > buy (desc)
                aVal = (a.side || '').toUpperCase() === 'SELL' ? 1 : 0;
                bVal = (b.side || '').toUpperCase() === 'SELL' ? 1 : 0;
                break;
            case 'price':
                aVal = parseFloat(a.price || 0);
                bVal = parseFloat(b.price || 0);
                break;
            default:
                return 0;
        }

        // 비교 로직
        let result = 0;
        if (aVal > bVal) result = 1;
        else if (aVal < bVal) result = -1;

        return direction === 'desc' ? -result : result;
    }

    /**
     * Get status priority for sorting
     * @param {Object} order - Order object
     * @returns {Number} Priority value (higher = earlier in sort)
     * @FEAT:open-orders-sorting @COMP:service @TYPE:core
     */
    getStatusPriority(order) {
        const isPending = order.source === 'pending_order' ||
                         order.status === 'PENDING_QUEUE' ||
                         (order.order_id && order.order_id.startsWith('p_'));
        return isPending ? 0 : 1;  // new(1) > queued(0)
    }

    /**
     * Get order type priority for sorting
     * @param {String} orderType - Order type string
     * @returns {Number} Priority value (higher = earlier in sort)
     * @FEAT:open-orders-sorting @COMP:service @TYPE:core
     */
    getOrderTypePriority(orderType) {
        const priorities = {
            'STOP_MARKET': 3,
            'STOP_LIMIT': 2,
            'LIMIT': 1,
            'MARKET': 0  // (열린 주문에는 없어야 함)
        };
        return priorities[orderType?.toUpperCase()] || 0;
    }

    /**
     * Update sort indicators in table headers
     *
     * @description
     * Updates CSS classes on .sort-icon elements to reflect current sort state.
     * Shows ▲ (ascending) or ▼ (descending) arrow on the active column,
     * and hides icons on inactive columns.
     *
     * @FEAT:open-orders-sorting @COMP:ui @TYPE:core
     */
    updateSortIndicators() {
        const sortableHeaders = document.querySelectorAll('#openOrdersTable th[data-sortable]');

        sortableHeaders.forEach(header => {
            const column = header.getAttribute('data-sortable');
            const icon = header.querySelector('.sort-icon');
            if (!icon) return;

            if (column === this.sortConfig.column) {
                // 현재 정렬 중인 컬럼
                icon.classList.add('active');
                icon.classList.toggle('desc', this.sortConfig.direction === 'desc');
            } else {
                // 비활성 컬럼
                icon.classList.remove('active', 'desc');
            }
        });
    }

    /**
     * Handle column header click for sorting
     * @FEAT:open-orders-sorting @COMP:ui @TYPE:interaction
     * @param {string} column - Column name to sort by
     */
    handleSort(column) {
        if (this.sortConfig.column === column) {
            // 같은 컬럼 클릭 → 정렬 방향 토글
            this.sortConfig.direction = this.sortConfig.direction === 'asc' ? 'desc' : 'asc';
        } else {
            // 다른 컬럼 클릭 → 새 컬럼으로 정렬 (기본 desc)
            this.sortConfig.column = column;
            this.sortConfig.direction = 'desc';
        }

        // 테이블 재정렬
        this.reorderTable();
    }

    /**
     * Re-sort and re-render the order table
     *
     * @description
     * Applies current sort configuration to all orders in memory,
     * then re-renders the table body (tbody) while preserving the header.
     * Automatically updates sort indicators after rendering.
     *
     * @FEAT:open-orders-sorting @COMP:ui @TYPE:core
     */
    reorderTable() {
        // 현재 주문들을 정렬
        const currentOrders = Array.from(this.openOrders.values());
        const sortedOrders = this.sortOrders(currentOrders);

        // tbody만 업데이트 (헤더 유지)
        const tbody = document.querySelector('#openOrdersTable tbody');
        if (!tbody) return;

        tbody.innerHTML = '';
        sortedOrders.forEach(order => {
            const orderRow = this.createOrderRow(order);
            tbody.appendChild(orderRow);
        });

        // 정렬 아이콘 업데이트
        this.updateSortIndicators();
    }

    /**
     * Attach click event listeners to sortable column headers
     *
     * @description
     * Registers click event handlers on all table headers with data-sortable attribute.
     * Includes idempotency guard to prevent duplicate listener registration.
     * Sets cursor style to 'pointer' for visual feedback.
     *
     * @FEAT:open-orders-sorting @COMP:ui @TYPE:interaction
     */
    attachSortListeners() {
        if (this._listenersAttached) return;  // 중복 방지
        this._listenersAttached = true;

        const sortableHeaders = document.querySelectorAll('#openOrdersTable th[data-sortable]');

        sortableHeaders.forEach(header => {
            header.style.cursor = 'pointer';
            header.addEventListener('click', () => {
                const column = header.getAttribute('data-sortable');
                this.handleSort(column);
            });
        });
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

        // 정렬 적용 (sortOrders 내부에서 복제 처리)
        const sortedOrders = this.sortOrders(orders);

        // Add each order (정렬된 순서대로)
        sortedOrders.forEach(order => {
            // 통일된 명명: order_id만 사용 (이미 백엔드에서 매핑됨)
            this.openOrders.set(order.order_id, order);
            const orderRow = this.createOrderRow(order);
            tbody.appendChild(orderRow);
        });

        // 정렬 UI 업데이트
        this.updateSortIndicators();

        // 컬럼 클릭 이벤트 리스너 등록 (테이블 생성 후)
        this.attachSortListeners();
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
            this.attachSortListeners();
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
                            <th data-sortable="symbol" class="sortable">
                                심볼 <span class="sort-icon"></span>
                            </th>
                            <th data-sortable="order_type" class="sortable">
                                주문타입 <span class="sort-icon"></span>
                            </th>
                            <th data-sortable="side" class="sortable">
                                주문방향 <span class="sort-icon"></span>
                            </th>
                            <th>수량</th>
                            <th data-sortable="price" class="sortable">
                                주문가격 <span class="sort-icon"></span>
                            </th>
                            <th>Stop 가격</th>
                            <th data-sortable="status" class="sortable">
                                상태 <span class="sort-icon"></span>
                            </th>
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
        const side = (data.side || '').toUpperCase();

        // PendingOrder 여부 판단
        const isPendingOrder = data.source === 'pending_order';

        // 색상 타입 결정
        let toastType;
        if (eventType === 'order_filled') {
            // 체결: 매수면 buy(초록), 매도면 sell(빨강)
            toastType = side === 'BUY' ? 'buy' : 'sell';
        } else if (eventType === 'order_cancelled') {
            toastType = 'warning';
        } else if (eventType === 'order_created') {
            // PendingOrder는 info, 일반 주문은 success
            toastType = isPendingOrder ? 'info' : 'success';
        } else {
            toastType = 'info';
        }

        const quantity = Math.abs(data.quantity || 0);

        // PendingOrder인 경우 메시지에 "(대기열)" 추가
        const message = isPendingOrder
            ? `${eventTypeText} (대기열): ${data.symbol} ${side} ${quantity}`
            : `${eventTypeText}: ${data.symbol} ${side} ${quantity}`;

        // Phase 1: FIFO removal before showing new toast
        this._removeFIFOToast();

        if (window.showToast) {
            window.showToast(message, toastType, 2000);
        }
    }

    /**
     * FIFO 큐 관리: 최대 토스트 개수 초과 시 가장 오래된 토스트 제거
     *
     * DEBUG 모드에서 다음 로그를 출력합니다:
     * - FIFO 체크 시작 (현재 개수, 최대 개수, 제거 필요 여부)
     * - 가장 오래된 토스트 제거 중 (토스트 타입)
     * - FIFO 제거 완료 (남은 개수)
     *
     * @private
     */
    _removeFIFOToast() {
        const toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            this.logger.warn('Toast container not found - FIFO removal skipped');
            return;
        }

        const currentToasts = toastContainer.children.length;
        // ADD LOG 1: After currentToasts calculation
        this.logger.debug('Toast-FIFO', 'Checking FIFO removal', {
            currentCount: currentToasts,
            maxToasts: MAX_TOASTS,
            needsRemoval: currentToasts >= MAX_TOASTS
        });

        if (currentToasts >= MAX_TOASTS) {
            const oldestToast = toastContainer.firstChild;
            if (oldestToast && oldestToast.parentNode) {
                // ADD LOG 2: Before adding fade-out class
                this.logger.debug('Toast-FIFO', 'Removing oldest toast', {
                    toastType: oldestToast.className.match(/toast\s+(\w+)/)?.[1] || 'unknown'
                });

                oldestToast.classList.add('fade-out');
                setTimeout(() => {
                    if (oldestToast && oldestToast.parentNode) {
                        oldestToast.remove();
                        // ADD LOG 3: After remove() call
                        this.logger.debug('Toast-FIFO', 'FIFO removal complete', {
                            remaining: toastContainer.children.length
                        });
                    }
                }, TOAST_FADE_DURATION_MS);
            }
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
            const strategyId = this.getStrategyIdFromUrl();

            if (!strategyId) {
                if (window.showToast) {
                    window.showToast('전략 ID를 확인할 수 없습니다.', 'error');
                }
                return;
            }
            
            const response = await fetch('/api/open-orders/cancel-all', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ strategy_id: strategyId })
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
     * 배치 주문 이벤트를 하나의 토스트로 집계하여 표시
     *
     * DEBUG 모드에서 다음 로그를 출력합니다:
     * - 배치 집계 시작 (원본 이벤트 개수, 고유 타입 개수)
     * - 배치 토스트 생성 완료 (최종 메시지, 집계된 타입 개수)
     *
     * @param {Array} summaries - 주문 요약 배열 (order_type, action, count 포함)
     * @private
     */
    createBatchToast(summaries) {
        if (!summaries || summaries.length === 0) {
            return;
        }

        const aggregated = {};
        summaries.forEach(summary => {
            const key = `${summary.order_type}_${summary.action}`;
            if (!aggregated[key]) {
                aggregated[key] = { ...summary, count: 0 };
            }
            aggregated[key].count += summary.count;
        });

        // ADD LOG 1: After aggregation logic completes
        this.logger.debug('Toast-Batch', 'Batch aggregation started', {
            summaryCount: summaries.length,
            uniqueTypes: Object.keys(aggregated).length
        });

        const messages = summaries.map(summary => {
            const parts = [];
            if (summary.created > 0) {
                parts.push(`생성 ${summary.created}건`);
            }
            if (summary.cancelled > 0) {
                parts.push(`취소 ${summary.cancelled}건`);
            }
            if (parts.length === 0) {
                return null;
            }

            return `${summary.order_type} 주문 ${parts.join(', ')}`;
        }).filter(msg => msg !== null);

        if (messages.length > 0) {
            this._removeFIFOToast();

            const finalMessage = `📦 ${messages.join(' | ')}`;
            // ADD LOG 2: Before window.showToast() call
            this.logger.debug('Toast-Batch', 'Batch toast created', {
                message: finalMessage.substring(0, 100),
                aggregatedCount: messages.length
            });

            window.showToast(finalMessage, 'info', 3000);
        }
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