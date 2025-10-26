// @FEAT:strategy-management @COMP:ui @TYPE:core
// Depends on: strategies-core.js (getCurrencySymbol), strategies-rendering.js (renderStatusBadge, renderMarketTypeBadge, etc.)

/**
 * Tab 전환 및 데이터 로딩 관리
 * @param {string} tab - 전환할 탭 ('my', 'subscribed', 'discover')
 */
function switchTab(tab) {
    const sections = {
        my: document.getElementById('section-my'),
        subscribed: document.getElementById('section-subscribed'),
        discover: document.getElementById('section-discover')
    };
    Object.values(sections).forEach(s => s.classList.add('hidden'));
    sections[tab]?.classList.remove('hidden');

    // Load data when switching to subscribed or discover
    if (tab === 'subscribed') {
        loadSubscribedStrategies();
    } else if (tab === 'discover') {
        loadPublicStrategies();
    }
}

/**
 * 전략 카드 업데이트 (계좌 정보 및 요약 정보)
 * @param {Object} strategy - 업데이트할 전략 데이터
 */
function updateStrategyCard(strategy) {
    // 전략 카드의 계좌 정보 업데이트
    const accountsContainer = document.getElementById(`strategy-accounts-${strategy.id}`);

    if (accountsContainer) {
        if (strategy.connected_accounts && strategy.connected_accounts.length > 0) {
            let accountsHtml = '';
            strategy.connected_accounts.forEach(account => {
                const allocated = Number(account.allocated_capital ?? 0);
                accountsHtml += `
                    <div class="strategy-account-item">
                        <div class="strategy-account-info">
                            <p>${account.exchange.charAt(0).toUpperCase() + account.exchange.slice(1)} - ${account.name}</p>
                            <p>가중치: ${account.weight} | ${account.max_symbols ? `최대: ${account.max_symbols}개` : '최대: -'} | 레버리지: ${account.leverage}x</p>
                        </div>
                        <div class="strategy-account-amount">
                            <p class="amount tabular-nums">${getCurrencySymbol(account.exchange)}${allocated.toFixed(2)}</p>
                            <p class="currency">USDT${account.exchange === 'upbit' ? ' 환산' : ''}</p>
                        </div>
                    </div>
                `;
            });
            accountsContainer.innerHTML = accountsHtml;
        } else {
            accountsContainer.innerHTML = `
                <div class="text-center py-8 text-muted">
                    <p>연결된 계좌가 없습니다</p>
                </div>
            `;
        }
    }

    // 전략 요약 정보 업데이트
    const strategyCard = document.getElementById(`strategy-card-${strategy.id}`);
    if (strategyCard) {
        const summaryAmount = strategyCard.querySelector('.strategy-summary-card .amount');
        const accountCount = strategyCard.querySelector('.account-count .highlight');

        if (summaryAmount) {
            const totalAllocated = Number(strategy.total_allocated_capital ?? 0);
            const firstAccount = strategy.connected_accounts?.[0];
            const currencySymbol = getCurrencySymbol(firstAccount?.exchange || 'BINANCE');
            summaryAmount.textContent = `${currencySymbol}${totalAllocated.toFixed(2)}`;
        }
        if (accountCount) {
            accountCount.textContent = `${strategy.connected_accounts.length}개`;
        }
    }
}
