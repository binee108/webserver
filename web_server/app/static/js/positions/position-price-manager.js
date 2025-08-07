/**
 * Position Price Manager
 * WebSocket을 통한 실시간 가격 업데이트 관리
 * 거래소별 WebSocket 연결 및 포지션 가격 추적
 */

class PositionPriceManager {
    constructor() {
        this.exchanges = new Map(); // Map of exchange WebSocket instances
        this.positions = new Map(); // Map of position data for price tracking
        this.priceCache = new Map(); // Cache for latest prices by symbol
        this.positionPreviousPrices = new Map(); // Cache for previous prices by position ID
        this.isInitialized = false;
        
        // Exchange configurations
        this.exchangeConfigs = {
            binance: {
                class: window.BinanceWebSocket || null,
                marketTypes: {
                    spot: 'spot',
                    futures: 'futures'
                }
            },
            bybit: {
                class: window.BybitWebSocket || null,
                marketTypes: {
                    spot: 'spot',
                    futures: 'linear'
                }
            },
            okx: {
                class: window.OkxWebSocket || null,
                marketTypes: {
                    spot: 'spot',
                    futures: 'swap'
                }
            }
        };
        
        // Get utilities from RealtimeCore
        this.logger = window.RealtimeCore ? window.RealtimeCore.logger : console;
        this.DOM = window.RealtimeCore ? window.RealtimeCore.DOM : null;
        this.format = window.RealtimeCore ? window.RealtimeCore.format : null;
        this.eventBus = window.RealtimeCore ? window.RealtimeCore.eventBus : null;
    }
    
    /**
     * Initialize with position data
     */
    initialize(positionsData = []) {
        if (this.isInitialized) {
            this.logger.warn('Position price manager already initialized');
            return;
        }
        
        this.logger.info(`Initializing position price tracking for ${positionsData.length} positions`);
        
        // Process positions data
        positionsData.forEach(position => {
            this.addPosition(position);
        });
        
        // Start exchange connections
        this.startExchangeConnections();
        
        this.isInitialized = true;
        this.logger.info('✅ Position price tracking initialized successfully');
    }
    
    /**
     * Add a position to be tracked
     */
    addPosition(positionData) {
        const positionKey = `${positionData.id || positionData.position_id}`;
        
        this.logger.debug(`Adding position for price tracking: ${positionData.symbol} (ID: ${positionKey})`);
        
        // Store position data
        const position = {
            id: positionData.id || positionData.position_id,
            symbol: positionData.symbol,
            exchange: this.normalizeExchangeName(positionData),
            quantity: parseFloat(positionData.quantity),
            entryPrice: parseFloat(positionData.entry_price),
            marketType: this.determineMarketType(positionData),
            accountName: positionData.account?.name || positionData.account_name || 'unknown'
        };
        
        this.positions.set(positionKey, position);
        this.logger.debug(`Position added for price tracking: ${positionKey}`, position);
    }
    
    /**
     * Dynamically add a position and update WebSocket subscriptions
     */
    addPositionDynamic(positionData) {
        const positionKey = `${positionData.id || positionData.position_id}`;
        
        // Check if position already exists
        if (this.positions.has(positionKey)) {
            this.logger.debug(`Position ${positionKey} already tracked, updating...`);
        }
        
        // Add position to tracking
        this.addPosition(positionData);
        
        // Get position details
        const position = this.positions.get(positionKey);
        if (!position) {
            this.logger.error(`Failed to add position ${positionKey}`);
            return;
        }
        
        // Check if we need to subscribe to this symbol
        const exchangeKey = `${position.exchange}-${position.marketType}`;
        const ws = this.exchanges.get(exchangeKey);
        
        if (ws) {
            // Check if already subscribed using unified interface
            if (ws.isSubscribed && ws.isSubscribed(position.symbol)) {
                this.logger.debug(`Already subscribed to ${position.symbol} on ${exchangeKey}`);
            } else {
                this.logger.info(`Dynamically subscribing to ${position.symbol} on ${exchangeKey}`);
                
                try {
                    // Use unified interface
                    ws.subscribePrice(position.symbol, (priceData) => {
                        this.logger.debug(`Price data received for ${position.symbol}:`, priceData);
                        this.updateAllPositionsForSymbol(position.symbol, priceData);
                    });
                    
                    this.logger.info(`✅ Successfully subscribed to ${position.symbol} on ${exchangeKey}`);
                } catch (error) {
                    this.logger.error(`Failed to subscribe to ${position.symbol} on ${exchangeKey}:`, error);
                }
            }
        } else {
            // Need to create new WebSocket connection for this exchange
            this.logger.info(`Creating new WebSocket for ${position.exchange} ${position.marketType}`);
            this.connectToExchange(position.exchange);
        }
    }
    
    /**
     * Dynamically remove a position and update WebSocket subscriptions
     */
    removePositionDynamic(positionId) {
        const positionKey = `${positionId}`;
        const position = this.positions.get(positionKey);
        
        if (!position) {
            this.logger.warn(`Position ${positionKey} not found in tracking`);
            return;
        }
        
        const symbol = position.symbol;
        const exchangeKey = `${position.exchange}-${position.marketType}`;
        
        // Remove position from tracking
        this.positions.delete(positionKey);
        this.logger.info(`Removed position ${positionKey} from price tracking`);
        
        // Check if any other positions use the same symbol
        let symbolStillNeeded = false;
        for (const [, pos] of this.positions.entries()) {
            if (pos.symbol === symbol && 
                pos.exchange === position.exchange && 
                pos.marketType === position.marketType) {
                symbolStillNeeded = true;
                break;
            }
        }
        
        // Unsubscribe if no other positions need this symbol
        if (!symbolStillNeeded) {
            const ws = this.exchanges.get(exchangeKey);
            if (ws && ws.unsubscribe) {
                this.logger.info(`Unsubscribing from ${symbol} on ${exchangeKey} (no positions remaining)`);
                
                try {
                    // Use unified interface
                    const result = ws.unsubscribePrice(symbol);
                    if (result) {
                        this.logger.info(`✅ Successfully unsubscribed from ${symbol} on ${exchangeKey}`);
                    } else {
                        this.logger.warn(`⚠️ Could not unsubscribe from ${symbol} on ${exchangeKey}`);
                    }
                } catch (error) {
                    this.logger.error(`Failed to unsubscribe from ${symbol} on ${exchangeKey}:`, error);
                }
            }
        } else {
            this.logger.debug(`Keeping subscription for ${symbol} on ${exchangeKey} (other positions still need it)`);
        }
        
        // Check if we should disconnect from exchange entirely
        let exchangeStillNeeded = false;
        for (const [, pos] of this.positions.entries()) {
            if (pos.exchange === position.exchange && pos.marketType === position.marketType) {
                exchangeStillNeeded = true;
                break;
            }
        }
        
        if (!exchangeStillNeeded) {
            const ws = this.exchanges.get(exchangeKey);
            if (ws) {
                this.logger.info(`Disconnecting from ${exchangeKey} (no positions remaining)`);
                ws.close();
                this.exchanges.delete(exchangeKey);
            }
        }
    }
    
    /**
     * Normalize exchange name from position data
     */
    normalizeExchangeName(positionData) {
        const exchange = positionData.account?.exchange || positionData.exchange || 'unknown';
        return exchange.toLowerCase();
    }
    
    /**
     * Determine market type from position data
     */
    determineMarketType(positionData) {
        const symbol = positionData.symbol.toUpperCase();
        
        if (symbol.includes('PERP') || symbol.includes('USDT') || symbol.includes('USD')) {
            return 'futures';
        }
        
        return 'spot';
    }
    
    /**
     * Start WebSocket connections for required exchanges
     */
    startExchangeConnections() {
        const requiredExchanges = new Set();
        
        // Determine which exchanges we need to connect to
        this.positions.forEach(position => {
            if (position.exchange && position.exchange !== 'unknown') {
                requiredExchanges.add(position.exchange);
            }
        });
        
        this.logger.info(`Starting connections for ${requiredExchanges.size} exchanges:`, Array.from(requiredExchanges));
        
        // Start connections for each required exchange
        requiredExchanges.forEach(exchangeName => {
            this.connectToExchange(exchangeName);
        });
    }
    
    /**
     * Connect to a specific exchange
     */
    connectToExchange(exchangeName) {
        const config = this.exchangeConfigs[exchangeName];
        if (!config || !config.class) {
            this.logger.warn(`No configuration or class found for exchange: ${exchangeName}`);
            return;
        }
        
        // Get positions for this exchange
        const exchangePositions = Array.from(this.positions.values())
            .filter(pos => pos.exchange === exchangeName);
        
        // Group by market type
        const marketGroups = {};
        exchangePositions.forEach(position => {
            const marketType = position.marketType;
            if (!marketGroups[marketType]) {
                marketGroups[marketType] = [];
            }
            marketGroups[marketType].push(position);
        });
        
        // Create WebSocket connection for each market type
        Object.keys(marketGroups).forEach(marketType => {
            const positions = marketGroups[marketType];
            const wsKey = `${exchangeName}-${marketType}`;
            
            try {
                const ExchangeClass = config.class;
                const ws = new ExchangeClass({
                    marketType: config.marketTypes[marketType] || marketType,
                    onOpen: () => {
                        this.logger.info(`Connected to ${exchangeName} ${marketType}`);
                        this.subscribeToPositions(ws, positions, wsKey);
                        
                        // Update realtime indicator when WebSocket connects
                        if (window.updateRealtimeIndicator) {
                            window.updateRealtimeIndicator(true);
                        }
                        
                        // Emit event for WebSocket connection
                        if (this.eventBus) {
                            this.eventBus.emit('websocket-connected', { exchange: exchangeName, marketType });
                        }
                    },
                    onError: (error) => {
                        this.logger.error(`WebSocket error for ${wsKey}:`, error);
                    },
                    onClose: () => {
                        this.logger.warn(`WebSocket closed for ${wsKey}`);
                        
                        // Check if any WebSocket is still connected
                        if (this.exchanges.size === 0 && window.updateRealtimeIndicator) {
                            window.updateRealtimeIndicator(false);
                        }
                    }
                });
                
                this.exchanges.set(wsKey, ws);
                this.logger.debug(`Created WebSocket connection for ${wsKey}`);
                
            } catch (error) {
                this.logger.error(`Failed to create WebSocket for ${wsKey}:`, error);
            }
        });
    }
    
    /**
     * Subscribe to price updates for positions
     */
    subscribeToPositions(ws, positions, wsKey) {
        this.logger.debug(`Starting subscriptions for ${wsKey} with ${positions.length} positions`);
        
        // Group positions by symbol to avoid duplicate subscriptions
        const symbolGroups = {};
        positions.forEach(position => {
            if (!symbolGroups[position.symbol]) {
                symbolGroups[position.symbol] = [];
            }
            symbolGroups[position.symbol].push(position);
        });
        
        // Get already subscribed symbols for this WebSocket
        const alreadySubscribed = ws.getSubscribedSymbols ? ws.getSubscribedSymbols() : [];
        this.logger.debug(`Already subscribed symbols on ${wsKey}:`, alreadySubscribed);
        
        // Subscribe to each unique symbol once
        Object.entries(symbolGroups).forEach(([symbol, positionsForSymbol]) => {
            try {
                // Check if symbol is already subscribed
                if (alreadySubscribed.includes(symbol)) {
                    this.logger.warn(`Symbol ${symbol} already subscribed on ${wsKey}, skipping duplicate subscription`);
                    return;
                }
                
                this.logger.info(`Subscribing to ${symbol} on ${wsKey} for ${positionsForSymbol.length} positions`);
                
                // Use unified interface
                ws.subscribePrice(symbol, (priceData) => {
                    this.logger.debug(`Price data received for ${symbol} on ${wsKey}:`, priceData);
                    this.updateAllPositionsForSymbol(symbol, priceData);
                });
                
                this.logger.debug(`Successfully subscribed to ${symbol} on ${wsKey}`);
            } catch (error) {
                this.logger.error(`Failed to subscribe to ${symbol} on ${wsKey}:`, error);
            }
        });
    }
    
    /**
     * Update all positions with matching symbol
     */
    updateAllPositionsForSymbol(symbol, priceData) {
        this.logger.debug(`Updating all positions for symbol ${symbol}`);
        
        // Cache the latest price for this symbol
        const symbolCacheKey = `${priceData.exchange}-${symbol}`;
        this.priceCache.set(symbolCacheKey, priceData);
        
        // Find all position elements in the DOM with this symbol
        const positionRows = document.querySelectorAll('.position-row');
        
        positionRows.forEach(row => {
            // Extract position ID from the row
            const positionId = row.getAttribute('data-position-id');
            if (!positionId) return;
            
            const position = this.positions.get(positionId);
            if (!position || position.symbol !== symbol) return;
            
            this.logger.debug(`Updating position ${positionId} (${position.accountName}) for ${symbol}`);
            this.updateSinglePosition(positionId, position, priceData, row);
        });
    }
    
    /**
     * Update a single position's UI elements
     */
    updateSinglePosition(positionId, position, priceData, row) {
        const currentPrice = priceData.price;
        const entryPrice = position.entryPrice;
        const quantity = position.quantity;
        
        // Get previous price for this specific position
        const positionPriceKey = `position-${positionId}`;
        const previousPrice = this.positionPreviousPrices.get(positionPriceKey);
        
        this.logger.debug(`Position ${positionId}: Current=$${currentPrice}, Previous=$${previousPrice}, Entry=$${entryPrice}`);
        
        // Update current price element
        const priceElement = row.querySelector(`#current-price-${positionId}`);
        if (priceElement) {
            const formattedPrice = this.format ? this.format.formatPrice(currentPrice) : `$${currentPrice.toFixed(4)}`;
            priceElement.innerHTML = formattedPrice;
            priceElement.classList.remove('text-gray-400', 'loading-price');
            priceElement.classList.add('text-gray-900');
            
            // Apply price change animation if we have previous price
            if (previousPrice !== undefined) {
                this.applyPriceChangeAnimation(priceElement, currentPrice, previousPrice);
            }
        }
        
        // Calculate and update P&L
        const pnl = (currentPrice - entryPrice) * quantity;
        const pnlPercent = ((currentPrice - entryPrice) / entryPrice) * 100;
        
        const pnlElement = row.querySelector(`#pnl-${positionId}`);
        if (pnlElement) {
            const pnlClass = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
            const formattedPnl = this.format ? 
                `${this.format.formatPrice(Math.abs(pnl), 2)} (${this.format.formatPercent(pnlPercent)})` :
                `$${Math.abs(pnl).toFixed(2)} (${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%)`;
            
            pnlElement.innerHTML = `
                <span class="${pnlClass} font-medium">
                    ${pnl >= 0 ? '+' : '-'}${formattedPnl}
                </span>
            `;
            pnlElement.classList.remove('text-gray-400');
        }
        
        // Update last update timestamp
        const updateElement = row.querySelector(`#last-update-${positionId}`);
        if (updateElement) {
            const now = new Date();
            updateElement.textContent = now.toLocaleTimeString();
        }
        
        // Store current price as previous price for next update
        this.positionPreviousPrices.set(positionPriceKey, currentPrice);
    }
    
    /**
     * Apply visual animation for price change
     */
    applyPriceChangeAnimation(element, currentPrice, previousPrice) {
        if (!element || previousPrice === undefined || previousPrice === null) {
            return;
        }
        
        // Remove any existing animation classes
        element.classList.remove('price-up', 'price-down', 'price-neutral', 'price-animating');
        
        // Force a reflow to ensure classes are removed before adding new ones
        element.offsetHeight;
        
        // Compare prices
        const priceDifference = currentPrice - previousPrice;
        const tolerance = 0.0001;
        
        // Skip animation if price hasn't changed significantly
        if (Math.abs(priceDifference) < tolerance) {
            return;
        }
        
        let animationClass = '';
        if (priceDifference > 0) {
            animationClass = 'price-up';
            this.logger.debug(`Price increased: $${previousPrice.toFixed(4)} → $${currentPrice.toFixed(4)}`);
        } else {
            animationClass = 'price-down';
            this.logger.debug(`Price decreased: $${previousPrice.toFixed(4)} → $${currentPrice.toFixed(4)}`);
        }
        
        // Add animation classes
        element.classList.add(animationClass, 'price-animating');
        
        // Remove animation classes after animation completes
        setTimeout(() => {
            element.classList.remove(animationClass, 'price-animating');
        }, 700);
    }
    
    /**
     * Update subscriptions for all current positions
     */
    updateSubscriptions() {
        this.logger.info('Updating WebSocket subscriptions for all positions...');
        
        // Group positions by exchange and market type
        const exchangeGroups = new Map();
        
        for (const [, position] of this.positions.entries()) {
            const exchangeKey = `${position.exchange}-${position.marketType}`;
            if (!exchangeGroups.has(exchangeKey)) {
                exchangeGroups.set(exchangeKey, new Set());
            }
            exchangeGroups.get(exchangeKey).add(position.symbol);
        }
        
        // Update subscriptions for each exchange
        for (const [exchangeKey, symbols] of exchangeGroups.entries()) {
            const ws = this.exchanges.get(exchangeKey);
            if (!ws) {
                this.logger.warn(`No WebSocket connection for ${exchangeKey}, skipping...`);
                continue;
            }
            
            const currentSubscriptions = ws.getSubscribedSymbols ? ws.getSubscribedSymbols() : [];
            const neededSymbols = Array.from(symbols);
            
            // Subscribe to new symbols
            for (const symbol of neededSymbols) {
                if (!currentSubscriptions.includes(symbol)) {
                    this.logger.info(`Subscribing to ${symbol} on ${exchangeKey}`);
                    try {
                        // Use unified interface
                        ws.subscribePrice(symbol, (priceData) => {
                            this.updateAllPositionsForSymbol(symbol, priceData);
                        });
                    } catch (error) {
                        this.logger.error(`Failed to subscribe to ${symbol}:`, error);
                    }
                }
            }
            
            // Unsubscribe from unneeded symbols
            for (const symbol of currentSubscriptions) {
                if (!neededSymbols.includes(symbol)) {
                    this.logger.info(`Unsubscribing from ${symbol} on ${exchangeKey}`);
                    try {
                        // Use unified interface
                        const result = ws.unsubscribePrice(symbol);
                        if (!result) {
                            this.logger.warn(`Could not unsubscribe from ${symbol} on ${exchangeKey}`);
                        }
                    } catch (error) {
                        this.logger.error(`Failed to unsubscribe from ${symbol}:`, error);
                    }
                }
            }
        }
        
        // Disconnect from exchanges with no positions
        for (const [exchangeKey, ws] of this.exchanges.entries()) {
            if (!exchangeGroups.has(exchangeKey)) {
                this.logger.info(`Disconnecting from ${exchangeKey} (no positions)`);
                ws.close();
                this.exchanges.delete(exchangeKey);
            }
        }
        
        this.logger.info('✅ WebSocket subscriptions updated successfully');
    }
    
    /**
     * Get latest price for a symbol
     */
    getLatestPrice(exchange, symbol) {
        const cacheKey = `${exchange}-${symbol}`;
        return this.priceCache.get(cacheKey);
    }
    
    /**
     * Get connection status for all exchanges
     */
    getConnectionStatus() {
        const status = {};
        
        this.exchanges.forEach((ws, key) => {
            const wsStatus = ws.getStatus ? ws.getStatus() : {};
            status[key] = {
                connected: wsStatus.connected || false,
                subscriptionsCount: wsStatus.subscriptionsCount || 0,
                subscribedSymbols: wsStatus.subscribedSymbols || [],
                reconnectAttempts: wsStatus.reconnectAttempts || 0
            };
        });
        
        this.logger.debug('Current connection status:', status);
        return status;
    }
    
    /**
     * Disconnect all WebSocket connections
     */
    disconnect() {
        this.logger.info('Disconnecting all WebSocket connections');
        
        this.exchanges.forEach((ws, key) => {
            try {
                ws.close();
                this.logger.debug(`Closed connection: ${key}`);
            } catch (error) {
                this.logger.error(`Error closing connection ${key}:`, error);
            }
        });
        
        this.exchanges.clear();
        this.positions.clear();
        this.priceCache.clear();
        this.positionPreviousPrices.clear();
        this.isInitialized = false;
    }
    
    /**
     * Reconnect to all exchanges
     */
    reconnect() {
        this.logger.info('Reconnecting to all exchanges');
        
        // Store current positions
        const currentPositions = Array.from(this.positions.values());
        
        // Disconnect current connections
        this.disconnect();
        
        // Reinitialize with current positions
        setTimeout(() => {
            currentPositions.forEach(position => {
                this.addPosition(position);
            });
            this.startExchangeConnections();
            this.isInitialized = true;
        }, 1000);
    }
    
    /**
     * Get detailed diagnostic information
     */
    getDiagnostics() {
        const diagnostics = {
            timestamp: new Date().toISOString(),
            isInitialized: this.isInitialized,
            totalPositions: this.positions.size,
            totalExchanges: this.exchanges.size,
            totalPriceUpdates: this.priceCache.size,
            exchanges: {},
            positions: [],
            recentPriceUpdates: []
        };
        
        // Exchange diagnostics
        this.exchanges.forEach((ws, key) => {
            diagnostics.exchanges[key] = {
                connected: ws.isConnected || false,
                status: ws.getStatus ? ws.getStatus() : {},
                subscriptions: ws.getSubscribedSymbols ? ws.getSubscribedSymbols().length : 0
            };
        });
        
        // Position diagnostics
        this.positions.forEach((position) => {
            const latestPrice = this.getLatestPrice(position.exchange, position.symbol);
            diagnostics.positions.push({
                id: position.id,
                symbol: position.symbol,
                exchange: position.exchange,
                marketType: position.marketType,
                hasRecentPrice: !!latestPrice,
                lastPriceUpdate: latestPrice ? latestPrice.timestamp : null
            });
        });
        
        // Recent price updates
        this.priceCache.forEach((priceData, key) => {
            diagnostics.recentPriceUpdates.push({
                key: key,
                symbol: priceData.symbol,
                price: priceData.price,
                timestamp: priceData.timestamp,
                exchange: priceData.exchange
            });
        });
        
        return diagnostics;
    }
}

// ========================================
// Global Instance Management
// ========================================

let globalPriceManager = null;

/**
 * Get or create global price manager instance
 */
function getPositionPriceManager() {
    if (!globalPriceManager) {
        globalPriceManager = new PositionPriceManager();
    }
    return globalPriceManager;
}

/**
 * Initialize position price manager
 */
function initializePositionPrices(positionsData = []) {
    const manager = getPositionPriceManager();
    manager.initialize(positionsData);
    return manager;
}

// ========================================
// Export to Global Scope
// ========================================

window.PositionPriceManager = PositionPriceManager;
window.getPositionPriceManager = getPositionPriceManager;
window.initializePositionPrices = initializePositionPrices;

// ========================================
// Legacy Compatibility (레거시 호환성)
// ========================================

// Redirect legacy PositionRealtimeManager to PositionPriceManager
window.PositionRealtimeManager = PositionPriceManager;

// Redirect legacy initialization function
window.initializePositionRealtime = function(positionsData) {
    console.warn('⚠️ initializePositionRealtime is deprecated. Use initializePositionPrices instead.');
    return initializePositionPrices(positionsData);
};

// Redirect legacy getter function
window.getPositionManager = function() {
    console.warn('⚠️ getPositionManager is deprecated. Use getPositionPriceManager instead.');
    return getPositionPriceManager();
};

// Additional legacy functions that might be used
window.upsertPositionRow = function(positionData) {
    console.warn('⚠️ upsertPositionRow is deprecated. Use RealtimePositionsManager instead.');
    const manager = window.getRealtimePositionsManager ? window.getRealtimePositionsManager() : null;
    if (manager && manager.isInitialized) {
        manager.upsertPosition(positionData);
    }
};

window.removePositionRow = function(positionId) {
    console.warn('⚠️ removePositionRow is deprecated. Use RealtimePositionsManager instead.');
    const manager = window.getRealtimePositionsManager ? window.getRealtimePositionsManager() : null;
    if (manager && manager.isInitialized) {
        manager.removePosition(positionId);
    }
};