/**
 * Simple Logger Utility
 * Controls console output based on debug mode and log levels
 */
class Logger {
    constructor() {
        // Check if debug mode is enabled
        this.debugMode = window.DEBUG_MODE || this.getUrlParam('debug') === 'true' || false;
        this.logLevels = {
            ERROR: 0,
            WARN: 1,
            INFO: 2,
            DEBUG: 3
        };
        this.currentLevel = this.debugMode ? this.logLevels.DEBUG : this.logLevels.INFO;
        
        // Initialize debug mode message (only once)
        if (this.debugMode) {
            console.log('🔧 Debug mode enabled - showing all log levels');
        }
    }
    
    getUrlParam(param) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(param);
    }
    
    setDebugMode(enabled) {
        this.debugMode = enabled;
        this.currentLevel = enabled ? this.logLevels.DEBUG : this.logLevels.INFO;
        window.DEBUG_MODE = enabled;
        
        if (enabled) {
            console.log('🔧 Debug mode enabled - showing all log levels');
        } else {
            console.log('🔇 Debug mode disabled - showing only INFO, WARN, ERROR');
        }
    }
    
    error(...args) {
        if (this.currentLevel >= this.logLevels.ERROR) {
            console.error('❌', ...args);
        }
    }
    
    warn(...args) {
        if (this.currentLevel >= this.logLevels.WARN) {
            console.warn('⚠️', ...args);
        }
    }
    
    info(...args) {
        if (this.currentLevel >= this.logLevels.INFO) {
            console.log('ℹ️', ...args);
        }
    }
    
    debug(...args) {
        if (this.currentLevel >= this.logLevels.DEBUG) {
            console.log('🔍', ...args);
        }
    }
    
    // Special methods for specific use cases
    success(...args) {
        if (this.currentLevel >= this.logLevels.INFO) {
            console.log('✅', ...args);
        }
    }
    
    connection(...args) {
        if (this.currentLevel >= this.logLevels.INFO) {
            console.log('🔌', ...args);
        }
    }
    
    price(...args) {
        if (this.currentLevel >= this.logLevels.DEBUG) {
            console.log('💰', ...args);
        }
    }
    
    subscription(...args) {
        if (this.currentLevel >= this.logLevels.DEBUG) {
            console.log('📡', ...args);
        }
    }
    
    // Group methods for cleaner output
    group(title, callback) {
        if (this.currentLevel >= this.logLevels.DEBUG) {
            console.group(title);
            callback();
            console.groupEnd();
        } else {
            // In non-debug mode, just execute without grouping
            callback();
        }
    }
}

// Global logger instance
const logger = new Logger();

// Make logger available globally
window.logger = logger;

// Utility functions for easy access
window.enableDebugMode = () => logger.setDebugMode(true);
window.disableDebugMode = () => logger.setDebugMode(false);
window.toggleDebugMode = () => logger.setDebugMode(!logger.debugMode);

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Logger;
} 