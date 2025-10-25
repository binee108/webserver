/**
 * Binance WebSocket Client
 * Supports both Spot and Futures markets
 */
class BinanceWebSocket extends WebSocketManager {
    constructor(options = {}) {
        const marketType = options.marketType || 'spot'; // 'spot' or 'futures'
        
        // Binance WebSocket URLs
        const urls = {
            spot: 'wss://stream.binance.com:9443/ws/!ticker@arr',
            futures: 'wss://fstream.binance.com/ws/!ticker@arr'
        };
        
        super(urls[marketType], {
            ...options,
            pingInterval: 180000, // 3 minutes for Binance
            pongTimeout: 10000
        });
        
        this.marketType = marketType;
        
        // Use logger if available, fallback to console
        this.log = window.logger || console;
    }
    
    // Override base class methods for Binance-specific implementation
    sendPing() {
        // Binance uses ping/pong frame, not JSON message
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.ping();
        }
    }
    
    handleMessage(data) {
        super.handleMessage(data);
        
        // Handle Binance ticker data
        if (Array.isArray(data)) {
            // Multiple ticker data
            data.forEach(ticker => this.handleTickerData(ticker));
        } else if (data.e === '24hrTicker') {
            // Single ticker data
            this.handleTickerData(data);
        }
    }
    
    handleTickerData(ticker) {
        const symbol = ticker.s; // symbol
        const price = parseFloat(ticker.c); // close price
        const priceChange = parseFloat(ticker.P); // price change percent
        
        // Call registered callbacks for this symbol
        const callback = this.priceCallbacks.get(symbol);
        if (callback) {
            callback({
                symbol: symbol,
                price: price,
                priceChangePercent: priceChange,
                timestamp: Date.now(),
                exchange: 'binance'
            });
        }
    }
    
    /**
     * Subscribe to price updates (unified interface)
     * Overrides base class method
     */
    subscribePrice(symbol, callback) {
        // Normalize symbol for Binance (uppercase, no separator)
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        // Check if already subscribed
        if (this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`Binance ${this.marketType}: Symbol ${normalizedSymbol} already subscribed`);
            return normalizedSymbol;
        }
        
        this.log.debug(`Subscribing to Binance ${this.marketType} price for ${normalizedSymbol}`);
        
        // Register callback and track subscription
        this.priceCallbacks.set(normalizedSymbol, callback);
        this.subscribedSymbols.add(normalizedSymbol);
        
        // Binance all-ticker stream includes all symbols automatically
        // No need to send specific subscription message
        
        this.log.debug(`Binance ${this.marketType} subscription added for ${normalizedSymbol} (total: ${this.subscribedSymbols.size})`);
        
        return normalizedSymbol;
    }
    
    /**
     * Unsubscribe from price updates (unified interface)
     * Overrides base class method
     */
    unsubscribePrice(symbol) {
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        if (!this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`Binance ${this.marketType}: Cannot unsubscribe ${normalizedSymbol} - not subscribed`);
            return false;
        }
        
        this.log.debug(`Unsubscribing from Binance ${this.marketType} price for ${normalizedSymbol}`);
        
        // Remove callback and tracking
        this.priceCallbacks.delete(normalizedSymbol);
        this.subscribedSymbols.delete(normalizedSymbol);
        
        // Binance all-ticker stream - no need to send unsubscribe message
        
        this.log.debug(`Binance ${this.marketType} unsubscribed from ${normalizedSymbol} (remaining: ${this.subscribedSymbols.size})`);
        return true;
    }
    
    /**
     * @deprecated Use subscribePrice() instead
     */
    subscribeToPrice(symbol, callback) {
        return this.subscribePrice(symbol, callback);
    }
    
    /**
     * @deprecated Use unsubscribePrice() instead
     */
    unsubscribeFromPrice(symbol) {
        return this.unsubscribePrice(symbol);
    }
    
    /**
     * Normalize symbol for Binance format
     * Overrides base class method
     */
    normalizeSymbol(symbol) {
        // Convert various formats to Binance format
        // e.g., "BTC/USDT" -> "BTCUSDT", "BTC-USDT" -> "BTCUSDT"
        return symbol.replace(/[\/\-_]/g, '').toUpperCase();
    }
    
    /**
     * Send price subscription message
     * Overrides base class method
     */
    sendPriceSubscription(normalizedSymbol) {
        // Binance all-ticker stream includes all symbols automatically
        // No need to send specific subscription message
    }
    
    /**
     * Send price unsubscription message
     * Overrides base class method
     */
    sendPriceUnsubscription(normalizedSymbol) {
        // Binance all-ticker stream - no need to send unsubscribe message
    }
    
    // Override old subscription methods (not used for all-ticker stream)
    sendSubscription(channel, symbol) {
        // Not needed for all-ticker stream
    }
    
    sendUnsubscription(channel, symbol) {
        // Not needed for all-ticker stream
    }
    
    /**
     * Check if symbol is subscribed
     * Overrides base class method
     */
    isSubscribed(symbol) {
        const normalizedSymbol = this.normalizeSymbol(symbol);
        return this.subscribedSymbols.has(normalizedSymbol);
    }
}

/**
 * Factory function to create Binance WebSocket instances
 */
function createBinanceWebSocket(marketType = 'spot', options = {}) {
    return new BinanceWebSocket({
        marketType: marketType,
        ...options
    });
}

// Export to global scope
window.BinanceWebSocket = BinanceWebSocket; 