/**
 * Base WebSocket Manager Class
 * Handles connection, reconnection, and subscription management
 */
class WebSocketManager {
    constructor(url, options = {}) {
        this.url = url;
        this.ws = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
        this.reconnectInterval = options.reconnectInterval || 5000;
        this.pingInterval = options.pingInterval || 30000;
        this.pongTimeout = options.pongTimeout || 10000;
        
        // Callback functions
        this.onOpen = options.onOpen || (() => {});
        this.onMessage = options.onMessage || (() => {});
        this.onError = options.onError || (() => {});
        this.onClose = options.onClose || (() => {});
        
        // Subscription management
        this.subscriptions = new Map();
        this.messageQueue = [];
        
        // Price subscription tracking (unified interface)
        this.priceCallbacks = new Map();
        this.subscribedSymbols = new Set();
        
        // Ping/Pong management
        this.pingTimer = null;
        this.pongTimer = null;
        
        // Use logger if available, fallback to console
        this.log = window.logger || console;
        
        this.connect();
    }
    
    connect() {
        try {
            this.log.debug(`Connecting to WebSocket: ${this.url}`);
            this.ws = new WebSocket(this.url);
            
            this.ws.onopen = (event) => {
                this.log.connection(`WebSocket connected: ${this.url}`);
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.startPing();
                this.processMessageQueue();
                this.onOpen(event);
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    this.log.error('Failed to parse WebSocket message:', error);
                }
            };
            
            this.ws.onerror = (error) => {
                this.log.error(`WebSocket error: ${this.url}`, error);
                this.onError(error);
            };
            
            this.ws.onclose = (event) => {
                this.log.warn(`WebSocket closed: ${this.url}`, event);
                this.isConnected = false;
                this.stopPing();
                this.handleReconnect();
                this.onClose(event);
            };
            
        } catch (error) {
            this.log.error('Failed to create WebSocket connection:', error);
            this.handleReconnect();
        }
    }
    
    handleMessage(data) {
        // Handle pong messages
        if (data.pong || data.result === 'pong') {
            this.handlePong();
            return;
        }
        
        // Call the onMessage callback
        this.onMessage(data);
    }
    
    send(message) {
        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            // Queue message for later sending
            this.messageQueue.push(message);
            this.log.debug('Message queued for later sending:', message);
        }
    }
    
    /**
     * @deprecated Use subscribePrice() instead
     */
    subscribe(channel, symbol, callback) {
        // For backward compatibility, redirect to new interface if it's a price subscription
        if (channel === 'ticker' || channel === 'tickers') {
            return this.subscribePrice(symbol, callback);
        }
        
        const subscriptionKey = `${channel}:${symbol}`;
        
        // Check for duplicate subscription
        if (this.subscriptions.has(subscriptionKey)) {
            this.log.warn(`Duplicate subscription attempt: ${subscriptionKey} already exists`);
            return false;
        }
        
        this.subscriptions.set(subscriptionKey, callback);
        
        // Send subscription message (implementation varies by exchange)
        this.sendSubscription(channel, symbol);
        
        this.log.debug(`Subscription added: ${subscriptionKey} (total: ${this.subscriptions.size})`);
        return true;
    }
    
    /**
     * @deprecated Use unsubscribePrice() instead
     */
    unsubscribe(channel, symbol) {
        // For backward compatibility, redirect to new interface if it's a price subscription
        if (channel === 'ticker' || channel === 'tickers') {
            return this.unsubscribePrice(symbol);
        }
        
        const subscriptionKey = `${channel}:${symbol}`;
        
        if (!this.subscriptions.has(subscriptionKey)) {
            this.log.warn(`Cannot unsubscribe: ${subscriptionKey} not found`);
            return false;
        }
        
        this.subscriptions.delete(subscriptionKey);
        
        // Send unsubscription message (implementation varies by exchange)
        this.sendUnsubscription(channel, symbol);
        
        this.log.debug(`Unsubscribed: ${subscriptionKey} (remaining: ${this.subscriptions.size})`);
        return true;
    }
    
    // Check if a symbol is already subscribed
    isSubscribed(channel, symbol) {
        const subscriptionKey = `${channel}:${symbol}`;
        return this.subscriptions.has(subscriptionKey);
    }
    
    // Get all subscription keys for debugging
    getSubscriptionKeys() {
        return Array.from(this.subscriptions.keys());
    }
    
    // Check for duplicate subscriptions (debugging utility)
    checkDuplicateSubscriptions() {
        const keys = this.getSubscriptionKeys();
        const duplicates = {};
        
        keys.forEach(key => {
            const parts = key.split(':');
            if (parts.length >= 2) {
                const symbol = parts[1];
                if (!duplicates[symbol]) {
                    duplicates[symbol] = [];
                }
                duplicates[symbol].push(key);
            }
        });
        
        const duplicateSymbols = Object.entries(duplicates)
            .filter(([symbol, keys]) => keys.length > 1);
        
        if (duplicateSymbols.length > 0) {
            this.log.warn('Duplicate subscriptions found:', duplicateSymbols);
            return duplicateSymbols;
        } else {
            this.log.debug('No duplicate subscriptions found');
            return [];
        }
    }
    
    sendSubscription(channel, symbol) {
        // Override in exchange-specific implementations
        throw new Error('sendSubscription must be implemented by subclass');
    }
    
    sendUnsubscription(channel, symbol) {
        // Override in exchange-specific implementations
        throw new Error('sendUnsubscription must be implemented by subclass');
    }
    
    processMessageQueue() {
        if (this.messageQueue.length > 0) {
            this.log.debug(`Processing ${this.messageQueue.length} queued messages`);
        }
        
        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            this.send(message);
        }
    }
    
    startPing() {
        this.pingTimer = setInterval(() => {
            if (this.isConnected) {
                this.sendPing();
                this.waitForPong();
            }
        }, this.pingInterval);
    }
    
    stopPing() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
        if (this.pongTimer) {
            clearTimeout(this.pongTimer);
            this.pongTimer = null;
        }
    }
    
    sendPing() {
        // Override in exchange-specific implementations
        this.send({ ping: Date.now() });
    }
    
    waitForPong() {
        this.pongTimer = setTimeout(() => {
            this.log.warn('Pong timeout, reconnecting...');
            this.reconnect();
        }, this.pongTimeout);
    }
    
    handlePong() {
        if (this.pongTimer) {
            clearTimeout(this.pongTimer);
            this.pongTimer = null;
        }
    }
    
    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.log.info(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
            
            setTimeout(() => {
                this.connect();
            }, this.reconnectInterval * this.reconnectAttempts);
        } else {
            this.log.error(`Max reconnection attempts reached for ${this.url}`);
        }
    }
    
    reconnect() {
        if (this.ws) {
            this.ws.close();
        }
        this.connect();
    }
    
    close() {
        this.stopPing();
        if (this.ws) {
            this.ws.close();
        }
    }
    
    // Utility method to get connection status
    getStatus() {
        return {
            connected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts,
            subscriptionsCount: this.subscriptions.size,
            subscribedSymbols: this.getSubscribedSymbols()
        };
    }
    
    // Get list of subscribed symbols
    getSubscribedSymbols() {
        return Array.from(this.subscribedSymbols);
    }
    
    // ========================================
    // Unified Price Subscription Interface
    // ========================================
    
    /**
     * Subscribe to price updates for a symbol (unified interface)
     * All exchange implementations should override this method
     * @param {string} symbol - The trading symbol
     * @param {function} callback - Callback for price updates
     * @returns {string} Normalized symbol
     */
    subscribePrice(symbol, callback) {
        // Normalize symbol (can be overridden by subclasses)
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        // Check if already subscribed
        if (this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`Symbol ${normalizedSymbol} already subscribed`);
            return normalizedSymbol;
        }
        
        // Register callback and track subscription
        this.priceCallbacks.set(normalizedSymbol, callback);
        this.subscribedSymbols.add(normalizedSymbol);
        
        // Call exchange-specific implementation
        this.sendPriceSubscription(normalizedSymbol);
        
        this.log.debug(`Price subscription added for ${normalizedSymbol}`);
        return normalizedSymbol;
    }
    
    /**
     * Unsubscribe from price updates for a symbol (unified interface)
     * All exchange implementations should override this method
     * @param {string} symbol - The trading symbol
     * @returns {boolean} Success status
     */
    unsubscribePrice(symbol) {
        // Normalize symbol
        const normalizedSymbol = this.normalizeSymbol(symbol);
        
        if (!this.subscribedSymbols.has(normalizedSymbol)) {
            this.log.warn(`Cannot unsubscribe: ${normalizedSymbol} not subscribed`);
            return false;
        }
        
        // Remove callback and tracking
        this.priceCallbacks.delete(normalizedSymbol);
        this.subscribedSymbols.delete(normalizedSymbol);
        
        // Call exchange-specific implementation
        this.sendPriceUnsubscription(normalizedSymbol);
        
        this.log.debug(`Price subscription removed for ${normalizedSymbol}`);
        return true;
    }
    
    /**
     * Check if a symbol is subscribed
     * @param {string} symbol - The trading symbol
     * @returns {boolean} Subscription status
     */
    isSubscribed(symbol) {
        const normalizedSymbol = this.normalizeSymbol(symbol);
        return this.subscribedSymbols.has(normalizedSymbol);
    }
    
    /**
     * Normalize symbol format (override in subclasses for exchange-specific formats)
     * @param {string} symbol - The trading symbol
     * @returns {string} Normalized symbol
     */
    normalizeSymbol(symbol) {
        // Default normalization: remove separators, uppercase
        return symbol.replace(/[\/-_]/g, '').toUpperCase();
    }
    
    /**
     * Send price subscription message (must be implemented by subclasses)
     * @param {string} normalizedSymbol - The normalized symbol
     */
    sendPriceSubscription(normalizedSymbol) {
        // Override in exchange-specific implementations
        this.log.warn('sendPriceSubscription must be implemented by subclass');
    }
    
    /**
     * Send price unsubscription message (must be implemented by subclasses)
     * @param {string} normalizedSymbol - The normalized symbol
     */
    sendPriceUnsubscription(normalizedSymbol) {
        // Override in exchange-specific implementations
        this.log.warn('sendPriceUnsubscription must be implemented by subclass');
    }
}

// Export to global scope
window.WebSocketManager = WebSocketManager; 