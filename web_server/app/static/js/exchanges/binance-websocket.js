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
        this.priceCallbacks = new Map();
        this.subscribedSymbols = new Set();
        
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
    
    subscribeToPrice(symbol, callback) {
        // Normalize symbol for Binance (uppercase, no separator)
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        // Check if already subscribed
        if (this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`Binance ${this.marketType}: Symbol ${normalizedSymbol} already subscribed, skipping duplicate`);
            return normalizedSymbol;
        }
        
        this.log.debug(`Subscribing to Binance ${this.marketType} price for ${normalizedSymbol}`);
        
        // Register callback
        this.priceCallbacks.set(normalizedSymbol, callback);
        this.subscribedSymbols.add(normalizedSymbol);
        
        // Update parent class subscriptions for proper tracking
        const subscriptionKey = `ticker:${normalizedSymbol}`;
        this.subscriptions.set(subscriptionKey, callback);
        
        // Binance all-ticker stream includes all symbols automatically
        // No need to send specific subscription message
        
        this.log.debug(`Binance ${this.marketType} subscription added for ${normalizedSymbol} (total: ${this.subscribedSymbols.size})`);
        
        return normalizedSymbol;
    }
    
    unsubscribeFromPrice(symbol) {
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        this.log.debug(`Unsubscribing from Binance ${this.marketType} price for ${normalizedSymbol}`);
        
        this.priceCallbacks.delete(normalizedSymbol);
        this.subscribedSymbols.delete(normalizedSymbol);
        
        // Update parent class subscriptions
        const subscriptionKey = `ticker:${normalizedSymbol}`;
        this.subscriptions.delete(subscriptionKey);
    }
    
    normalizeSymbol(symbol) {
        // Convert various formats to Binance format
        // e.g., "BTC/USDT" -> "BTCUSDT", "BTC-USDT" -> "BTCUSDT"
        return symbol.replace(/[\/\-_]/g, '').toUpperCase();
    }
    
    // Override subscription methods (not used for all-ticker stream)
    sendSubscription(channel, symbol) {
        // Not needed for all-ticker stream
    }
    
    sendUnsubscription(channel, symbol) {
        // Not needed for all-ticker stream
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