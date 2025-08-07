/**
 * Bybit WebSocket Client (V5 API)
 * Supports Spot, USDT Perpetual, and Inverse Perpetual markets
 */
class BybitWebSocket extends WebSocketManager {
    constructor(options = {}) {
        const marketType = options.marketType || 'spot'; // 'spot', 'linear', 'inverse'
        
        // Bybit V5 WebSocket URLs
        const urls = {
            spot: 'wss://stream.bybit.com/v5/public/spot',
            linear: 'wss://stream.bybit.com/v5/public/linear',
            inverse: 'wss://stream.bybit.com/v5/public/inverse'
        };
        
        super(urls[marketType], {
            ...options,
            pingInterval: 20000, // 20 seconds for Bybit
            pongTimeout: 10000
        });
        
        this.marketType = marketType;
        this.requestId = 1;
        
        // Use logger if available, fallback to console
        this.log = window.logger || console;
    }
    
    // Override base class methods for Bybit-specific implementation
    sendPing() {
        this.send({
            op: 'ping',
            req_id: this.getNextRequestId()
        });
    }
    
    handleMessage(data) {
        super.handleMessage(data);
        
        // Handle Bybit messages
        if (data.op === 'pong') {
            this.handlePong();
            return;
        }
        
        if (data.topic && data.topic.startsWith('tickers.')) {
            this.handleTickerData(data);
        }
        
        // Handle subscription responses
        if (data.op === 'subscribe' && data.success) {
            this.log.debug('Bybit subscription successful:', data);
        }
    }
    
    handleTickerData(data) {
        if (!data.data) return;
        
        const ticker = data.data;
        const symbol = ticker.symbol;
        const price = parseFloat(ticker.lastPrice);
        const priceChange = parseFloat(ticker.price24hPcnt || 0) * 100; // Convert to percentage
        
        // Call registered callbacks for this symbol
        const callback = this.priceCallbacks.get(symbol);
        if (callback) {
            callback({
                symbol: symbol,
                price: price,
                priceChangePercent: priceChange,
                timestamp: Date.now(),
                exchange: 'bybit'
            });
        }
    }
    
    /**
     * Subscribe to price updates (unified interface)
     * Overrides base class method
     */
    subscribePrice(symbol, callback) {
        // Normalize symbol for Bybit
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        // Check if already subscribed
        if (this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`Bybit ${this.marketType}: Symbol ${normalizedSymbol} already subscribed`);
            return normalizedSymbol;
        }
        
        this.log.debug(`Subscribing to Bybit ${this.marketType} price for ${normalizedSymbol}`);
        
        // Register callback and track subscription
        this.priceCallbacks.set(normalizedSymbol, callback);
        this.subscribedSymbols.add(normalizedSymbol);
        
        // Send subscription message
        this.sendPriceSubscription(normalizedSymbol);
        
        this.log.debug(`Bybit ${this.marketType} subscription added for ${normalizedSymbol} (total: ${this.subscribedSymbols.size})`);
        
        return normalizedSymbol;
    }
    
    /**
     * Unsubscribe from price updates (unified interface)
     * Overrides base class method
     */
    unsubscribePrice(symbol) {
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        if (!this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`Bybit ${this.marketType}: Cannot unsubscribe ${normalizedSymbol} - not subscribed`);
            return false;
        }
        
        this.log.debug(`Unsubscribing from Bybit ${this.marketType} price for ${normalizedSymbol}`);
        
        // Remove callback and tracking
        this.priceCallbacks.delete(normalizedSymbol);
        this.subscribedSymbols.delete(normalizedSymbol);
        
        // Send unsubscription message
        this.sendPriceUnsubscription(normalizedSymbol);
        
        this.log.debug(`Bybit ${this.marketType} unsubscribed from ${normalizedSymbol} (remaining: ${this.subscribedSymbols.size})`);
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
     * Normalize symbol for Bybit format
     * Overrides base class method
     */
    normalizeSymbol(symbol) {
        // Convert various formats to Bybit format
        // Bybit uses different formats for different markets
        if (this.marketType === 'spot') {
            // Spot: "BTCUSDT"
            return symbol.replace(/[\/\-_]/g, '').toUpperCase();
        } else {
            // Futures: "BTCUSDT", "BTCUSD"
            return symbol.replace(/[\/\-_]/g, '').toUpperCase();
        }
    }
    
    /**
     * Send price subscription message
     * Overrides base class method
     */
    sendPriceSubscription(normalizedSymbol) {
        this.send({
            op: 'subscribe',
            args: [`tickers.${normalizedSymbol}`],
            req_id: this.getNextRequestId()
        });
    }
    
    /**
     * Send price unsubscription message
     * Overrides base class method
     */
    sendPriceUnsubscription(normalizedSymbol) {
        this.send({
            op: 'unsubscribe',
            args: [`tickers.${normalizedSymbol}`],
            req_id: this.getNextRequestId()
        });
    }
    
    // Override old subscription methods
    sendSubscription(channel, symbol) {
        this.send({
            op: 'subscribe',
            args: [`${channel}.${symbol}`],
            req_id: this.getNextRequestId()
        });
    }
    
    sendUnsubscription(channel, symbol) {
        this.send({
            op: 'unsubscribe',
            args: [`${channel}.${symbol}`],
            req_id: this.getNextRequestId()
        });
    }
    
    getNextRequestId() {
        return String(this.requestId++);
    }
    
    /**
     * Check if symbol is subscribed
     * Overrides base class method
     */
    isSubscribed(symbol) {
        const normalizedSymbol = this.normalizeSymbol(symbol);
        return this.subscribedSymbols.has(normalizedSymbol);
    }
    
    // Handle connection authentication (if needed for private channels)
    authenticate(apiKey, apiSecret) {
        const timestamp = Date.now();
        const signature = this.generateSignature(apiKey, apiSecret, timestamp);
        
        this.send({
            op: 'auth',
            args: [apiKey, timestamp, signature],
            req_id: this.getNextRequestId()
        });
    }
    
    generateSignature(apiKey, apiSecret, timestamp) {
        // Bybit signature generation would be implemented here
        // For public channels, authentication is not required
        return '';
    }
}

/**
 * Factory function to create Bybit WebSocket instances
 */
function createBybitWebSocket(marketType = 'spot', options = {}) {
    return new BybitWebSocket({
        marketType: marketType,
        ...options
    });
}

// Export to global scope
window.BybitWebSocket = BybitWebSocket; 