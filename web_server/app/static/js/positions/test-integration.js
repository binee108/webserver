/**
 * Test script to verify the consolidated position management system
 * Run this in the browser console on the positions page
 */

function testPositionIntegration() {
    const results = {
        timestamp: new Date().toISOString(),
        tests: [],
        passed: 0,
        failed: 0
    };
    
    function test(name, testFn) {
        try {
            const result = testFn();
            if (result) {
                results.tests.push({ name, status: 'PASS', details: result });
                results.passed++;
                console.log(`✅ ${name}: PASS`);
            } else {
                results.tests.push({ name, status: 'FAIL', details: 'Test returned false' });
                results.failed++;
                console.error(`❌ ${name}: FAIL`);
            }
        } catch (error) {
            results.tests.push({ name, status: 'ERROR', error: error.message });
            results.failed++;
            console.error(`❌ ${name}: ERROR - ${error.message}`);
        }
    }
    
    // Test 1: Core utilities loaded
    test('RealtimeCore loaded', () => {
        return window.RealtimeCore !== undefined;
    });
    
    // Test 2: SSE Manager loaded
    test('SSE Manager available', () => {
        return typeof window.getSSEManager === 'function';
    });
    
    // Test 3: Position Price Manager loaded
    test('Position Price Manager available', () => {
        return typeof window.getPositionPriceManager === 'function';
    });
    
    // Test 4: Realtime Positions Manager loaded
    test('Realtime Positions Manager available', () => {
        return typeof window.getRealtimePositionsManager === 'function';
    });
    
    // Test 5: Realtime Open Orders Manager loaded
    test('Realtime Open Orders Manager available', () => {
        return typeof window.getRealtimeOpenOrdersManager === 'function';
    });
    
    // Test 6: Legacy functions redirected
    test('Legacy getPositionManager redirected', () => {
        return typeof window.getPositionManager === 'function';
    });
    
    // Test 7: Legacy initializePositionRealtime redirected
    test('Legacy initializePositionRealtime redirected', () => {
        return typeof window.initializePositionRealtime === 'function';
    });
    
    // Test 8: SSE Manager initialized
    test('SSE Manager initialized', () => {
        const manager = window.getSSEManager();
        return manager && manager.isInitialized;
    });
    
    // Test 9: Position Price Manager initialized
    test('Position Price Manager initialized', () => {
        const manager = window.getPositionPriceManager();
        return manager && manager.isInitialized;
    });
    
    // Test 10: Realtime Positions Manager initialized
    test('Realtime Positions Manager initialized', () => {
        const manager = window.getRealtimePositionsManager();
        return manager && manager.isInitialized;
    });
    
    // Test 11: Check for duplicate position-realtime-manager.js
    test('No duplicate position-realtime-manager.js loaded', () => {
        const scripts = Array.from(document.querySelectorAll('script[src*="position-realtime-manager.js"]'));
        return scripts.length === 0;
    });
    
    // Test 12: Check WebSocket connections
    test('WebSocket connections status', () => {
        const manager = window.getPositionPriceManager();
        if (manager) {
            const status = manager.getConnectionStatus();
            console.log('WebSocket status:', status);
            return true;
        }
        return false;
    });
    
    // Test 13: Check SSE connection
    test('SSE connection status', () => {
        const manager = window.getSSEManager();
        if (manager) {
            const status = manager.getStatus();
            console.log('SSE status:', status);
            return status.initialized;
        }
        return false;
    });
    
    // Test 14: Legacy function warnings
    test('Legacy function warnings working', () => {
        // Capture console.warn
        const originalWarn = console.warn;
        let warnings = [];
        console.warn = (msg) => warnings.push(msg);
        
        // Call legacy functions
        window.getPositionManager();
        window.initializePositionRealtime([]);
        
        // Restore console.warn
        console.warn = originalWarn;
        
        // Check if warnings were issued
        const hasWarnings = warnings.some(w => w.includes('deprecated'));
        if (hasWarnings) {
            console.log('Legacy warnings detected:', warnings);
        }
        return hasWarnings;
    });
    
    // Test 15: Position table exists
    test('Position table exists', () => {
        const table = document.querySelector('#positionsTable');
        return table !== null;
    });
    
    // Test 16: Open orders container exists
    test('Open orders container exists', () => {
        const container = document.querySelector('#open-orders-content');
        return container !== null;
    });
    
    // Summary
    console.log('\n========================================');
    console.log('Test Results Summary:');
    console.log(`Total Tests: ${results.tests.length}`);
    console.log(`Passed: ${results.passed} ✅`);
    console.log(`Failed: ${results.failed} ❌`);
    console.log('========================================\n');
    
    return results;
}

// Run the test
console.log('Running Position Integration Tests...\n');
const testResults = testPositionIntegration();

// Export for debugging
window.positionIntegrationTestResults = testResults;

console.log('\nTest results saved to: window.positionIntegrationTestResults');
console.log('To see detailed results: console.table(window.positionIntegrationTestResults.tests)');