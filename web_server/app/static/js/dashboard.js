'use strict';

// eslint-disable-next-line no-unused-vars
(function (window, document) {
    // showToast는 toast.js에서 전역으로 제공됨

    const state = {
        dashboardData: null,
        currentStrategy: null,
        sparklineCharts: {},
        modalChart: null,
        refreshIntervalId: null,
        updateIntervalId: null,
        trades: {
            allTrades: [],
            displayedTrades: [],
            offset: 0,
            hasMore: true,
            isLoading: false,
            filters: {
                strategy: '',
                account: '',
                symbol: '',
                period: 'all',
            },
        },
    };

    function formatNumber(num, decimals = 2) {
        if (num === null || num === undefined) return '0';
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        }).format(num);
    }

    function formatCurrency(num) {
        if (num === null || num === undefined) return '$0.00';
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
        }).format(num);
    }

    function formatPercent(num) {
        if (num === null || num === undefined) return '0.00%';
        return `${num >= 0 ? '+' : ''}${formatNumber(num)}%`;
    }

    function formatMDD(num) {
        if (num === null || num === undefined) return '0.00%';
        return `${formatNumber(Math.abs(num))}%`;
    }

    function getCsrfToken() {
        return document.querySelector('meta[name=csrf-token]')?.getAttribute('content') || '';
    }

    async function toggleStrategyState(strategyId) {
        const response = await fetch(`/api/strategies/${strategyId}/toggle`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
        });

        let data;
        try {
            data = await response.json();
        } catch (error) {
            const parseError = new Error('전략 상태 변경 응답을 해석할 수 없습니다.');
            parseError.cause = error;
            parseError.httpStatus = response.status;
            throw parseError;
        }

        if (!response.ok || !data?.success) {
            const message = data?.error?.message || data?.message || `전략 상태 변경에 실패했습니다. (HTTP ${response.status})`;
            const apiError = new Error(message);
            apiError.payload = data;
            apiError.httpStatus = response.status;
            throw apiError;
        }

        return data;
    }

    async function toggleStrategyInput(strategyId, isChecked) {
        const toggleInput = document.querySelector(`input[data-strategy-id="${strategyId}"]`);
        const statusText = document.getElementById(`status-text-${strategyId}`);

        try {
            if (toggleInput) {
                toggleInput.disabled = true;
                toggleInput.style.opacity = '0.7';
            }

            const data = await toggleStrategyState(strategyId);
            const payload = data.data || {};
            const isActive = typeof payload.is_active === 'boolean' ? payload.is_active : isChecked;

            if (toggleInput) {
                toggleInput.checked = isActive;
            }

            if (statusText) {
                statusText.textContent = isActive ? '활성' : '비활성';
            }

            showToast(data.message || '전략 상태가 변경되었습니다.', 'success');
        } catch (error) {
            if (toggleInput) {
                toggleInput.checked = !isChecked;
            }
            showToast(error.message || '전략 상태 변경 중 오류가 발생했습니다.', 'error');
        } finally {
            if (toggleInput) {
                toggleInput.disabled = false;
                toggleInput.style.opacity = '1';
            }
        }
    }

    async function toggleStrategy(strategyId, currentStatus) {
        const strategyCard = document.querySelector(`[data-strategy-id="${strategyId}"]`);
        const toggleElement = strategyCard?.querySelector('.toggle-switch');
        const statusText = strategyCard?.querySelector('.text-xs.text-muted');

        try {
            if (toggleElement) {
                toggleElement.style.opacity = '0.7';
                toggleElement.style.pointerEvents = 'none';
            }

            const data = await toggleStrategyState(strategyId);
            const payload = data.data || {};
            const newStatus = typeof payload.is_active === 'boolean' ? payload.is_active : !currentStatus;

            if (toggleElement) {
                toggleElement.classList.toggle('active', newStatus);
                toggleElement.setAttribute('onclick', `toggleStrategy(${strategyId}, ${newStatus})`);
            }

            if (statusText) {
                statusText.textContent = newStatus ? '활성' : '비활성';
            }

            showToast(data.message || '전략 상태가 변경되었습니다.', 'success');
        } catch (error) {
            if (toggleElement) {
                toggleElement.classList.toggle('active', currentStatus);
                toggleElement.setAttribute('onclick', `toggleStrategy(${strategyId}, ${currentStatus})`);
            }
            showToast(error.message || '전략 상태 변경 중 오류가 발생했습니다.', 'error');
        } finally {
            if (toggleElement) {
                toggleElement.style.opacity = '1';
                toggleElement.style.pointerEvents = 'auto';
            }
        }
    }

    function createStrategyCard(strategy) {
        const isActive = strategy.is_active;
        const pnlColor = strategy.pnl_30d >= 0 ? 'text-success' : 'text-error';
        const roiColor = strategy.roi_30d >= 0 ? 'text-success' : 'text-error';

        return `
            <div class="card rounded-xl p-6 fade-in strategy-card" data-strategy-id="${strategy.id}">
                <div class="flex justify-between items-center mb-6">
                    <div class="flex items-center space-x-3">
                        <div class="w-10 h-10 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
                            <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                        </div>
                        <div>
                            <h3 class="text-lg font-semibold text-primary">${strategy.name}</h3>
                            <p class="text-xs text-muted">${strategy.group_name}</p>
                        </div>
                    </div>
                    <div class="flex items-center space-x-2">
                        <span class="text-xs text-muted" id="status-text-${strategy.id}">${isActive ? '활성' : '비활성'}</span>
                        <label class="toggle-switch-container" title="전략 활성화/비활성화">
                            <input type="checkbox" class="strategy-toggle sr-only"
                                   data-strategy-id="${strategy.id}"
                                   ${isActive ? 'checked' : ''}
                                   onchange="toggleStrategyInput(${strategy.id}, this.checked)">
                            <div class="toggle-switch"></div>
                        </label>
                    </div>
                </div>

                <div class="mb-6 text-center">
                    <p class="text-sm text-muted mb-1">30일 손익 (30D PnL)</p>
                    <p class="text-4xl font-bold ${pnlColor} tabular-nums">${formatCurrency(strategy.pnl_30d)}</p>
                    <div class="mt-3 sparkline-container" id="sparkline-${strategy.id}">
                        <canvas width="200" height="40"></canvas>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-4 mb-6">
                    <div class="card p-4 rounded-lg text-center bg-secondary">
                        <p class="text-xs text-muted mb-1 flex items-center justify-center">
                            30D ROI
                            <svg class="w-4 h-4 ml-1 ${roiColor}" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="${strategy.roi_30d >= 0 ? 'M3.293 9.707a1 1 0 010-1.414l6-6a1 1 0 011.414 0l6 6a1 1 0 01-1.414 1.414L11 5.414V17a1 1 0 11-2 0V5.414L4.707 9.707a1 1 0 01-1.414 0z' : 'M14.707 12.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 14.586V3a1 1 0 012 0v11.586l2.293-2.293a1 1 0 011.414 0z'}" clip-rule="evenodd"></path>
                            </svg>
                        </p>
                        <p class="text-xl font-semibold ${roiColor} tabular-nums">${formatPercent(strategy.roi_30d)}</p>
                    </div>
                    <div class="card p-4 rounded-lg text-center bg-secondary">
                        <p class="text-xs text-muted mb-1 flex items-center justify-center">
                            30D MDD
                            <svg class="w-4 h-4 ml-1 text-error" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                            </svg>
                        </p>
                        <p class="text-xl font-semibold text-error tabular-nums">${formatMDD(strategy.mdd_30d)}</p>
                    </div>
                </div>

                <div class="space-y-3">
                    <div class="flex justify-between items-center text-sm">
                        <div class="flex items-center text-muted">
                            <svg class="w-5 h-5 mr-2 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                            <span>할당 자본</span>
                        </div>
                        <span class="font-medium text-primary tabular-nums">${formatCurrency(strategy.allocated_capital)}</span>
                    </div>
                    <div class="flex justify-between items-center text-sm">
                        <div class="flex items-center text-muted">
                            <svg class="w-5 h-5 mr-2 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                            </svg>
                            <span>활성 포지션</span>
                        </div>
                        <span class="font-medium text-primary tabular-nums">${strategy.position_count}</span>
                    </div>
                    <div class="flex justify-between items-center text-sm">
                        <div class="flex items-center text-muted">
                            <svg class="w-5 h-5 mr-2 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z"></path>
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z"></path>
                            </svg>
                            <span>30D Sharpe</span>
                        </div>
                        <span class="font-medium text-primary tabular-nums">${formatNumber(strategy.sharpe_ratio_30d, 2)}</span>
                    </div>
                </div>

                <div class="mt-8 pt-4 border-t border-color text-right">
                    <button type="button" onclick="openStrategyModal(${strategy.id})" class="text-sm text-accent hover:text-accent font-medium transition-colors">
                        전략 상세 보기 &rarr;
                    </button>
                </div>
            </div>
        `;
    }

    function createSparklineChart(containerId, data) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const canvas = container.querySelector('canvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const chart = new window.Chart(ctx, {
            type: 'line',
            data: {
                labels: data.map((_, i) => i),
                datasets: [{
                    data,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: false },
                    y: { display: false },
                },
                elements: { point: { radius: 0 } },
                interaction: { intersect: false },
            },
        });

        state.sparklineCharts[containerId] = chart;
    }

    function createAccountCard(account) {
        return `
            <div class="card p-5 rounded-lg">
                <div class="flex justify-between items-center mb-4">
                    <div>
                        <h4 class="text-lg font-semibold text-accent">${account.name} (${account.exchange.toUpperCase()})</h4>
                        <span class="text-xs ${account.is_active ? 'text-success bg-green-900/20' : 'text-muted bg-secondary'} px-2 py-0.5 rounded-full">
                            ${account.is_active ? '● 활성' : '○ 비활성'}
                        </span>
                    </div>
                </div>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                        <p class="text-xs text-muted">할당 자본</p>
                        <p class="text-lg font-medium text-primary">${formatCurrency(account.allocated_capital)}</p>
                    </div>
                    <div>
                        <p class="text-xs text-muted">총 손익 (PnL)</p>
                        <p class="text-lg font-medium ${account.current_pnl >= 0 ? 'text-success' : 'text-error'}">${formatCurrency(account.current_pnl)}</p>
                    </div>
                    <div>
                        <p class="text-xs text-muted">수익률 (ROI)</p>
                        <p class="text-lg font-medium ${account.cumulative_return >= 0 ? 'text-success' : 'text-error'}">${formatPercent(account.cumulative_return)}</p>
                    </div>
                    <div>
                        <p class="text-xs text-muted">최대 낙폭 (MDD)</p>
                        <p class="text-lg font-medium text-error">${formatMDD(account.mdd_30d)}</p>
                    </div>
                </div>
            </div>
        `;
    }

    function createModalChart(strategy) {
        if (state.modalChart) {
            state.modalChart.destroy();
            state.modalChart = null;
        }

        const ctx = document.getElementById('modal-equity-curve-chart');
        if (!ctx || !strategy.chart_data) return;

        state.modalChart = new window.Chart(ctx, {
            type: 'line',
            data: {
                labels: strategy.chart_data.dates,
                datasets: [{
                    label: '누적 수익 ($)',
                    data: strategy.chart_data.pnl_values,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    tension: 0.1,
                    fill: true,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: false,
                        ticks: {
                            color: getComputedStyle(document.documentElement).getPropertyValue('--text-muted'),
                            callback: value => formatCurrency(value),
                        },
                        grid: { color: getComputedStyle(document.documentElement).getPropertyValue('--border-color') },
                    },
                    x: {
                        ticks: { color: getComputedStyle(document.documentElement).getPropertyValue('--text-muted') },
                        grid: { color: getComputedStyle(document.documentElement).getPropertyValue('--border-color') },
                    },
                },
                plugins: {
                    legend: {
                        labels: { color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary') },
                    },
                },
            },
        });
    }

    function createTradeRow(trade) {
        const isEntry = trade.is_entry === true;
        const pnlColor = isEntry
            ? 'text-muted'
            : trade.pnl > 0
                ? 'text-success'
                : trade.pnl < 0
                    ? 'text-error'
                    : 'text-muted';
        const exchangeBadge = trade.exchange ? trade.exchange.toUpperCase() : '';
        const pnlDisplay = isEntry ? '-' : trade.pnl !== null ? formatCurrency(trade.pnl) : '-';

        return `
            <tr class="hover:bg-card-hover transition-colors">
                <td class="px-4 py-3 text-sm text-primary">
                    ${new Date(trade.timestamp).toLocaleString('ko-KR', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                    })}
                </td>
                <td class="px-4 py-3 text-sm">
                    <div class="text-primary font-medium">${trade.strategy_name}</div>
                </td>
                <td class="px-4 py-3 text-sm">
                    <div class="text-primary">${trade.name}</div>
                    <div class="text-xs text-muted">${exchangeBadge}</div>
                </td>
                <td class="px-4 py-3 text-sm">
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary text-primary">
                        ${trade.symbol}
                    </span>
                </td>
                <td class="px-4 py-3 text-sm">
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${trade.side === 'buy' ? 'bg-green-900/20 text-success' : 'bg-red-900/20 text-error'}">
                        ${trade.side.toUpperCase()}
                    </span>
                </td>
                <td class="px-4 py-3 text-sm text-right text-primary font-mono">
                    ${formatCurrency(trade.price)}
                </td>
                <td class="px-4 py-3 text-sm text-right text-primary font-mono">
                    ${formatNumber(trade.quantity, 4)}
                </td>
                <td class="px-4 py-3 text-sm text-right font-mono">
                    <span class="${pnlColor} font-medium">
                        ${pnlDisplay}
                    </span>
                </td>
            </tr>
        `;
    }

    function updateDashboardStats(stats) {
        document.getElementById('total-capital').textContent = formatCurrency(stats.total_capital);

        const totalPnlElement = document.getElementById('total-pnl');
        totalPnlElement.textContent = formatCurrency(stats.total_pnl);
        totalPnlElement.className = `text-3xl font-bold ${stats.total_pnl >= 0 ? 'text-success' : 'text-error'}`;

        const cumulativeReturnElement = document.getElementById('cumulative-return');
        cumulativeReturnElement.textContent = formatPercent(stats.cumulative_return);
        cumulativeReturnElement.className = `text-3xl font-bold ${stats.cumulative_return >= 0 ? 'text-success' : 'text-error'}`;

        const overallWinRateElement = document.getElementById('overall-win-rate');
        overallWinRateElement.textContent = formatPercent(stats.overall_win_rate);
    }

    function updateStrategiesDisplay(strategies) {
        const container = document.getElementById('strategies-container');
        if (!container) return;

        if (!strategies.length) {
            container.innerHTML = `
                <div class="text-center py-12 col-span-full">
                    <div class="mx-auto w-16 h-16 bg-secondary rounded-full flex items-center justify-center mb-4">
                        <svg class="w-8 h-8 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2H9zm2 12h6m-6 0h6"></path>
                        </svg>
                    </div>
                    <h3 class="text-lg font-medium text-primary mb-2">등록된 전략이 없습니다</h3>
                    <p class="text-sm text-muted">새로운 트레이딩 전략을 추가해보세요.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = strategies.map(createStrategyCard).join('');

        strategies.forEach((strategy) => {
            if (strategy.sparkline_data && strategy.sparkline_data.length > 0) {
                window.setTimeout(() => {
                    createSparklineChart(`sparkline-${strategy.id}`, strategy.sparkline_data);
                }, 100);
            }
        });
    }

    function setupInfiniteScroll() {
        const container = document.getElementById('recent-trades-container');
        if (!container) return;

        container.addEventListener('scroll', () => {
            const scrollTop = container.scrollTop;
            const scrollHeight = container.scrollHeight;
            const clientHeight = container.clientHeight;

            const threshold = 250;
            const isNearBottom = scrollTop + clientHeight >= scrollHeight - threshold;

            if (isNearBottom && !state.trades.isLoading && state.trades.hasMore) {
                loadMoreTrades();
            }
        });
    }

    async function loadInitialTrades() {
        try {
            state.trades.offset = 0;
            state.trades.allTrades = [];
            state.trades.hasMore = true;

            const response = await fetch('/api/dashboard/recent-trades?limit=20&offset=0');
            const data = await response.json();

            if (data.success) {
                state.trades.allTrades = data.trades || [];
                state.trades.hasMore = data.has_more !== false;
                state.trades.offset = 20;

                populateFilterOptions(state.trades.allTrades);
                applyTradeFilters();
            }
        } catch (error) {
            console.error('거래 내역 로드 오류:', error);
            showToast('거래 내역을 불러오는 중 오류가 발생했습니다.', 'error');
        }
    }

    async function loadMoreTrades() {
        if (state.trades.isLoading || !state.trades.hasMore) return;

        state.trades.isLoading = true;
        showLoadingIndicator(true);

        try {
            const response = await fetch(`/api/dashboard/recent-trades?limit=10&offset=${state.trades.offset}`);
            const data = await response.json();

            if (data.success) {
                const newTrades = data.trades || [];
                state.trades.allTrades = [...state.trades.allTrades, ...newTrades];
                state.trades.hasMore = data.has_more !== false;
                state.trades.offset += newTrades.length;

                applyTradeFilters();
            }
        } catch (error) {
            console.error('추가 거래 로드 오류:', error);
        } finally {
            state.trades.isLoading = false;
            showLoadingIndicator(false);
        }
    }

    function showLoadingIndicator(show) {
        const indicator = document.getElementById('trades-loading');
        if (indicator) {
            indicator.classList.toggle('hidden', !show);
        }
    }

    function renderTrades(trades) {
        const container = document.getElementById('recent-trades-container');
        if (!container) return;

        if (!trades.length) {
            container.innerHTML = `
                <div class="text-center py-12">
                    <div class="mx-auto w-16 h-16 bg-secondary rounded-xl flex items-center justify-center mb-4">
                        <svg class="w-8 h-8 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                        </svg>
                    </div>
                    <h3 class="text-lg font-medium text-primary mb-2">필터 조건에 맞는 거래가 없습니다</h3>
                    <p class="text-sm text-muted">다른 조건으로 검색해보세요.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-color">
                    <thead class="bg-secondary sticky top-0 z-10">
                        <tr>
                            <th class="px-4 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">시간</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">전략</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">계좌</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">심볼</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">사이드</th>
                            <th class="px-4 py-3 text-right text-xs font-medium text-muted uppercase tracking-wider">가격</th>
                            <th class="px-4 py-3 text-right text-xs font-medium text-muted uppercase tracking-wider">수량</th>
                            <th class="px-4 py-3 text-right text-xs font-medium text-muted uppercase tracking-wider">손익</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-color">
                        ${trades.map(createTradeRow).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    function updateModalOverviewTab(strategy) {
        document.getElementById('modal-total-pnl').textContent = formatCurrency(strategy.current_pnl);
        document.getElementById('modal-total-pnl').className = `mt-1 text-3xl font-semibold ${strategy.current_pnl >= 0 ? 'text-success' : 'text-error'}`;

        document.getElementById('modal-total-roi').textContent = formatPercent(strategy.cumulative_return);
        document.getElementById('modal-total-roi').className = `mt-1 text-3xl font-semibold ${strategy.cumulative_return >= 0 ? 'text-success' : 'text-error'}`;

        document.getElementById('modal-mdd').textContent = formatMDD(strategy.mdd);
        document.getElementById('modal-profit-factor').textContent = formatNumber(strategy.profit_factor, 2);

        const metricsTable = document.getElementById('modal-metrics-table');
        const metrics = [
            ['승률 (Win Rate)', formatPercent(strategy.win_rate), 'text-success'],
            ['총 거래 횟수 (청산 기준)', strategy.total_trades, 'text-primary'],
            ['승리 거래 수 (청산 기준)', `${strategy.total_winning_trades} 회`, 'text-success'],
            ['패배 거래 수 (청산 기준)', `${strategy.total_losing_trades} 회`, 'text-error'],
            ['실현 손익 (Realized PnL)', formatCurrency(strategy.realized_pnl), strategy.realized_pnl >= 0 ? 'text-success' : 'text-error'],
            ['미실현 손익 (Unrealized PnL)', formatCurrency(strategy.unrealized_pnl), strategy.unrealized_pnl >= 0 ? 'text-success' : 'text-error'],
            ['30D Sharpe Ratio', formatNumber(strategy.sharpe_ratio_30d, 2), 'text-primary'],
            ['Sortino Ratio', formatNumber(strategy.sortino_ratio, 2), 'text-primary'],
            ['평균 수익 거래', formatCurrency(strategy.avg_win_trade), 'text-success'],
            ['평균 손실 거래', formatCurrency(strategy.avg_loss_trade), 'text-error'],
            ['최대 연속 수익', `${strategy.max_consecutive_wins}회`, 'text-primary'],
            ['최대 연속 손실', `${strategy.max_consecutive_losses}회`, 'text-primary'],
        ];

        metricsTable.innerHTML = metrics.map(([label, value, colorClass]) => `
            <tr class="hover:bg-card-hover">
                <td class="px-4 py-3 text-sm text-muted">${label}</td>
                <td class="px-4 py-3 text-sm ${colorClass} text-right font-medium">${value}</td>
            </tr>
        `).join('');
    }

    function updateModalAccountsTab(strategy) {
        const container = document.getElementById('modal-accounts-container');
        if (!container) return;

        if (!strategy.accounts_detail || !strategy.accounts_detail.length) {
            container.innerHTML = `
                <div class="text-center py-12">
                    <div class="mx-auto w-12 h-12 bg-secondary rounded-xl flex items-center justify-center mb-4">
                        <svg class="w-6 h-6 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                        </svg>
                    </div>
                    <h3 class="text-lg font-medium text-primary mb-2">거래 내역이 없습니다</h3>
                    <p class="text-sm text-muted">트레이딩 전략이 실행되면 거래 내역이 표시됩니다.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = strategy.accounts_detail.map(createAccountCard).join('');
    }

    function openStrategyModal(strategyId) {
        const strategy = state.dashboardData?.strategies_detail?.find((item) => item.id === strategyId);
        if (!strategy) return;

        state.currentStrategy = strategy;
        document.getElementById('modal-strategy-name').textContent = `${strategy.name} 상세 정보`;
        updateModalOverviewTab(strategy);
        updateModalAccountsTab(strategy);

        document.getElementById('strategy-detail-modal').classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        showModalTab('overview');
    }

    function closeStrategyModal() {
        document.getElementById('strategy-detail-modal').classList.add('hidden');
        document.body.style.overflow = 'auto';

        if (state.modalChart) {
            state.modalChart.destroy();
            state.modalChart = null;
        }
    }

    function showModalTab(tabName) {
        document.querySelectorAll('.tab-button').forEach((btn) => {
            btn.classList.remove('active');
            btn.classList.add('text-secondary');
        });

        const activeButton = document.querySelector(`.${tabName}-tab`);
        if (activeButton) {
            activeButton.classList.add('active');
            activeButton.classList.remove('text-secondary');
        }

        document.querySelectorAll('.modal-tab-content').forEach((content) => {
            content.classList.add('hidden');
        });

        const target = document.getElementById(`modal-${tabName}-tab`);
        if (target) {
            target.classList.remove('hidden');
        }

        if (tabName === 'overview' && state.currentStrategy) {
            window.setTimeout(() => createModalChart(state.currentStrategy), 100);
        }
    }

    function populateFilterOptions(trades) {
        const strategies = [...new Set(trades.map((t) => t.strategy_name))].sort();
        const strategySelect = document.getElementById('filter-strategy');
        if (strategySelect) {
            strategySelect.innerHTML =
                '<option value="">전체</option>' + strategies.map((s) => `<option value="${s}">${s}</option>`).join('');
        }

        const accounts = [...new Set(trades.map((t) => t.name))].sort();
        const accountSelect = document.getElementById('filter-account');
        if (accountSelect) {
            accountSelect.innerHTML =
                '<option value="">전체</option>' + accounts.map((a) => `<option value="${a}">${a}</option>`).join('');
        }
    }

    function toggleTradeFilters() {
        const panel = document.getElementById('trade-filters-panel');
        if (panel) {
            panel.classList.toggle('hidden');
        }
    }

    function applyTradeFilters() {
        state.trades.filters = {
            strategy: document.getElementById('filter-strategy')?.value || '',
            account: document.getElementById('filter-account')?.value || '',
            symbol: document.getElementById('filter-symbol')?.value.toUpperCase() || '',
            period: document.getElementById('filter-period')?.value || 'all',
        };

        let filtered = [...state.trades.allTrades];

        if (state.trades.filters.strategy) {
            filtered = filtered.filter((t) => t.strategy_name === state.trades.filters.strategy);
        }

        if (state.trades.filters.account) {
            filtered = filtered.filter((t) => t.name === state.trades.filters.account);
        }

        if (state.trades.filters.symbol) {
            filtered = filtered.filter((t) => t.symbol.includes(state.trades.filters.symbol));
        }

        if (state.trades.filters.period !== 'all') {
            const now = new Date();
            const cutoff = new Date();

            switch (state.trades.filters.period) {
                case 'today':
                    cutoff.setHours(0, 0, 0, 0);
                    break;
                case 'week':
                    cutoff.setDate(now.getDate() - 7);
                    break;
                case 'month':
                    cutoff.setDate(now.getDate() - 30);
                    break;
            }

            filtered = filtered.filter((t) => new Date(t.timestamp) >= cutoff);
        }

        state.trades.displayedTrades = filtered;
        renderTrades(filtered);
    }

    function resetTradeFilters() {
        document.getElementById('filter-strategy').value = '';
        document.getElementById('filter-account').value = '';
        document.getElementById('filter-symbol').value = '';
        document.getElementById('filter-period').value = 'all';
        applyTradeFilters();
    }

    async function loadDashboardData() {
        try {
            const statsResponse = await fetch('/api/dashboard/stats');
            const statsData = await statsResponse.json();

            if (statsData.success) {
                state.dashboardData = statsData.stats;
                updateDashboardStats(state.dashboardData);
                updateStrategiesDisplay(state.dashboardData.strategies_detail || []);
            } else {
                console.error('❌ API 응답 실패:', statsData.error);
            }
        } catch (error) {
            console.error('대시보드 데이터 로드 오류:', error);
            showToast('데이터를 불러오는 중 오류가 발생했습니다.', 'error');
        }
    }

    async function refreshDashboard() {
        showToast('대시보드를 새로고침하는 중...', 'info');
        await loadDashboardData();
        updateLastUpdate();
        showToast('대시보드가 업데이트되었습니다.', 'success');
    }

    function updateLastUpdate() {
        const now = new Date();
        const timeString = now.toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
        const label = document.getElementById('last-update');
        if (label) {
            label.textContent = `마지막 업데이트: ${timeString}`;
        }
    }

    function handleKeydown(event) {
        if (event.key === 'Escape') {
            closeStrategyModal();
        }
    }

    function handleModalOverlayClick(event) {
        if (event.target === event.currentTarget) {
            closeStrategyModal();
        }
    }

    function initialize() {
        updateLastUpdate();
        loadDashboardData();
        loadInitialTrades();

        document.addEventListener('keydown', handleKeydown);

        const modalOverlay = document.getElementById('strategy-detail-modal');
        if (modalOverlay) {
            modalOverlay.addEventListener('click', handleModalOverlayClick);
        }

        setupInfiniteScroll();

        state.refreshIntervalId = window.setInterval(updateLastUpdate, 30000);
        state.updateIntervalId = window.setInterval(loadDashboardData, 300000);
    }

    document.addEventListener('DOMContentLoaded', initialize);

    window.toggleStrategyInput = toggleStrategyInput;
    window.toggleStrategy = toggleStrategy;
    window.openStrategyModal = openStrategyModal;
    window.closeStrategyModal = closeStrategyModal;
    window.showModalTab = showModalTab;
    window.refreshDashboard = refreshDashboard;
    window.toggleTradeFilters = toggleTradeFilters;
    window.applyTradeFilters = applyTradeFilters;
    window.resetTradeFilters = resetTradeFilters;
})(window, document);
