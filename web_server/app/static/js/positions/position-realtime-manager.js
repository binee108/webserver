/**
 * Position Real-time Manager
 * Manages real-time price updates for positions across multiple exchanges
 */
class PositionRealtimeManager {
    constructor() {
        this.exchanges = new Map(); // Map of exchange instances
        this.positions = new Map(); // Map of position data
        this.priceCache = new Map(); // Cache for latest prices by symbol
        this.positionPreviousPrices = new Map(); // Cache for previous prices by position ID
        this.isInitialized = false;
        
        // Exchange configurations
        this.exchangeConfigs = {
            binance: {
                class: BinanceWebSocket,
                marketTypes: {
                    spot: 'spot',
                    futures: 'futures'
                }
            },
            bybit: {
                class: BybitWebSocket,
                marketTypes: {
                    spot: 'spot',
                    futures: 'linear'
                }
            },
            okx: {
                class: OkxWebSocket,
                marketTypes: {
                    spot: 'spot',
                    futures: 'swap'
                }
            }
        };
        
        // Use logger if available, fallback to console
        this.log = window.logger || console;
        this.log.debug('Position Realtime Manager initialized');
    }
    
    /**
     * Initialize with position data from the page
     */
    initialize(positionsData) {
        if (this.isInitialized) {
            this.log.warn('Position manager already initialized');
            return;
        }
        
        this.log.info(`Initializing position tracking for ${positionsData.length} positions`);
        
        // Process positions data
        positionsData.forEach(position => {
            this.addPosition(position);
        });
        
        // Start exchange connections
        this.startExchangeConnections();
        
        this.isInitialized = true;
        this.log.success('Position tracking initialized successfully');
    }
    
    /**
     * Add a position to be tracked
     */
    addPosition(positionData) {
        const positionKey = `${positionData.id}`;
        
        this.log.debug(`Adding position: ${positionData.symbol} (ID: ${positionData.id}, Exchange: ${positionData.account ? positionData.account.exchange : 'unknown'})`);
        
        // Store position data
        const position = {
            id: positionData.id,
            symbol: positionData.symbol,
            exchange: positionData.account ? positionData.account.exchange.toLowerCase() : 'unknown',
            quantity: parseFloat(positionData.quantity),
            entryPrice: parseFloat(positionData.entry_price),
            marketType: this.determineMarketType(positionData),
            accountName: positionData.account ? positionData.account.name : 'unknown'
        };
        
        this.positions.set(positionKey, position);
        this.log.debug(`Position tracking added: ${positionKey}`, position);
    }
    
    /**
     * Dynamically add a position and update WebSocket subscriptions
     */
    addPositionDynamic(positionData) {
        const positionKey = `${positionData.id || positionData.position_id}`;
        
        // Check if position already exists
        if (this.positions.has(positionKey)) {
            this.log.debug(`Position ${positionKey} already tracked, updating...`);
        }
        
        // Normalize position data
        const normalizedData = {
            id: positionData.id || positionData.position_id,
            symbol: positionData.symbol,
            account: positionData.account || {
                exchange: positionData.exchange || 'unknown',
                name: positionData.account_name || 'unknown'
            },
            quantity: positionData.quantity,
            entry_price: positionData.entry_price
        };
        
        // Add position to tracking
        this.addPosition(normalizedData);
        
        // Get position details
        const position = this.positions.get(positionKey);
        if (!position) {
            this.log.error(`Failed to add position ${positionKey}`);
            return;
        }
        
        // Check if we need to subscribe to this symbol
        const exchangeKey = `${position.exchange}-${position.marketType}`;
        const ws = this.exchanges.get(exchangeKey);
        
        if (ws) {
            // Check if already subscribed to this symbol
            const subscribedSymbols = ws.getSubscribedSymbols ? ws.getSubscribedSymbols() : [];
            if (!subscribedSymbols.includes(position.symbol)) {
                this.log.subscription(`Dynamically subscribing to ${position.symbol} on ${exchangeKey}`);
                
                try {
                    ws.subscribeToPrice(position.symbol, (priceData) => {
                        this.log.debug(`Price data received for ${position.symbol} on ${exchangeKey}:`, priceData);
                        this.updateAllPositionsForSymbol(position.symbol, priceData);
                    });
                    
                    this.log.success(`Successfully subscribed to ${position.symbol} on ${exchangeKey}`);
                } catch (error) {
                    this.log.error(`Failed to subscribe to ${position.symbol} on ${exchangeKey}:`, error);
                }
            } else {
                this.log.debug(`Already subscribed to ${position.symbol} on ${exchangeKey}`);
            }
        } else {
            // Need to create new WebSocket connection for this exchange
            this.log.info(`Creating new WebSocket for ${position.exchange} ${position.marketType}`);
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
            this.log.warn(`Position ${positionKey} not found in tracking`);
            return;
        }
        
        const symbol = position.symbol;
        const exchangeKey = `${position.exchange}-${position.marketType}`;
        
        // Remove position from tracking
        this.positions.delete(positionKey);
        this.log.info(`Removed position ${positionKey} from tracking`);
        
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
                this.log.subscription(`Unsubscribing from ${symbol} on ${exchangeKey} (no positions remaining)`);
                
                try {
                    ws.unsubscribe('ticker', symbol);
                    this.log.success(`Successfully unsubscribed from ${symbol} on ${exchangeKey}`);
                } catch (error) {
                    this.log.error(`Failed to unsubscribe from ${symbol} on ${exchangeKey}:`, error);
                }
            }
        } else {
            this.log.debug(`Keeping subscription for ${symbol} on ${exchangeKey} (other positions still need it)`);
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
                this.log.info(`Disconnecting from ${exchangeKey} (no positions remaining)`);
                ws.close();
                this.exchanges.delete(exchangeKey);
            }
        }
    }
    
    /**
     * Update subscriptions for all current positions
     * Useful for reconciling subscriptions after multiple changes
     */
    updateSubscriptions() {
        this.log.info('Updating WebSocket subscriptions for all positions...');
        
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
                this.log.warn(`No WebSocket connection for ${exchangeKey}, skipping...`);
                continue;
            }
            
            const currentSubscriptions = ws.getSubscribedSymbols ? ws.getSubscribedSymbols() : [];
            const neededSymbols = Array.from(symbols);
            
            // Subscribe to new symbols
            for (const symbol of neededSymbols) {
                if (!currentSubscriptions.includes(symbol)) {
                    this.log.subscription(`Subscribing to ${symbol} on ${exchangeKey}`);
                    try {
                        ws.subscribeToPrice(symbol, (priceData) => {
                            this.updateAllPositionsForSymbol(symbol, priceData);
                        });
                    } catch (error) {
                        this.log.error(`Failed to subscribe to ${symbol}:`, error);
                    }
                }
            }
            
            // Unsubscribe from unneeded symbols
            for (const symbol of currentSubscriptions) {
                if (!neededSymbols.includes(symbol)) {
                    this.log.subscription(`Unsubscribing from ${symbol} on ${exchangeKey}`);
                    try {
                        ws.unsubscribe('ticker', symbol);
                    } catch (error) {
                        this.log.error(`Failed to unsubscribe from ${symbol}:`, error);
                    }
                }
            }
        }
        
        // Disconnect from exchanges with no positions
        for (const [exchangeKey, ws] of this.exchanges.entries()) {
            if (!exchangeGroups.has(exchangeKey)) {
                this.log.info(`Disconnecting from ${exchangeKey} (no positions)`);
                ws.close();
                this.exchanges.delete(exchangeKey);
            }
        }
        
        this.log.success('WebSocket subscriptions updated successfully');
    }
    
    /**
     * Determine market type from position data
     */
    determineMarketType(positionData) {
        // Check if it's a futures/perpetual contract
        const symbol = positionData.symbol.toUpperCase();
        
        if (symbol.includes('PERP') || symbol.includes('USDT') || symbol.includes('USD')) {
            // Most perpetual contracts contain these patterns
            return 'futures';
        }
        
        // Default to spot
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
        
        this.log.info(`Starting connections for ${requiredExchanges.size} exchanges:`, Array.from(requiredExchanges));
        
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
        if (!config) {
            this.log.warn(`No configuration found for exchange: ${exchangeName}`);
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
                        this.log.connection(`Connected to ${exchangeName} ${marketType}`);
                        this.subscribeToPositions(ws, positions, wsKey);
                    },
                    onError: (error) => {
                        this.log.error(`WebSocket error for ${wsKey}:`, error);
                    },
                    onClose: () => {
                        this.log.warn(`WebSocket closed for ${wsKey}`);
                    }
                });
                
                this.exchanges.set(wsKey, ws);
                this.log.debug(`Created WebSocket connection for ${wsKey}`);
                
            } catch (error) {
                this.log.error(`Failed to create WebSocket for ${wsKey}:`, error);
            }
        });
    }
    
    /**
     * Subscribe to price updates for positions
     */
    subscribeToPositions(ws, positions, wsKey) {
        this.log.debug(`Starting subscriptions for ${wsKey} with ${positions.length} positions`);
        
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
        this.log.debug(`Already subscribed symbols on ${wsKey}:`, alreadySubscribed);
        
        // Subscribe to each unique symbol once, but only if not already subscribed
        Object.entries(symbolGroups).forEach(([symbol, positionsForSymbol]) => {
            try {
                // Check if symbol is already subscribed
                if (alreadySubscribed.includes(symbol)) {
                    this.log.warn(`Symbol ${symbol} already subscribed on ${wsKey}, skipping duplicate subscription`);
                    return;
                }
                
                this.log.subscription(`Subscribing to ${symbol} on ${wsKey} for ${positionsForSymbol.length} positions`);
                
                ws.subscribeToPrice(symbol, (priceData) => {
                    this.log.debug(`Price data received for ${symbol} on ${wsKey}:`, priceData);
                    
                    // Update all positions with this symbol by DOM traversal
                    this.updateAllPositionsForSymbol(symbol, priceData);
                });
                
                this.log.debug(`Successfully subscribed to ${symbol} on ${wsKey}`);
            } catch (error) {
                this.log.error(`Failed to subscribe to ${symbol} on ${wsKey}:`, error);
            }
        });
        
        // Log subscription status after attempting all subscriptions
        setTimeout(() => {
            const status = ws.getStatus();
            this.log.debug(`${wsKey} subscription status:`, status);
            
            // Verify no duplicate subscriptions
            const finalSubscribed = ws.getSubscribedSymbols ? ws.getSubscribedSymbols() : [];
            const uniqueSymbols = [...new Set(finalSubscribed)];
            
            if (finalSubscribed.length !== uniqueSymbols.length) {
                this.log.warn(`Duplicate subscriptions detected on ${wsKey}!`);
                this.log.debug('All subscribed:', finalSubscribed);
                this.log.debug('Unique symbols:', uniqueSymbols);
            } else {
                this.log.debug(`No duplicate subscriptions on ${wsKey} (${finalSubscribed.length} unique symbols)`);
            }
        }, 1500);
    }
    
    /**
     * Update all positions with matching symbol through DOM traversal
     */
    updateAllPositionsForSymbol(symbol, priceData) {
        this.log.debug(`Updating all positions for symbol ${symbol}`);
        
        // Cache the latest price for this symbol
        const symbolCacheKey = `${priceData.exchange}-${symbol}`;
        this.priceCache.set(symbolCacheKey, priceData);
        
        // Find all position elements in the DOM with this symbol
        const positionRows = document.querySelectorAll('.position-row');
        
        positionRows.forEach(row => {
            // Extract position ID from the row's price element ID
            const priceElement = row.querySelector('[id^="current-price-"]');
            if (!priceElement) return;
            
            const positionId = priceElement.id.replace('current-price-', '');
            const position = this.positions.get(positionId);
            
            if (!position) return;
            
            // Check if this position matches the symbol
            if (position.symbol === symbol) {
                this.log.debug(`Updating position ${positionId} (${position.accountName}) for ${symbol}`);
                this.updateSinglePosition(positionId, position, priceData, row);
            }
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
        
        this.log.price(`Position ${positionId}: Current=$${currentPrice}, Previous=$${previousPrice}, Entry=$${entryPrice}`);
        
        // Update current price element
        const priceElement = row.querySelector(`#current-price-${positionId}`);
        if (priceElement) {
            priceElement.innerHTML = `$${currentPrice.toFixed(4)}`;
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
            const pnlSign = pnl >= 0 ? '+' : '';
            
            pnlElement.innerHTML = `
                <span class="${pnlClass} font-medium">
                    ${pnlSign}$${pnl.toFixed(2)} (${pnlSign}${pnlPercent.toFixed(2)}%)
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
     * Apply visual animation for price change based on previous price comparison
     */
    applyPriceChangeAnimation(element, currentPrice, previousPrice) {
        if (!element || previousPrice === undefined || previousPrice === null) {
            return; // No animation if no previous price to compare
        }
        
        // Remove any existing animation classes
        element.classList.remove('price-up', 'price-down', 'price-neutral', 'price-animating');
        
        // Force a reflow to ensure classes are removed before adding new ones
        element.offsetHeight;
        
        // Compare current price with previous price
        const priceDifference = currentPrice - previousPrice;
        const tolerance = 0.0001; // Small tolerance for floating point comparison
        
        // Skip animation if price hasn't changed significantly
        if (Math.abs(priceDifference) < tolerance) {
            return;
        }
        
        let animationClass = '';
        if (priceDifference > 0) {
            // Price increased - green flash
            animationClass = 'price-up';
            this.log.debug(`Price increased: $${previousPrice.toFixed(4)} → $${currentPrice.toFixed(4)}`);
        } else {
            // Price decreased - red flash
            animationClass = 'price-down';
            this.log.debug(`Price decreased: $${previousPrice.toFixed(4)} → $${currentPrice.toFixed(4)}`);
        }
        
        // Add the appropriate animation class
        element.classList.add(animationClass, 'price-animating');
        
        // Remove animation classes after animation completes
        setTimeout(() => {
            element.classList.remove(animationClass, 'price-animating');
        }, 700); // Slightly longer than CSS animation duration (0.6s)
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
            const wsStatus = ws.getStatus();
            status[key] = {
                connected: wsStatus.connected,
                subscriptionsCount: wsStatus.subscriptionsCount,
                subscribedSymbols: wsStatus.subscribedSymbols || [],
                reconnectAttempts: wsStatus.reconnectAttempts
            };
        });
        
        this.log.debug('Current connection status:', status);
        return status;
    }
    
    /**
     * Disconnect all WebSocket connections
     */
    disconnect() {
        this.log.info('Disconnecting all WebSocket connections');
        
        this.exchanges.forEach((ws, key) => {
            try {
                ws.close();
                this.log.debug(`Closed connection: ${key}`);
            } catch (error) {
                this.log.error(`Error closing connection ${key}:`, error);
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
        this.log.info('Reconnecting to all exchanges');
        
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
                connected: ws.isConnected,
                status: ws.getStatus(),
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
    
    /**
     * Test specific exchange connection
     */
    testExchangeConnection(exchangeName, marketType = 'spot', symbols = ['BTCUSDT']) {
        return new Promise((resolve, reject) => {
            const config = this.exchangeConfigs[exchangeName];
            if (!config) {
                reject(new Error(`No configuration found for exchange: ${exchangeName}`));
                return;
            }
            
            this.log.info(`Testing ${exchangeName} ${marketType} connection...`);
            
            const testResults = {
                exchange: exchangeName,
                marketType: marketType,
                connectionSuccess: false,
                subscriptionSuccess: false,
                priceDataReceived: false,
                errors: [],
                priceUpdates: []
            };
            
            try {
                const ExchangeClass = config.class;
                const ws = new ExchangeClass({
                    marketType: config.marketTypes[marketType] || marketType,
                    onOpen: () => {
                        this.log.success(`${exchangeName} ${marketType} connected`);
                        testResults.connectionSuccess = true;
                        
                        // Test subscription for each symbol
                        symbols.forEach(symbol => {
                            try {
                                ws.subscribeToPrice(symbol, (priceData) => {
                                    this.log.info(`Price received: ${symbol} = $${priceData.price}`);
                                    testResults.priceDataReceived = true;
                                    testResults.priceUpdates.push({
                                        symbol: symbol,
                                        price: priceData.price,
                                        timestamp: priceData.timestamp
                                    });
                                });
                                testResults.subscriptionSuccess = true;
                            } catch (error) {
                                testResults.errors.push(`Subscription failed for ${symbol}: ${error.message}`);
                            }
                        });
                    },
                    onError: (error) => {
                        this.log.error(`${exchangeName} ${marketType} error:`, error);
                        testResults.errors.push(`Connection error: ${error.message || error}`);
                    },
                    onClose: () => {
                        this.log.info(`${exchangeName} ${marketType} disconnected`);
                    }
                });
                
                // Complete test after 8 seconds
                setTimeout(() => {
                    ws.close();
                    testResults.completed = true;
                    resolve(testResults);
                }, 8000);
                
            } catch (error) {
                testResults.errors.push(`Failed to create connection: ${error.message}`);
                reject(testResults);
            }
        });
    }
    
    /**
     * Run comprehensive system test
     */
    async runSystemTest() {
        this.log.info('Starting comprehensive system test...');
        
        const testResults = {
            timestamp: new Date().toISOString(),
            overall: 'running',
            exchanges: {},
            summary: {
                totalTests: 0,
                passed: 0,
                failed: 0
            }
        };
        
        // Test each exchange with different market types
        const testMatrix = [
            { exchange: 'binance', marketType: 'spot', symbols: ['BTCUSDT', 'ETHUSDT'] },
            { exchange: 'binance', marketType: 'futures', symbols: ['BTCUSDT', 'ETHUSDT'] },
            { exchange: 'bybit', marketType: 'spot', symbols: ['BTCUSDT', 'ETHUSDT'] },
            { exchange: 'bybit', marketType: 'linear', symbols: ['BTCUSDT', 'ETHUSDT'] },
            { exchange: 'okx', marketType: 'spot', symbols: ['BTC-USDT', 'ETH-USDT'] },
            { exchange: 'okx', marketType: 'swap', symbols: ['BTC-USDT-SWAP', 'ETH-USDT-SWAP'] }
        ];
        
        for (const test of testMatrix) {
            testResults.summary.totalTests++;
            
            try {
                const result = await this.testExchangeConnection(
                    test.exchange, 
                    test.marketType, 
                    test.symbols
                );
                
                testResults.exchanges[`${test.exchange}-${test.marketType}`] = result;
                
                if (result.connectionSuccess && result.priceDataReceived) {
                    testResults.summary.passed++;
                } else {
                    testResults.summary.failed++;
                }
                
            } catch (error) {
                testResults.exchanges[`${test.exchange}-${test.marketType}`] = error;
                testResults.summary.failed++;
            }
        }
        
        testResults.overall = testResults.summary.failed === 0 ? 'passed' : 'failed';
        
        this.log.info('System test completed:', testResults);
        return testResults;
    }
}

// Global instance
let positionManager = null;

/**
 * Initialize position real-time manager
 */
function initializePositionRealtime(positionsData) {
    if (positionManager) {
        positionManager.disconnect();
    }
    
    positionManager = new PositionRealtimeManager();
    positionManager.initialize(positionsData);
    
    return positionManager;
}

/**
 * Get global position manager instance
 */
function getPositionManager() {
    return positionManager;
}

// ========================================
// Position UI Management Functions
// ========================================

/**
 * Create a position row element
 */
function createPositionRow(positionData) {
    const row = document.createElement('tr');
    row.className = 'position-row';
    row.setAttribute('data-position-id', positionData.position_id || positionData.id);
    
    const isLong = parseFloat(positionData.quantity) > 0;
    const quantity = Math.abs(parseFloat(positionData.quantity));
    const entryPrice = parseFloat(positionData.entry_price || 0);
    
    // 계좌 정보 (중첩 구조 지원)
    const accountName = positionData.account_name || positionData.account?.name || 'Unknown';
    const exchange = positionData.exchange || positionData.account?.exchange || 'unknown';
    const exchangeInitial = exchange.toUpperCase().charAt(0);
    
    row.innerHTML = `
        <td>
            <div class="account-info">
                <div class="account-avatar">
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
            ${quantity.toFixed(8)}
        </td>
        <td class="text-sm text-primary entry-price">
            $${entryPrice.toFixed(4)}
        </td>
        <td class="text-sm text-primary current-price" id="current-price-${positionData.position_id || positionData.id}">
            <span class="text-muted loading-price">연결 중...</span>
        </td>
        <td class="text-sm" id="pnl-${positionData.position_id || positionData.id}">
            <span class="text-muted">계산 중...</span>
        </td>
        <td class="text-sm text-muted">
            <span id="last-update-${positionData.position_id || positionData.id}">방금 전</span>
        </td>
        <td>
            ${quantity !== 0 ? `
                <button data-position-id="${positionData.position_id || positionData.id}" class="close-position-btn btn btn-error btn-sm">
                    <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                    청산
                </button>
            ` : '<span class="text-muted text-xs">-</span>'}
        </td>
    `;
    
    // 청산 버튼 이벤트 리스너 추가
    const closeBtn = row.querySelector('.close-position-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            const positionId = this.getAttribute('data-position-id');
            if (typeof closePosition === 'function') {
                closePosition(positionId);
            }
        });
    }
    
    return row;
}

/**
 * Upsert (insert or update) a position row
 */
function upsertPositionRow(positionData) {
    const log = window.logger || console;
    log.info('📈 포지션 upsert 시작:', positionData);
    
    let positionTable = document.querySelector('#positionsTable tbody');
    
    // 테이블이 없으면 에러 대신 경고만 출력
    if (!positionTable) {
        log.error('포지션 테이블을 찾을 수 없습니다. 페이지 구조를 확인하세요.');
        return;
    }
    
    // 빈 상태 메시지가 있으면 제거
    const emptyRow = positionTable.querySelector('.empty-positions-row');
    if (emptyRow) {
        emptyRow.remove();
    }
    
    const positionId = positionData.position_id || positionData.id;
    const existingRow = document.querySelector(`tr[data-position-id="${positionId}"]`);
    
    if (existingRow) {
        log.info('📈 기존 포지션 행 업데이트:', positionId);
        // 기존 행을 새 데이터로 교체
        const newRow = createPositionRow(positionData);
        existingRow.replaceWith(newRow);
        // 업데이트 애니메이션 적용
        newRow.classList.add('highlight-update');
        setTimeout(() => {
            newRow.classList.remove('highlight-update');
        }, 2000);
    } else {
        log.info('📈 새 포지션 행 생성:', positionId);
        // 새 행 생성 및 추가
        const newRow = createPositionRow(positionData);
        positionTable.appendChild(newRow);
        // 새 행 추가 애니메이션 (초록색 배경)
        newRow.classList.add('highlight-new');
        setTimeout(() => {
            newRow.classList.remove('highlight-new');
        }, 2000);
        
        // 새 포지션이 추가되면 웹소켓 구독 시작
        if (positionManager && !existingRow) {
            log.info('📈 새 포지션에 대한 웹소켓 구독 시작:', positionData.symbol);
            positionManager.addPositionDynamic(positionData);
        }
    }
}

/**
 * Remove a position row from the table
 */
function removePositionRow(positionId) {
    const log = window.logger || console;
    const positionRow = document.querySelector(`tr[data-position-id="${positionId}"]`);
    if (!positionRow) {
        log.warn('제거할 포지션 행을 찾을 수 없음:', positionId);
        return;
    }
    
    // 포지션 제거 시 웹소켓 구독 해제
    if (positionManager) {
        log.info('📈 포지션 제거에 따른 웹소켓 구독 해제:', positionId);
        positionManager.removePositionDynamic(positionId);
    }
    
    // 제거 애니메이션
    positionRow.style.transition = 'all 0.3s ease-out';
    positionRow.style.opacity = '0.5';
    positionRow.style.transform = 'translateX(-10px)';
    
    setTimeout(() => {
        positionRow.remove();
        checkEmptyPositions();
        log.info('포지션 행 제거됨:', positionId);
    }, 300);
}

/**
 * Check if positions table is empty and show empty state
 */
function checkEmptyPositions() {
    const positionRows = document.querySelectorAll('tr[data-position-id]');
    if (positionRows.length === 0) {
        showEmptyPositionsState();
        if (typeof showToast === 'function') {
            showToast('모든 포지션이 청산되었습니다.', 'success');
        }
    }
}

/**
 * Show empty positions state in the table
 */
function showEmptyPositionsState() {
    const positionTable = document.querySelector('#positionsTable tbody');
    if (positionTable) {
        // 기존 빈 상태 메시지가 있으면 제거
        const existingEmptyRow = positionTable.querySelector('.empty-positions-row');
        if (existingEmptyRow) {
            existingEmptyRow.remove();
        }
        
        // 새로운 빈 상태 행 추가
        const emptyRow = document.createElement('tr');
        emptyRow.className = 'empty-positions-row';
        emptyRow.innerHTML = `
            <td colspan="9">
                <div class="empty-state" style="padding: 2rem 1rem;">
                    <svg class="empty-state-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <h3>보유 포지션이 없습니다</h3>
                    <p>모든 포지션이 성공적으로 청산되었습니다</p>
                </div>
            </td>
        `;
        positionTable.appendChild(emptyRow);
    }
}

/**
 * Remove empty positions state from the table
 */
function removeEmptyPositionsState() {
    const emptyRow = document.querySelector('.empty-positions-row');
    if (emptyRow) {
        emptyRow.remove();
    }
}

/**
 * Update position statistics
 */
function updatePositionStats() {
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
    
    // 통계 카드 업데이트
    const totalCountElement = document.querySelector('.stats-grid .stats-value');
    if (totalCountElement) {
        totalCountElement.textContent = totalCount;
    }
    
    const longCountElements = document.querySelectorAll('.stats-grid .stats-card:nth-child(2) .stats-value');
    longCountElements.forEach(el => el.textContent = longCount);
    
    const shortCountElements = document.querySelectorAll('.stats-grid .stats-card:nth-child(3) .stats-value');
    shortCountElements.forEach(el => el.textContent = shortCount);
    
    const log = window.logger || console;
    log.debug('포지션 통계 업데이트:', { total: totalCount, long: longCount, short: shortCount });
}

/**
 * Handle position update from SSE
 */
function handlePositionUpdate(data) {
    const log = window.logger || console;
    try {
        log.info('포지션 업데이트 처리:', data);
        
        // 이벤트 타입에 따른 처리
        switch (data.event_type) {
            case 'position_created':
            case 'position_updated':
                upsertPositionRow(data);
                // 웹소켓 구독 동적 관리
                if (positionManager) {
                    positionManager.addPositionDynamic(data);
                }
                break;
            case 'position_closed':
                removePositionRow(data.position_id);
                // 웹소켓 구독 해제
                if (positionManager) {
                    positionManager.removePositionDynamic(data.position_id);
                }
                break;
            default:
                log.warn('알 수 없는 포지션 이벤트 타입:', data.event_type);
        }
        
        // 통계 정보 업데이트
        updatePositionStats();
        
        // 토스트 알림
        const eventTypeText = {
            'position_created': '새 포지션',
            'position_updated': '포지션 업데이트', 
            'position_closed': '포지션 청산'
        }[data.event_type] || '포지션 변경';
        
        if (typeof showToast === 'function') {
            showToast(`${eventTypeText}: ${data.symbol} (${Math.abs(data.quantity)})`, 'success', 2000);
        }
        
    } catch (error) {
        log.error('포지션 업데이트 처리 실패:', error);
    }
}

// ========================================
// Export functions to global scope
// ========================================

window.positionRealtimeUtils = {
    // Manager functions
    initializePositionRealtime,
    getPositionManager,
    
    // UI functions
    createPositionRow,
    upsertPositionRow,
    removePositionRow,
    checkEmptyPositions,
    showEmptyPositionsState,
    removeEmptyPositionsState,
    updatePositionStats,
    handlePositionUpdate,
    
    // Test functions
    getDiagnostics: () => positionManager ? positionManager.getDiagnostics() : null,
    testExchange: (exchange, marketType, symbols) => positionManager ? positionManager.testExchangeConnection(exchange, marketType, symbols) : null,
    runSystemTest: () => positionManager ? positionManager.runSystemTest() : null,
    getManager: () => positionManager
};

// Also export individual functions for backward compatibility
window.initializePositionRealtime = initializePositionRealtime;
window.getPositionManager = getPositionManager;
window.createPositionRow = createPositionRow;
window.upsertPositionRow = upsertPositionRow;
window.removePositionRow = removePositionRow;
window.checkEmptyPositions = checkEmptyPositions;
window.showEmptyPositionsState = showEmptyPositionsState;
window.removeEmptyPositionsState = removeEmptyPositionsState;
window.updatePositionStats = updatePositionStats;
window.handlePositionUpdate = handlePositionUpdate; 