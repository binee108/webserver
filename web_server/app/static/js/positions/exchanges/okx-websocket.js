/**
 * OKX WebSocket Client (V5 API)
 * Supports Spot, Futures, and Swap markets
 */
class OkxWebSocket extends WebSocketManager {
    constructor(options = {}) {
        // OKX uses a single WebSocket URL for all markets
        const url = 'wss://ws.okx.com:8443/ws/v5/public';
        
        super(url, {
            ...options,
            pingInterval: 30000, // 30 seconds for OKX
            pongTimeout: 10000
        });
        
        this.marketType = options.marketType || 'spot'; // 'spot', 'futures', 'swap'
        this.requestId = Date.now();
        
        // Use logger if available, fallback to console
        this.log = window.logger || console;
    }
    
    // Override base class methods for OKX-specific implementation
    sendPing() {
        this.send('ping');
    }
    
    handleMessage(data) {
        super.handleMessage(data);
        
        // Handle OKX messages
        if (data === 'pong') {
            this.handlePong();
            return;
        }
        
        // Handle ticker data
        if (data.arg && data.arg.channel === 'tickers' && data.data) {
            this.handleTickerData(data);
        }
        
        // Handle subscription responses
        if (data.event === 'subscribe') {
            if (data.code === '0') {
                this.log.debug('OKX subscription successful:', data);
            } else {
                this.log.error('OKX subscription failed:', data);
            }
        }
    }
    
    handleTickerData(message) {
        if (!message.data || !Array.isArray(message.data)) return;
        
        message.data.forEach(ticker => {
            const symbol = ticker.instId;
            const price = parseFloat(ticker.last);
            const priceChange = parseFloat(ticker.sodUtc8 || 0); // 24h price change in percentage
            
            // Call registered callbacks for this symbol
            const callback = this.priceCallbacks.get(symbol);
            if (callback) {
                callback({
                    symbol: symbol,
                    price: price,
                    priceChangePercent: priceChange,
                    timestamp: parseInt(ticker.ts),
                    exchange: 'okx'
                });
            }
        });
    }
    
    /**
     * Subscribe to price updates (unified interface)
     * Overrides base class method
     */
    subscribePrice(symbol, callback) {
        // Normalize symbol for OKX
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        // Check if already subscribed
        if (this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`OKX ${this.marketType}: Symbol ${normalizedSymbol} already subscribed`);
            return normalizedSymbol;
        }
        
        this.log.debug(`Subscribing to OKX ${this.marketType} price for ${normalizedSymbol}`);
        
        // Register callback and track subscription
        this.priceCallbacks.set(normalizedSymbol, callback);
        this.subscribedSymbols.add(normalizedSymbol);
        
        // Send subscription message
        this.sendPriceSubscription(normalizedSymbol);
        
        this.log.debug(`OKX ${this.marketType} subscription added for ${normalizedSymbol} (total: ${this.subscribedSymbols.size})`);
        
        return normalizedSymbol;
    }
    
    /**
     * Unsubscribe from price updates (unified interface)
     * Overrides base class method
     */
    unsubscribePrice(symbol) {
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        if (!this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`OKX ${this.marketType}: Cannot unsubscribe ${normalizedSymbol} - not subscribed`);
            return false;
        }
        
        this.log.debug(`Unsubscribing from OKX ${this.marketType} price for ${normalizedSymbol}`);
        
        // Remove callback and tracking
        this.priceCallbacks.delete(normalizedSymbol);
        this.subscribedSymbols.delete(normalizedSymbol);
        
        // Send unsubscription message
        this.sendPriceUnsubscription(normalizedSymbol);
        
        this.log.debug(`OKX ${this.marketType} unsubscribed from ${normalizedSymbol} (remaining: ${this.subscribedSymbols.size})`);
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
     * Normalize symbol for OKX format
     * Overrides base class method
     */
    normalizeSymbol(symbol) {
        // Convert various formats to OKX format
        if (this.marketType === 'spot') {
            // Spot: "BTC-USDT"
            return symbol.replace(/[\/\_]/g, '-').toUpperCase();
        } else if (this.marketType === 'futures') {
            // Futures: "BTC-USDT-240329" (with expiry date)
            // For perpetual contracts: "BTC-USDT-SWAP"
            if (symbol.includes('PERP') || symbol.includes('SWAP')) {
                return symbol.replace(/[\/\_]/g, '-').replace('PERP', 'SWAP').toUpperCase();
            } else {
                return symbol.replace(/[\/\_]/g, '-').toUpperCase();
            }
        } else if (this.marketType === 'swap') {
            // Swap (Perpetual): "BTC-USDT-SWAP"
            if (!symbol.includes('SWAP')) {
                return symbol.replace(/[\/\_]/g, '-').toUpperCase() + '-SWAP';
            }
            return symbol.replace(/[\/\_]/g, '-').toUpperCase();
        }
        
        return symbol.replace(/[\/\_]/g, '-').toUpperCase();
    }
    
    /**
     * Send price subscription message
     * Overrides base class method
     */
    sendPriceSubscription(normalizedSymbol) {
        this.send({
            op: 'subscribe',
            args: [{
                channel: 'tickers',
                instId: normalizedSymbol
            }],
            id: this.getNextRequestId()
        });
    }
    
    /**
     * Send price unsubscription message
     * Overrides base class method
     */
    sendPriceUnsubscription(normalizedSymbol) {
        this.send({
            op: 'unsubscribe',
            args: [{
                channel: 'tickers',
                instId: normalizedSymbol
            }],
            id: this.getNextRequestId()
        });
    }
    
    // Override old subscription methods
    sendSubscription(channel, symbol) {
        this.send({
            op: 'subscribe',
            args: [{
                channel: channel,
                instId: symbol
            }],
            id: this.getNextRequestId()
        });
    }
    
    sendUnsubscription(channel, symbol) {
        this.send({
            op: 'unsubscribe',
            args: [{
                channel: channel,
                instId: symbol
            }],
            id: this.getNextRequestId()
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
    authenticate(apiKey, secretKey, passphrase) {
        const timestamp = Date.now() / 1000;
        const method = 'GET';
        const requestPath = '/users/self/verify';
        const body = '';
        
        const signature = this.generateSignature(timestamp, method, requestPath, body, secretKey);
        
        this.send({
            op: 'login',
            args: [{
                apiKey: apiKey,
                passphrase: passphrase,
                timestamp: timestamp.toString(),
                sign: signature
            }]
        });
    }
    
    generateSignature(timestamp, method, requestPath, body, secretKey) {
        // OKX signature generation would be implemented here
        // For public channels, authentication is not required
        return '';
    }
}

/**
 * Factory function to create OKX WebSocket instances
 */
function createOkxWebSocket(marketType = 'spot', options = {}) {
        return new OkxWebSocket({
        marketType: marketType,
        ...options
    });
}

// Export to global scope
window.OkxWebSocket = OkxWebSocket; 