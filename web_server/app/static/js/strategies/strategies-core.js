// @FEAT:strategy-management @COMP:util @TYPE:core
// Core utilities for strategies page - Exchange helpers, CSRF token, constants
'use strict';

// Phase 4.3: Exchange type helper functions
// Sync with: web_server/app/constants.py:Exchange.DOMESTIC_EXCHANGES (Line 249)
function isExchangeDomestic(exchange) {
    const domesticExchanges = ['UPBIT', 'BITHUMB'];
    return domesticExchanges.includes(exchange?.toUpperCase());
}

function getCurrencySymbol(exchange) {
    return isExchangeDomestic(exchange) ? '₩' : '$';
}

// CSRF 토큰
function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

// @FEAT:strategy-rendering @COMP:util @TYPE:config
// 메트릭 아이콘 경로 정의
const METRIC_ICONS = {
    accounts: 'M4 4a2 2 0 00-2 2v4a2 2 0 002 2V6h10a2 2 0 00-2-2H4zm2 6a2 2 0 012-2h8a2 2 0 012 2v4a2 2 0 01-2 2H8a2 2 0 01-2-2v-4zm6 4a2 2 0 100-4 2 2 0 000 4z',
    positions: 'M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z'
};
