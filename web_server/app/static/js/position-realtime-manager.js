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
        this.positions.forEach((position, key) => {
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

/**
 * Global test functions for easy access from console or UI
 */
window.positionTestUtils = {
    getDiagnostics: () => positionManager ? positionManager.getDiagnostics() : null,
    testExchange: (exchange, marketType, symbols) => positionManager ? positionManager.testExchangeConnection(exchange, marketType, symbols) : null,
    runSystemTest: () => positionManager ? positionManager.runSystemTest() : null,
    getManager: () => positionManager
}; 