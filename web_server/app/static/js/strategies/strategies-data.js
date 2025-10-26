// @FEAT:strategy-data @COMP:service @TYPE:core
// Depends on: strategies-api.js (apiCall, renderState), strategies-rendering.js (renderStatusBadge, renderMarketTypeBadge, renderStrategyBadges, renderStrategyMetrics, renderAccountItem), strategies-core.js (getCurrencySymbol)

// WHY: 구독/공개 전략 데이터 로딩 및 렌더링 로직 분리

'use strict';

async function loadSubscribedStrategies() {
    const container = document.getElementById('subscribed-strategies');
    renderState(container, 'loading');

    try {
        const data = await apiCall('/api/strategies/accessibles');
        const items = (data.strategies || []).filter(s => s.ownership === 'subscriber');

        if (items.length === 0) {
            renderState(container, 'empty', {
                message: '구독 중인 전략이 없습니다.',
                emptyIcon: 'chart-line'
            });
            return;
        }

        container.innerHTML = items.map(renderSubscribedStrategy).join('');
    } catch (error) {
        renderState(container, 'error', {
            message: error.message,
            onRetry: loadSubscribedStrategies
        });
    }
}

function renderSubscribedStrategy(s) {
    const accounts = s.connected_accounts || [];
    const totalAllocated = accounts.reduce((sum, a) => sum + (a.allocated_capital || 0), 0);
    const firstAccount = accounts[0];
    const currencySymbol = getCurrencySymbol(firstAccount?.exchange || 'BINANCE');

    return `
    <div class="strategy-card-new" id="strategy-card-${s.id}">
      <div class="strategy-card-header">
        <div class="strategy-title-section">
          <div class="strategy-title-row">
            <h3>${s.name}</h3>
            ${renderStrategyBadges(s)}
          </div>
          <p>${s.description || ''}</p>
        </div>
        <div class="strategy-actions-section">
          <button onclick="openSubscribeModal(${s.id})" class="btn-action btn-action-secondary" title="구독 관리">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
          </button>
        </div>
      </div>

      <div class="strategy-grid-layout">
        <div class="strategy-summary-card">
          <div class="summary-header"><h4>전략 요약</h4></div>
          <div class="summary-main-metrics">
            <div class="main-metric">
              <p class="amount tabular-nums">${currencySymbol}${totalAllocated.toFixed(2)}</p>
              <p class="amount-label">총 할당 자본</p>
            </div>
            ${renderStrategyMetrics(s)}
          </div>
          <div class="summary-quick-actions">
            <a href="/strategies/${s.id}/positions" class="quick-action-btn quick-action-view" title="포지션 보기">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.022 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd" />
              </svg>
              포지션 보기
            </a>
            <button onclick="openSubscribeModal(${s.id})" class="quick-action-btn quick-action-add" title="계좌 연동">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
              계좌 연동
            </button>
          </div>
        </div>

        <div class="strategy-accounts-section">
          <h4>내 연결 계좌</h4>
          <div class="strategy-accounts-list" id="strategy-accounts-${s.id}">
            ${accounts.length ? accounts.map(a => renderAccountItem(a, {
              showActions: true,
              strategyId: s.id,
              showInactiveTag: true
            })).join('') : '<div class="text-center py-8 text-muted">연결된 계좌가 없습니다</div>'}
          </div>
        </div>
      </div>
    </div>`;
}

async function loadPublicStrategies() {
    const container = document.getElementById('public-strategies');
    renderState(container, 'loading');

    try {
        const data = await apiCall('/api/strategies/public');
        const items = data.strategies || [];

        if (items.length === 0) {
            renderState(container, 'empty', {
                message: '공개된 전략이 없습니다.',
                emptyIcon: 'globe'
            });
            return;
        }

        container.innerHTML = items.map(renderPublicStrategy).join('');
    } catch (error) {
        renderState(container, 'error', {
            message: error.message,
            onRetry: loadPublicStrategies
        });
    }
}

function renderPublicStrategy(s) {
    return `
    <div class="card-inner">
        <div class="flex items-center justify-between">
            <div>
                <div class="text-lg font-semibold text-primary">${s.name}</div>
                <div class="text-sm text-muted">${s.description || ''}</div>
            </div>
            <div class="flex items-center space-x-2">
                <button class="btn btn-secondary btn-sm" onclick="openPublicDetail(${s.id})">자세히</button>
                <button class="btn btn-primary btn-sm" onclick="openSubscribeModal(${s.id})">구독하기</button>
            </div>
        </div>
    </div>`;
}
