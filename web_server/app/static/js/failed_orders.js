/**
 * Failed Orders Management System
 * @FEAT:immediate-order-execution @COMP:ui @TYPE:core
 *
 * Manages failed order display, retry, and removal functionality
 * Provides real-time updates and error handling for failed order operations
 *
 * Key Functions:
 * - loadFailedOrders(filters): Fetch and render failed orders
 * - renderFailedOrders(orders): Render table with order data
 * - retryFailedOrder(id): POST retry API call
 * - removeFailedOrder(id): DELETE API call
 * - filterFailedOrders(): Event handler for filter changes
 *
 * Dependencies:
 * - toast.js: showToast() for notifications
 * - base.html: CSRF token meta tag
 *
 * @see web_server/app/routes/failed_orders.py for API specification
 */

'use strict';

(function (window, document) {
    // Logger reference (graceful fallback)
    const log = window.logger || console;

    /**
     * Get CSRF token from meta tag
     * @returns {string} CSRF token value
     */
    function getCsrfToken() {
        const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        if (!token) {
            log.warn('CSRF token not found in meta tag');
        }
        return token;
    }

    /**
     * Extract error message from API response
     * @param {object} data - API response data
     * @param {string} fallback - Fallback error message
     * @returns {string} Error message
     */
    function getErrorMessage(data, fallback = '알 수 없는 오류가 발생했습니다.') {
        if (!data || typeof data !== 'object') {
            return fallback;
        }

        // Direct error field
        if (typeof data.error === 'string') {
            return data.error;
        }

        // Error object with message field
        if (data.error && typeof data.error === 'object' && data.error.message) {
            return data.error.message;
        }

        // Message field
        if (typeof data.message === 'string') {
            return data.message;
        }

        return fallback;
    }

    /**
     * Escape HTML special characters to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} HTML-escaped text
     */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Fetch failed orders from API with optional filters
     * @param {object} filters - Filter parameters {strategy_account_id, symbol}
     * @returns {Promise<Array>} Array of failed order objects
     */
    async function loadFailedOrders(filters = {}) {
        try {
            // Build query parameters
            const params = new URLSearchParams();
            if (filters.strategy_account_id) {
                params.append('strategy_account_id', filters.strategy_account_id);
            }
            if (filters.symbol) {
                params.append('symbol', filters.symbol);
            }

            const queryString = params.toString();
            const url = `/api/failed-orders${queryString ? '?' + queryString : ''}`;

            log.debug('Loading failed orders from:', url);

            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            if (data.success) {
                log.info(`Failed orders loaded: ${data.orders.length} orders`);
                renderFailedOrders(data.orders);
                return data.orders;
            } else {
                throw new Error(data.error || '주문 조회에 실패했습니다.');
            }

        } catch (error) {
            log.error('Failed to load failed orders:', error);
            const errorMsg = error.message || '실패한 주문을 불러오는데 실패했습니다.';
            showToast(errorMsg, 'error');
            renderFailedOrders([]);
            return [];
        }
    }

    /**
     * Render failed orders table with all order data
     * @param {Array} orders - Array of failed order objects
     */
    function renderFailedOrders(orders) {
        const tbody = document.getElementById('failed-orders-tbody');
        if (!tbody) {
            log.warn('Failed orders table body not found');
            return;
        }

        // Empty state
        if (!orders || orders.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center" style="padding: 2rem;">
                        <svg style="width: 48px; height: 48px; margin: 0 auto 0.5rem; color: var(--text-muted);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        <p style="color: var(--text-muted); margin: 0;">실패된 주문이 없습니다</p>
                    </td>
                </tr>
            `;
            return;
        }

        // Render each order row
        const rows = orders.map(order => {
            const sideBadgeClass = order.side === 'BUY' ? 'badge-buy' : 'badge-sell';
            const sideText = order.side === 'BUY' ? '매수' : '매도';

            // Retry count styling
            let retryCountHtml = '';
            if (order.retry_count > 0) {
                retryCountHtml = `<span class="retry-count-badge">${order.retry_count}/5</span>`;
            }

            // Disable retry button if max retries reached
            const isMaxRetriesReached = order.retry_count >= 5;
            const retryButtonDisabled = isMaxRetriesReached ? 'disabled' : '';
            const retryButtonTitle = isMaxRetriesReached ? '최대 재시도 횟수(5회)에 도달했습니다' : '이 주문을 재시도합니다';

            // Exchange error tooltip
            const exchangeErrorDisplay = order.exchange_error ? escapeHtml(order.exchange_error) : '없음';

            return `
                <tr data-failed-order-id="${order.id}">
                    <td>${escapeHtml(order.symbol)}</td>
                    <td><span class="${sideBadgeClass}">${sideText}</span></td>
                    <td>${escapeHtml(order.order_type)}</td>
                    <td>${parseFloat(order.quantity).toFixed(8)}</td>
                    <td>${order.price ? '$' + parseFloat(order.price).toFixed(4) : 'N/A'}</td>
                    <td>${escapeHtml(order.reason)}</td>
                    <td>
                        <span class="exchange-error-cell">
                            ${exchangeErrorDisplay}
                            ${order.exchange_error ? `<span class="exchange-error-tooltip">${escapeHtml(order.exchange_error)}</span>` : ''}
                        </span>
                    </td>
                    <td>${new Date(order.created_at).toLocaleString('ko-KR')}</td>
                    <td>
                        <button class="btn-retry"
                                onclick="window.retryFailedOrder(${order.id})"
                                title="${retryButtonTitle}"
                                ${retryButtonDisabled}>
                            재시도${retryCountHtml}
                        </button>
                        <button class="btn-remove"
                                onclick="window.removeFailedOrder(${order.id})"
                                title="이 주문을 영구 삭제합니다">
                            제거
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        tbody.innerHTML = rows;
        log.info(`Rendered ${orders.length} failed orders`);
    }

    /**
     * Retry a failed order via API
     * @param {number} failedOrderId - ID of the failed order to retry
     */
    async function retryFailedOrder(failedOrderId) {
        if (!confirm('이 주문을 재시도하시겠습니까?')) {
            return;
        }

        try {
            // Find and disable the button
            const button = document.querySelector(`tr[data-failed-order-id="${failedOrderId}"] .btn-retry`);
            if (button) {
                const originalText = button.innerHTML;
                button.disabled = true;
                button.innerHTML = '처리 중...';

                try {
                    const response = await fetch(`/api/failed-orders/${failedOrderId}/retry`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        }
                    });

                    const data = await response.json();

                    if (data.success) {
                        const message = `재시도 성공: ${data.order_id}`;
                        log.info(message);
                        showToast(message, 'success');
                        // Reload to reflect updated retry count
                        await loadFailedOrders();
                    } else {
                        const errorMsg = getErrorMessage(data, '재시도 중 오류가 발생했습니다.');

                        // Handle specific error cases
                        if (response.status === 400 && data.error.includes('최대 재시도')) {
                            log.warn('Max retry attempts exceeded:', errorMsg);
                        }

                        showToast(errorMsg, 'error');
                        await loadFailedOrders();
                    }

                } finally {
                    // Restore button state
                    button.disabled = false;
                    button.innerHTML = originalText;
                }
            }

        } catch (error) {
            log.error('Failed to retry order:', error);
            const errorMsg = error.message || '재시도 중 오류가 발생했습니다.';
            showToast(errorMsg, 'error');
        }
    }

    /**
     * Remove a failed order via API
     * @param {number} failedOrderId - ID of the failed order to remove
     */
    async function removeFailedOrder(failedOrderId) {
        if (!confirm('이 주문을 영구 삭제하시겠습니까?')) {
            return;
        }

        try {
            // Find and disable the button
            const button = document.querySelector(`tr[data-failed-order-id="${failedOrderId}"] .btn-remove`);
            if (button) {
                const originalText = button.innerHTML;
                button.disabled = true;
                button.innerHTML = '삭제 중...';

                try {
                    const response = await fetch(`/api/failed-orders/${failedOrderId}`, {
                        method: 'DELETE',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        }
                    });

                    const data = await response.json();

                    if (data.success) {
                        log.info('Failed order removed successfully:', failedOrderId);
                        showToast('주문이 삭제되었습니다', 'success');
                        // Reload to reflect deletion
                        await loadFailedOrders();
                    } else {
                        const errorMsg = getErrorMessage(data, '삭제 중 오류가 발생했습니다.');

                        // Handle specific error cases
                        if (response.status === 403) {
                            log.warn('Permission denied:', errorMsg);
                        } else if (response.status === 404) {
                            log.warn('Order not found:', errorMsg);
                        }

                        showToast(errorMsg, 'error');
                        await loadFailedOrders();
                    }

                } finally {
                    // Restore button state
                    button.disabled = false;
                    button.innerHTML = originalText;
                }
            }

        } catch (error) {
            log.error('Failed to remove order:', error);
            const errorMsg = error.message || '삭제 중 오류가 발생했습니다.';
            showToast(errorMsg, 'error');
        }
    }

    /**
     * Event handler for filter changes
     * Collects current filter values and triggers load
     */
    function filterFailedOrders() {
        const strategyAccountId = document.getElementById('filter-strategy')?.value || '';
        const symbol = document.getElementById('filter-symbol')?.value || '';

        const filters = {};
        if (strategyAccountId) {
            filters.strategy_account_id = parseInt(strategyAccountId, 10);
        }
        if (symbol) {
            filters.symbol = symbol;
        }

        log.debug('Applying filters:', filters);
        loadFailedOrders(filters);
    }

    /**
     * Initialize event listeners
     */
    function initializeEventListeners() {
        // Search button click handler
        const searchButton = document.querySelector('.failed-orders-section .filters button');
        if (searchButton) {
            searchButton.addEventListener('click', filterFailedOrders);
            log.debug('Search button listener attached');
        }

        // Enter key on filter inputs
        const strategySelect = document.getElementById('filter-strategy');
        const symbolInput = document.getElementById('filter-symbol');

        if (symbolInput) {
            symbolInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    filterFailedOrders();
                }
            });
            log.debug('Symbol input listener attached');
        }

        if (strategySelect) {
            strategySelect.addEventListener('change', filterFailedOrders);
            log.debug('Strategy select listener attached');
        }
    }

    /**
     * Initialize the failed orders module
     */
    function initialize() {
        log.info('Initializing failed orders module');

        // Check if failed orders section exists
        const section = document.querySelector('.failed-orders-section');
        if (!section) {
            log.warn('Failed orders section not found in DOM');
            return;
        }

        // Initialize event listeners
        initializeEventListeners();

        // Load initial data
        loadFailedOrders();

        log.info('Failed orders module initialized successfully');
    }

    // Register global functions for inline onclick handlers
    window.retryFailedOrder = retryFailedOrder;
    window.removeFailedOrder = removeFailedOrder;
    window.filterFailedOrders = filterFailedOrders;

    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', initialize);

})(window, document);
