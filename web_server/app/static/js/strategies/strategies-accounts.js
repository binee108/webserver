// @FEAT:strategy-accounts @COMP:service @TYPE:core
// Depends on: strategies-api.js (apiCall, renderState, setButtonLoading, handleApiResponse, getPayload, getErrorMessage), strategies-modal.js (openModal, closeAccountModal), strategies-core.js (getCSRFToken), strategies-ui.js (updateStrategyCard)

// WHY: 전략 계좌 관리 로직 분리

'use strict';

// @FEAT:modal-management @COMP:route @TYPE:helper
function openAccountModal(strategyId, mode='view') {
    openModal('accountModal', {
        onOpen: () => loadStrategyAccountModal(strategyId, mode)
    });
}

async function loadStrategyAccountModal(strategyId, mode) {
    const modalContent = document.getElementById('accountModalContent');
    renderState(modalContent, 'loading');

    try {
        // 사용자의 모든 계좌와 전략의 연결된 계좌 정보 조회
        const [accountsResult, strategyAccountsResult] = await Promise.all([
            apiCall('/api/accounts', { autoErrorToast: false }),
            apiCall(`/api/strategies/${strategyId}/accounts`, { autoErrorToast: false })
        ]);

        const allAccounts = accountsResult.accounts || [];
        const linkedAccounts = strategyAccountsResult.accounts || [];
        renderAccountModal(strategyId, allAccounts, linkedAccounts);
    } catch (error) {
        renderState(modalContent, 'error', {
            message: error.message,
            onRetry: () => loadStrategyAccountModal(strategyId, mode)
        });
        showToast(error.message, 'error');
    }
}

function renderAccountModal(strategyId, allAccounts, connectedAccounts) {
    const modalContent = document.getElementById('accountModalContent');

    const connectedAccountIds = new Set(connectedAccounts.map(acc => acc.id));

    let html = `
        <div class="space-y-6">
            <div>
                <h4 class="text-lg font-medium text-primary mb-4">사용 가능한 계좌</h4>
                <div class="space-y-3">
    `;

    if (allAccounts.length === 0) {
        html += '<div class="text-center py-8 text-muted">등록된 계좌가 없습니다.</div>';
    } else {
        allAccounts.forEach(account => {
            const isConnected = connectedAccountIds.has(account.id);
            const connectedAccount = connectedAccounts.find(ca => ca.id === account.id);

            html += `
                <div class="account-item ${isConnected ? 'border-accent' : ''}">
                    <div class="flex items-center space-x-3 flex-1">
                        <div class="w-8 h-8 bg-accent bg-opacity-20 rounded-full flex items-center justify-center">
                            <span class="text-sm font-bold text-accent">${account.exchange.toUpperCase().charAt(0)}</span>
                        </div>
                        <div class="flex-1">
                            <div class="font-medium text-primary">${account.exchange.charAt(0).toUpperCase() + account.exchange.slice(1)} - ${account.name}</div>
                            <div class="text-sm text-muted">${account.is_active ? '활성' : '비활성'}</div>
                        </div>
                    </div>
                    <div class="flex items-center space-x-2">
                        ${isConnected ? `
                            <span class="badge badge-success">연결됨</span>
                            <button onclick="disconnectAccount(${strategyId}, ${account.id})" class="btn btn-error btn-sm">
                                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                                연결 해제
                            </button>
                            <button onclick="editConnection(${strategyId}, ${account.id})"
                                    data-weight="${connectedAccount ? connectedAccount.weight : 1.0}"
                                    data-leverage="${connectedAccount ? connectedAccount.leverage : 1.0}"
                                    data-max-symbols="${connectedAccount ? connectedAccount.max_symbols || '' : ''}"
                                    class="btn btn-secondary btn-sm">
                                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                </svg>
                                설정
                            </button>
                        ` : `
                            <button onclick="connectAccount(${strategyId}, ${account.id}, event)"
                                    data-exchange="${account.exchange}"
                                    class="btn btn-primary btn-sm">
                                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                                </svg>
                                연결
                            </button>
                        `}
                    </div>
                </div>
            `;
        });
    }

    html += `
                </div>
            </div>
        </div>
    `;

    modalContent.innerHTML = html;
}

// @FEAT:futures-validation @COMP:route @TYPE:validation
function connectAccount(strategyId, accountId, event) {
    // 메타데이터 로드 실패 시 백엔드 검증으로 fallback
    if (!window.EXCHANGE_METADATA) {
        console.warn('⚠️ Exchange metadata not loaded, validation skipped');
        showConnectionForm(strategyId, accountId, 'connect');
        return;
    }

    // 전략 정보 조회 (window.strategies 전역 변수 사용)
    const strategy = window.strategies?.find(s => s.id === parseInt(strategyId));
    if (!strategy) {
        showToast('전략 정보를 찾을 수 없습니다', 'error');
        return;
    }

    // 계좌 정보 조회 (allAccounts 전역 변수는 loadStrategyAccountModal에서 설정됨)
    // 하지만 여기서는 계좌가 이미 버튼 클릭 시점에 렌더링되어 있으므로,
    // data-exchange 속성을 사용하거나, renderAccountModal 내부에서 계좌 정보 전달
    // 현재 구현: 계좌 정보는 상단 modal의 data 속성에서 가져오기
    const accountButton = event?.target?.closest('button');
    const accountExchange = accountButton?.dataset?.exchange;

    if (!accountExchange) {
        console.error('❌ 계좌 거래소 정보를 찾을 수 없습니다');
        showConnectionForm(strategyId, accountId, 'connect');
        return;
    }

    // 선물 전략인 경우 거래소 선물 지원 여부 확인
    if (strategy.market_type === 'FUTURES') {
        const exchangeMeta = window.EXCHANGE_METADATA[accountExchange.toLowerCase()];

        if (exchangeMeta && !exchangeMeta.supports_futures && !exchangeMeta.supports_perpetual) {
            // 지원 거래소 목록 생성
            const supportedExchanges = Object.entries(window.EXCHANGE_METADATA)
                .filter(([_, meta]) => meta.supports_futures || meta.supports_perpetual)
                .map(([name, _]) => name.charAt(0).toUpperCase() + name.slice(1))
                .join(', ');

            showToast(
                `이 거래소(${accountExchange})는 선물 거래를 지원하지 않습니다. 지원 거래소: ${supportedExchanges}`,
                'error'
            );
            return;
        }
    }

    // 검증 통과 시 연결 폼 표시
    showConnectionForm(strategyId, accountId, 'connect');
}

function editConnection(strategyId, accountId) {
    // 기존 연결 설정 편집 폼 표시
    const button = event.target.closest('button');
    const existingData = {
        weight: parseFloat(button.dataset.weight),
        leverage: parseFloat(button.dataset.leverage),
        max_symbols: button.dataset.maxSymbols || null
    };
    showConnectionForm(strategyId, accountId, 'edit', existingData);
}

function showConnectionForm(strategyId, accountId, mode, existingData = null) {
    const modalContent = document.getElementById('accountModalContent');

    const weight = existingData?.weight || 1.0;
    const leverage = existingData?.leverage || 1.0;
    const maxSymbols = existingData?.max_symbols || '';

    modalContent.innerHTML = `
        <div class="space-y-6">
            <div class="flex items-center space-x-3">
                <button onclick="loadStrategyAccountModal(${strategyId})" class="btn btn-secondary btn-sm">
                    <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path>
                    </svg>
                    돌아가기
                </button>
                <h4 class="text-lg font-medium text-primary">${mode === 'edit' ? '연결 설정 수정' : '계좌 연결'}</h4>
            </div>

            <form id="connectionForm" onsubmit="submitConnection(event, ${strategyId}, ${accountId}, '${mode}')">
                <div class="space-y-4">
                    <div class="form-group">
                        <label class="form-label">가중치</label>
                        <input type="number" step="0.1" min="0.1" max="10" value="${weight}" name="weight" required class="form-input" placeholder="1.0">
                        <p class="text-sm text-muted mt-1">전체 자본 대비 이 계좌에 할당할 비율 (1.0 = 100%)</p>
                    </div>

                    <div class="form-group">
                        <label class="form-label">레버리지</label>
                        <input type="number" step="0.1" min="1" max="100" value="${leverage}" name="leverage" required class="form-input" placeholder="1.0">
                        <p class="text-sm text-muted mt-1">사용할 레버리지 배수</p>
                    </div>

                    <div class="form-group">
                        <label class="form-label">최대 보유 심볼 수 (선택사항)</label>
                        <input type="number" min="1" max="100" value="${maxSymbols}" name="max_symbols" class="form-input" placeholder="예: 10">
                        <p class="text-sm text-muted mt-1">이 계좌에서 동시에 보유할 수 있는 최대 심볼 수</p>
                    </div>
                </div>

                <div class="flex space-x-3 mt-6">
                    <button type="button" onclick="loadStrategyAccountModal(${strategyId})" class="btn btn-secondary flex-1">
                        취소
                    </button>
                    <button type="submit" class="btn btn-primary flex-1">
                        ${mode === 'edit' ? '수정' : '연결'}
                    </button>
                </div>
            </form>
        </div>
    `;
}

function submitConnection(event, strategyId, accountId, mode) {
    event.preventDefault();

    const form = document.getElementById('connectionForm');
    const formData = new FormData(form);

    const data = {
        account_id: accountId,
        weight: parseFloat(formData.get('weight')),
        leverage: parseFloat(formData.get('leverage'))
    };

    const maxSymbols = formData.get('max_symbols');
    if (maxSymbols && maxSymbols.trim() !== '') {
        data.max_symbols = parseInt(maxSymbols);
    }

    const url = mode === 'edit'
        ? `/api/strategies/${strategyId}/accounts/${accountId}`
        : `/api/strategies/${strategyId}/accounts`;
    const method = mode === 'edit' ? 'PUT' : 'POST';

    const submitButton = form.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = '<div class="loading-spinner"></div>처리 중...';

    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify(data)
    })
    .then(handleApiResponse)
    .then(data => {
        if (data.success) {
            showToast(mode === 'edit' ? '연결 설정이 성공적으로 수정되었습니다.' : '계좌가 성공적으로 연결되었습니다.', 'success');
            loadStrategyAccountModal(strategyId);

            // 전략 카드의 계좌 정보 업데이트
            const payload = getPayload(data);
            if (payload.updated_strategy) {
                updateStrategyCard(payload.updated_strategy);
            }
        } else {
            showToast('처리 실패: ' + getErrorMessage(data), 'error');
        }
    })
    .catch(error => {
        showToast('처리 중 오류가 발생했습니다: ' + error.message, 'error');
    })
    .finally(() => {
        submitButton.disabled = false;
        submitButton.innerHTML = originalText;
    });
}

function disconnectAccount(strategyId, accountId) {
    if (confirm('정말로 이 계좌와의 연결을 해제하시겠습니까?')) {
        fetch(`/api/strategies/${strategyId}/accounts/${accountId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(handleApiResponse)
        .then(data => {
            if (data.success) {
                showToast('계좌 연결이 성공적으로 해제되었습니다.', 'success');
                loadStrategyAccountModal(strategyId);

                // 전략 카드의 계좌 정보 업데이트
                const payload = getPayload(data);
                if (payload.updated_strategy) {
                    updateStrategyCard(payload.updated_strategy);
                }
            } else {
                showToast('연결 해제 실패: ' + getErrorMessage(data), 'error');
            }
        })
        .catch(error => {
            showToast('연결 해제 중 오류가 발생했습니다: ' + error.message, 'error');
        });
    }
}
