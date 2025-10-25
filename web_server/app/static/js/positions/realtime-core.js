/**
 * Real-time Core Utilities
 * 실시간 업데이트 시스템의 공통 유틸리티 함수들
 */

// ========================================
// Logging System
// ========================================

const RealtimeLogger = {
    debug: (...args) => {
        if (window.logger && window.logger.debug) {
            window.logger.debug(...args);
        } else {
            console.debug(...args);
        }
    },
    
    info: (...args) => {
        if (window.logger && window.logger.info) {
            window.logger.info(...args);
        } else {
            console.info(...args);
        }
    },
    
    warn: (...args) => {
        if (window.logger && window.logger.warn) {
            window.logger.warn(...args);
        } else {
            console.warn(...args);
        }
    },
    
    error: (...args) => {
        if (window.logger && window.logger.error) {
            window.logger.error(...args);
        } else {
            console.error(...args);
        }
    },
    
    success: (...args) => {
        if (window.logger && window.logger.success) {
            window.logger.success(...args);
        } else {
            console.log('✅', ...args);
        }
    }
};

// ========================================
// Toast Notification System
// ========================================

// showToast는 toast.js에서 전역으로 제공됨
// Legacy support
function showNotification(message, type = 'info') {
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    }
}

// ========================================
// DOM Utilities
// ========================================

const DOMUtils = {
    /**
     * Safely query selector with error handling
     */
    querySelector: (selector, parent = document) => {
        try {
            return parent.querySelector(selector);
        } catch (error) {
            RealtimeLogger.error(`Invalid selector: ${selector}`, error);
            return null;
        }
    },
    
    /**
     * Safely query all selectors
     */
    querySelectorAll: (selector, parent = document) => {
        try {
            return parent.querySelectorAll(selector);
        } catch (error) {
            RealtimeLogger.error(`Invalid selector: ${selector}`, error);
            return [];
        }
    },
    
    /**
     * Create element with attributes and content
     */
    createElement: (tag, attributes = {}, innerHTML = '') => {
        const element = document.createElement(tag);
        Object.entries(attributes).forEach(([key, value]) => {
            if (key === 'className') {
                element.className = value;
            } else if (key === 'dataset') {
                Object.entries(value).forEach(([dataKey, dataValue]) => {
                    element.dataset[dataKey] = dataValue;
                });
            } else {
                element.setAttribute(key, value);
            }
        });
        if (innerHTML) {
            element.innerHTML = innerHTML;
        }
        return element;
    },
    
    /**
     * Add animation class temporarily
     */
    addTemporaryClass: (element, className, duration = 2000) => {
        if (!element) return;
        element.classList.add(className);
        setTimeout(() => {
            element.classList.remove(className);
        }, duration);
    },
    
    /**
     * Highlight cell with animation
     */
    highlightCell: (cell, type = 'updated') => {
        if (!cell) return;
        const className = type === 'updated' ? 'highlight-update' : 
                         type === 'new' ? 'highlight-new' : 'highlight-error';
        DOMUtils.addTemporaryClass(cell, className);
    }
};

// ========================================
// Format Utilities
// ========================================

const FormatUtils = {
    /**
     * Format number with fixed decimal places
     */
    formatNumber: (value, decimals = 2) => {
        const num = parseFloat(value);
        if (isNaN(num)) return '0';
        return num.toFixed(decimals);
    },
    
    /**
     * Format price with currency symbol
     */
    formatPrice: (value, decimals = 4) => {
        return `$${FormatUtils.formatNumber(value, decimals)}`;
    },
    
    /**
     * Format percentage
     */
    formatPercent: (value, decimals = 2) => {
        const num = parseFloat(value);
        if (isNaN(num)) return '0%';
        const sign = num >= 0 ? '+' : '';
        return `${sign}${num.toFixed(decimals)}%`;
    },
    
    /**
     * Format quantity
     */
    formatQuantity: (value, decimals = 8) => {
        const num = Math.abs(parseFloat(value));
        if (isNaN(num)) return '0';
        return num.toFixed(decimals);
    },
    
    /**
     * Format timestamp to local time
     */
    formatTime: (timestamp) => {
        if (!timestamp) return '방금 전';
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    }
};

// ========================================
// CSRF Token Management
// ========================================

function getCSRFToken() {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.getAttribute('content') : '';
}

// ========================================
// API Utilities
// ========================================

const APIUtils = {
    /**
     * Make API request with error handling
     */
    request: async (url, options = {}) => {
        try {
            const defaultOptions = {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                }
            };
            
            const response = await fetch(url, { ...defaultOptions, ...options });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            return data;
            
        } catch (error) {
            RealtimeLogger.error(`API request failed: ${url}`, error);
            throw error;
        }
    },
    
    /**
     * GET request
     */
    get: (url) => {
        return APIUtils.request(url, { method: 'GET' });
    },
    
    /**
     * POST request
     */
    post: (url, body = {}) => {
        return APIUtils.request(url, {
            method: 'POST',
            body: JSON.stringify(body)
        });
    },
    
    /**
     * DELETE request
     */
    delete: (url) => {
        return APIUtils.request(url, { method: 'DELETE' });
    }
};

// ========================================
// Event Bus for Module Communication
// ========================================

class EventBus {
    constructor() {
        this.events = {};
    }
    
    on(event, callback) {
        if (!this.events[event]) {
            this.events[event] = [];
        }
        this.events[event].push(callback);
        return this; // For chaining
    }
    
    off(event, callback) {
        if (this.events[event]) {
            this.events[event] = this.events[event].filter(cb => cb !== callback);
        }
        return this;
    }
    
    emit(event, data) {
        if (this.events[event]) {
            this.events[event].forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    RealtimeLogger.error(`Error in event handler for ${event}:`, error);
                }
            });
        }
        return this;
    }
    
    once(event, callback) {
        const onceWrapper = (data) => {
            callback(data);
            this.off(event, onceWrapper);
        };
        return this.on(event, onceWrapper);
    }
}

// Global event bus instance
const realtimeEventBus = new EventBus();

// ========================================
// Connection Status Management
// ========================================

const ConnectionStatus = {
    CONNECTING: 'connecting',
    CONNECTED: 'connected',
    DISCONNECTED: 'disconnected',
    ERROR: 'error',
    RECONNECTING: 'reconnecting'
};

class ConnectionManager {
    constructor(name) {
        this.name = name;
        this.status = ConnectionStatus.DISCONNECTED;
        this.listeners = [];
    }
    
    setStatus(status) {
        const oldStatus = this.status;
        this.status = status;
        
        if (oldStatus !== status) {
            this.notifyListeners(status, oldStatus);
            realtimeEventBus.emit('connection-status-changed', {
                name: this.name,
                status: status,
                oldStatus: oldStatus
            });
        }
    }
    
    getStatus() {
        return this.status;
    }
    
    isConnected() {
        return this.status === ConnectionStatus.CONNECTED;
    }
    
    onStatusChange(callback) {
        this.listeners.push(callback);
        return () => {
            this.listeners = this.listeners.filter(cb => cb !== callback);
        };
    }
    
    notifyListeners(status, oldStatus) {
        this.listeners.forEach(callback => {
            try {
                callback(status, oldStatus);
            } catch (error) {
                RealtimeLogger.error(`Error in connection status listener:`, error);
            }
        });
    }
}

// ========================================
// Debounce and Throttle Utilities
// ========================================

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// ========================================
// Export to Global Scope
// ========================================

window.RealtimeCore = {
    // Logger
    logger: RealtimeLogger,
    
    // UI
    showToast,
    showNotification,
    
    // DOM
    DOM: DOMUtils,
    
    // Formatting
    format: FormatUtils,
    
    // API
    api: APIUtils,
    
    // CSRF
    getCSRFToken,
    
    // Events
    eventBus: realtimeEventBus,
    EventBus,
    
    // Connection
    ConnectionStatus,
    ConnectionManager,
    
    // Utils
    debounce,
    throttle
};

// Also export individual items for backward compatibility
window.showToast = showToast;
window.showNotification = showNotification;
window.getCSRFToken = getCSRFToken;