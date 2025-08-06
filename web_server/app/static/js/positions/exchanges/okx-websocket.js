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
        this.priceCallbacks = new Map();
        this.subscribedSymbols = new Set();
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
    
    subscribeToPrice(symbol, callback) {
        // Normalize symbol for OKX
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        // Check if already subscribed
        if (this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`OKX ${this.marketType}: Symbol ${normalizedSymbol} already subscribed, skipping duplicate`);
            return normalizedSymbol;
        }
        
        this.log.debug(`Subscribing to OKX ${this.marketType} price for ${normalizedSymbol}`);
        
        // Register callback
        this.priceCallbacks.set(normalizedSymbol, callback);
        this.subscribedSymbols.add(normalizedSymbol);
        
        // Update parent class subscriptions for proper tracking
        const subscriptionKey = `tickers:${normalizedSymbol}`;
        this.subscriptions.set(subscriptionKey, callback);
        
        // Subscribe to ticker channel
        this.send({
            op: 'subscribe',
            args: [{
                channel: 'tickers',
                instId: normalizedSymbol
            }],
            id: this.getNextRequestId()
        });
        
        this.log.debug(`OKX ${this.marketType} subscription added for ${normalizedSymbol} (total: ${this.subscribedSymbols.size})`);
        
        return normalizedSymbol;
    }
    
    unsubscribeFromPrice(symbol) {
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        this.log.debug(`Unsubscribing from OKX ${this.marketType} price for ${normalizedSymbol}`);
        
        this.priceCallbacks.delete(normalizedSymbol);
        this.subscribedSymbols.delete(normalizedSymbol);
        
        // Update parent class subscriptions
        const subscriptionKey = `tickers:${normalizedSymbol}`;
        this.subscriptions.delete(subscriptionKey);
        
        // Unsubscribe from ticker channel
        this.send({
            op: 'unsubscribe',
            args: [{
                channel: 'tickers',
                instId: normalizedSymbol
            }],
            id: this.getNextRequestId()
        });
    }
    
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
    
    // Override subscription methods
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
    
    // Get current subscribed symbols
    getSubscribedSymbols() {
        return Array.from(this.subscribedSymbols);
    }
    
    // Check if symbol is subscribed
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