/**
 * @FEAT:position-tracking @COMP:service @TYPE:core
 * Real-time Positions Manager
 * 포지션 관련 실시간 업데이트를 처리하는 모듈
 * SSE를 통한 포지션 이벤트 처리 및 DOM 업데이트
 */

class RealtimePositionsManager {
    constructor() {
        // Get utilities from RealtimeCore
        this.logger = window.RealtimeCore ? window.RealtimeCore.logger : console;
        this.DOM = window.RealtimeCore ? window.RealtimeCore.DOM : null;
        this.format = window.RealtimeCore ? window.RealtimeCore.format : null;
        this.eventBus = window.RealtimeCore ? window.RealtimeCore.eventBus : null;
        
        // SSE Manager reference
        this.sseManager = null;
        
        // Position price manager reference (for WebSocket prices)
        this.priceManager = null;
        
        // State
        this.positions = new Map(); // positionId -> positionData
        this.isInitialized = false;
    }
    
    /**
     * Initialize the positions manager
     */
    initialize(options = {}) {
        if (this.isInitialized) {
            this.logger.warn('Positions manager already initialized');
            return;
        }
        
        this.logger.info('Initializing realtime positions manager...');
        
        // Get SSE manager
        this.sseManager = window.getSSEManager ? window.getSSEManager() : null;
        if (!this.sseManager) {
            this.logger.error('SSE Manager not found');
            return;
        }
        
        // Get price manager if available
        this.priceManager = window.getPositionPriceManager ? window.getPositionPriceManager() : null;
        
        // Register SSE event handlers
        this.registerEventHandlers();
        
        // Load initial positions if provided
        if (options.positions) {
            this.loadInitialPositions(options.positions);
        }
        
        this.isInitialized = true;
        this.logger.info('✅ Realtime positions manager initialized');
    }
    
    /**
     * Register SSE event handlers
     *
     * WHY: SSEManager broadcasts events through eventBus. Avoid registering duplicate
     * handlers in multiple places - receive events through the single SSE channel only.
     *
     * EVENT FLOW (for duplicate prevention):
     * 1. SSE sends position_update → SSEManager.on('position_update')
     * 2. SSEManager broadcasts via eventBus → RealtimePositionsManager.on()
     * 3. RealtimePositionsManager.handlePositionUpdate() → showPositionNotification()
     *    (toast shown here, only once)
     *
     * ANTI-PATTERN PREVENTED:
     * ❌ DO NOT: Listen to eventBus AND register separate SSE listeners
     * ❌ DO NOT: Show toast in multiple places (registerEventHandlers, checkEmptyPositions, etc.)
     */
    registerEventHandlers() {
        if (!this.sseManager) return;

        // Position events (SSEManager already broadcasts via eventBus, avoid duplicate handling)
        this.sseManager.on('position_update', (data) => {
            this.handlePositionUpdate(data);
        });
    }
    
    /**
     * Load initial positions
     */
    loadInitialPositions(positionsData) {
        if (!Array.isArray(positionsData)) return;
        
        this.logger.info(`Loading ${positionsData.length} initial positions`);
        
        // Clear existing positions in table first
        const positionTable = document.querySelector('#positionsTable tbody');
        if (positionTable) {
            const existingRows = positionTable.querySelectorAll('tr[data-position-id]');
            existingRows.forEach(row => row.remove());
        }
        
        // If no positions, show empty state
        if (positionsData.length === 0) {
            this.showEmptyPositionsState();
            return;
        }
        
        // Load and display each position
        positionsData.forEach(position => {
            const positionId = position.position_id;  // 통일된 명명: position_id만 사용
            this.positions.set(positionId, position);
            
            // Display position in table
            this.upsertPositionRow(position, true);
            
            // Initialize price subscription if price manager exists
            if (this.priceManager && this.priceManager.addPosition) {
                this.priceManager.addPosition(position);
            }
        });
        
        // Update statistics
        this.updatePositionStats();
    }
    
    /**
     * Handle position update from SSE
     */
    handlePositionUpdate(data) {
        try {
            this.logger.info('포지션 업데이트 처리:', data);
            
            // Determine event type
            const eventType = data.event_type || data.type;
            
            switch (eventType) {
                case 'position_created':
                case 'position_updated':
                    this.upsertPosition(data);
                    break;
                    
                case 'position_closed':
                    this.removePosition(data.position_id);
                    break;
                    
                default:
                    this.logger.warn('Unknown position event type:', eventType);
            }
            
            // Update statistics
            this.updatePositionStats();
            
            // Show notification
            this.showPositionNotification(eventType, data);
            
        } catch (error) {
            this.logger.error('Failed to handle position update:', error);
        }
    }
    
    /**
     * Upsert (insert or update) a position
     */
    upsertPosition(positionData) {
        const positionId = positionData.position_id;  // 통일된 명명: position_id만 사용
        
        if (!positionId) {
            this.logger.error('Position ID is missing');
            return;
        }
        
        // Check if position exists
        const existingPosition = this.positions.get(positionId);
        
        // Update position in memory
        this.positions.set(positionId, positionData);
        
        // Update DOM
        this.upsertPositionRow(positionData, !existingPosition);
        
        // Handle price subscription
        if (this.priceManager) {
            if (!existingPosition) {
                // New position - add price subscription
                if (this.priceManager.addPositionDynamic) {
                    this.priceManager.addPositionDynamic(positionData);
                }
            } else {
                // Existing position - update if needed
                if (this.priceManager.updatePosition) {
                    this.priceManager.updatePosition(positionData);
                }
            }
        }
    }
    
    /**
     * Remove a position
     */
    removePosition(positionId) {
        if (!positionId) {
            this.logger.error('Position ID is missing');
            return;
        }
        
        // Get position data before removing
        const positionData = this.positions.get(positionId);
        
        // Remove from memory
        this.positions.delete(positionId);
        
        // Remove from DOM
        this.removePositionRow(positionId);
        
        // Remove price subscription
        if (this.priceManager && this.priceManager.removePositionDynamic) {
            this.priceManager.removePositionDynamic(positionId);
        }
        
        // Check if table is empty
        this.checkEmptyPositions();
    }
    
    /**
     * Upsert position row in the table
     */
    upsertPositionRow(positionData, isNew = false) {
        this.logger.info(`📈 포지션 ${isNew ? '생성' : '업데이트'}:`, positionData);
        
        const positionTable = document.querySelector('#positionsTable tbody');
        if (!positionTable) {
            this.logger.error('Position table not found');
            return;
        }
        
        // Remove empty state if exists
        const emptyRow = positionTable.querySelector('.empty-positions-row');
        if (emptyRow) {
            emptyRow.remove();
        }
        
        const positionId = positionData.position_id;  // 통일된 명명: position_id만 사용
        const existingRow = document.querySelector(`tr[data-position-id="${positionId}"]`);
        
        // Create new row
        const newRow = this.createPositionRow(positionData);
        
        if (existingRow) {
            // Replace existing row
            existingRow.replaceWith(newRow);
            // Add update animation
            if (this.DOM) {
                this.DOM.addTemporaryClass(newRow, 'highlight-update', 2000);
            }
        } else {
            // Add new row
            positionTable.appendChild(newRow);
            // Add new item animation
            if (this.DOM) {
                this.DOM.addTemporaryClass(newRow, 'highlight-new', 2000);
            }
        }
    }
    
    /**
     * Create position row element
     */
    createPositionRow(positionData) {
        const row = document.createElement('tr');
        row.className = 'position-row';
        row.setAttribute('data-position-id', positionData.position_id);  // 통일된 명명: position_id만 사용
        
        const isLong = parseFloat(positionData.quantity) > 0;
        const quantity = Math.abs(parseFloat(positionData.quantity));
        const entryPrice = parseFloat(positionData.entry_price || 0);
        
        // Account info
        const accountName = positionData.account_name || positionData.account?.name || 'Unknown';
        const exchange = positionData.exchange || positionData.account?.exchange || 'unknown';
        const exchangeInitial = exchange.toUpperCase().charAt(0);
        
        // Format values
        const formattedQuantity = this.format ? this.format.formatQuantity(quantity) : quantity.toFixed(8);
        const formattedPrice = this.format ? this.format.formatPrice(entryPrice) : `$${entryPrice.toFixed(4)}`;
        
        row.innerHTML = `
            <td>
                <div class="account-info">
                    <div class="account-avatar" data-exchange="${exchange.toLowerCase()}">
                        <span>${exchangeInitial}</span>
                    </div>
                    <div class="account-details">
                        <div class="account-name">${accountName}</div>
                        <div class="account-exchange">${exchange.charAt(0).toUpperCase() + exchange.slice(1)}</div>
                    </div>
                </div>
            </td>
            <td>
                <div class="position-symbol">${positionData.symbol}</div>
            </td>
            <td class="position-direction">
                <span class="badge ${isLong ? 'badge-success' : 'badge-error'}">
                    <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="${isLong 
                            ? 'M5.293 7.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 5.414V17a1 1 0 11-2 0V5.414L6.707 7.707a1 1 0 01-1.414 0z'
                            : 'M14.707 12.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 14.586V3a1 1 0 112 0v11.586l2.293-2.293a1 1 0 011.414 0z'
                        }" clip-rule="evenodd"></path>
                    </svg>
                    ${isLong ? 'LONG' : 'SHORT'}
                </span>
            </td>
            <td class="text-sm text-primary position-quantity">
                ${formattedQuantity}
            </td>
            <td class="text-sm text-primary entry-price">
                ${formattedPrice}
            </td>
            <td class="text-sm text-primary current-price" id="current-price-${positionData.position_id}">
                <span class="text-muted loading-price">연결 중...</span>
            </td>
            <td class="text-sm" id="pnl-${positionData.position_id}">
                <span class="text-muted">계산 중...</span>
            </td>
            <td class="text-sm text-muted">
                <span id="last-update-${positionData.position_id}">방금 전</span>
            </td>
            <td>
                ${quantity !== 0 ? `
                    <button data-position-id="${positionData.position_id}" 
                            class="close-position-btn btn btn-error btn-sm">
                        <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                        청산
                    </button>
                ` : '<span class="text-muted text-xs">-</span>'}
            </td>
        `;
        
        // Add close button event listener
        const closeBtn = row.querySelector('.close-position-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                const positionId = closeBtn.getAttribute('data-position-id');
                this.handleClosePosition(positionId);
            });
        }
        
        return row;
    }
    
    /**
     * Remove position row from table
     */
    removePositionRow(positionId) {
        const positionRow = document.querySelector(`tr[data-position-id="${positionId}"]`);
        if (!positionRow) {
            this.logger.warn('Position row not found:', positionId);
            return;
        }
        
        // Add removal animation
        positionRow.style.transition = 'all 0.3s ease-out';
        positionRow.style.opacity = '0.5';
        positionRow.style.transform = 'translateX(-10px)';
        
        setTimeout(() => {
            positionRow.remove();
            this.logger.info('Position row removed:', positionId);
        }, 300);
    }
    
    /**
     * Check if positions table is empty
     *
     * WHY: Called after position removal to update UI. Toast notification
     * is ALREADY triggered by showPositionNotification() in handlePositionUpdate()
     * during the position_closed event. This function updates DOM only.
     *
     * FLOW: position_closed event → handlePositionUpdate() → removePosition()
     *  → checkEmptyPositions() → showEmptyPositionsState() (UI update, NO toast)
     *
     * NOTE: Do NOT show toast here. Toast is shown once in handlePositionUpdate().
     */
    checkEmptyPositions() {
        const positionRows = document.querySelectorAll('tr[data-position-id]');
        if (positionRows.length === 0) {
            this.showEmptyPositionsState();
            // Toast notification already triggered by showPositionNotification() in handlePositionUpdate()
        }
    }
    
    /**
     * Show empty positions state
     */
    showEmptyPositionsState() {
        const positionTable = document.querySelector('#positionsTable tbody');
        if (!positionTable) return;
        
        // Remove existing empty row
        const existingEmptyRow = positionTable.querySelector('.empty-positions-row');
        if (existingEmptyRow) {
            existingEmptyRow.remove();
        }
        
        // Create empty state row
        const emptyRow = document.createElement('tr');
        emptyRow.className = 'empty-positions-row';
        emptyRow.innerHTML = `
            <td colspan="9">
                <div class="empty-state" style="padding: 2rem 1rem;">
                    <svg class="empty-state-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <h3>보유 포지션이 없습니다</h3>
                    <p>모든 포지션이 성공적으로 청산되었습니다</p>
                </div>
            </td>
        `;
        positionTable.appendChild(emptyRow);
    }
    
    /**
     * Update position statistics
     */
    updatePositionStats() {
        const positionRows = document.querySelectorAll('tr[data-position-id]');
        const totalCount = positionRows.length;
        
        let longCount = 0;
        let shortCount = 0;
        
        positionRows.forEach(row => {
            const directionBadge = row.querySelector('.position-direction .badge');
            if (directionBadge) {
                if (directionBadge.classList.contains('badge-success')) {
                    longCount++;
                } else if (directionBadge.classList.contains('badge-error')) {
                    shortCount++;
                }
            }
        });
        
        // Update stat cards
        const totalElement = document.querySelector('.stats-grid .stats-value');
        if (totalElement) {
            totalElement.textContent = totalCount;
        }
        
        const longElements = document.querySelectorAll('.stats-grid .stats-card:nth-child(2) .stats-value');
        longElements.forEach(el => el.textContent = longCount);
        
        const shortElements = document.querySelectorAll('.stats-grid .stats-card:nth-child(3) .stats-value');
        shortElements.forEach(el => el.textContent = shortCount);
        
        this.logger.debug('Position stats updated:', { total: totalCount, long: longCount, short: shortCount });
    }
    
    /**
     * Show position notification
     */
    showPositionNotification(eventType, data) {
        const eventTypeText = {
            'position_created': '새 포지션',
            'position_updated': '포지션 업데이트',
            'position_closed': '포지션 청산'
        }[eventType] || '포지션 변경';
        
        const message = `${eventTypeText}: ${data.symbol} (${Math.abs(data.quantity)})`;
        
        if (window.showToast) {
            window.showToast(message, 'success', 2000);
        }
    }
    
    /**
     * Handle close position button click
     */
    handleClosePosition(positionId) {
        if (typeof closePosition === 'function') {
            closePosition(positionId);
        } else {
            this.logger.warn('closePosition function not found');
        }
    }
    
    /**
     * Get position by ID
     */
    getPosition(positionId) {
        return this.positions.get(positionId);
    }
    
    /**
     * Get all positions
     */
    getAllPositions() {
        return Array.from(this.positions.values());
    }
    
    /**
     * Clear all positions
     */
    clearPositions() {
        this.positions.clear();
        
        // Clear table
        const positionTable = document.querySelector('#positionsTable tbody');
        if (positionTable) {
            positionTable.innerHTML = '';
            this.showEmptyPositionsState();
        }
    }
    
    /**
     * Destroy the manager
     */
    destroy() {
        this.clearPositions();
        this.isInitialized = false;
    }
}

// ========================================
// Global Instance Management
// ========================================

let globalPositionsManager = null;

/**
 * Get or create global positions manager
 */
function getRealtimePositionsManager() {
    if (!globalPositionsManager) {
        globalPositionsManager = new RealtimePositionsManager();
    }
    return globalPositionsManager;
}

/**
 * Initialize realtime positions
 */
function initializeRealtimePositions(options = {}) {
    const manager = getRealtimePositionsManager();
    manager.initialize(options);
    return manager;
}

// ========================================
// Export to Global Scope
// ========================================

window.RealtimePositionsManager = RealtimePositionsManager;
window.getRealtimePositionsManager = getRealtimePositionsManager;
window.initializeRealtimePositions = initializeRealtimePositions;

// Export individual functions for backward compatibility
window.handlePositionUpdate = (data) => {
    const manager = getRealtimePositionsManager();
    if (manager.isInitialized) {
        manager.handlePositionUpdate(data);
    }
};

window.upsertPositionRow = (data) => {
    const manager = getRealtimePositionsManager();
    if (manager.isInitialized) {
        manager.upsertPosition(data);
    }
};

window.removePositionRow = (positionId) => {
    const manager = getRealtimePositionsManager();
    if (manager.isInitialized) {
        manager.removePosition(positionId);
    }
};

window.updatePositionStats = () => {
    const manager = getRealtimePositionsManager();
    if (manager.isInitialized) {
        manager.updatePositionStats();
    }
};

window.checkEmptyPositions = () => {
    const manager = getRealtimePositionsManager();
    if (manager.isInitialized) {
        manager.checkEmptyPositions();
    }
};

window.showEmptyPositionsState = () => {
    const manager = getRealtimePositionsManager();
    if (manager.isInitialized) {
        manager.showEmptyPositionsState();
    }
};
