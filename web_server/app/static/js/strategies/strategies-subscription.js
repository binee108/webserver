// @FEAT:strategy-subscription @COMP:service @TYPE:core
// Depends on: strategies-api.js (apiCall, renderState, handleApiResponse, getPayload, getErrorMessage), strategies-modal.js (openModal, closeAccountModal), strategies-core.js (getCSRFToken)

// WHY: 전략 구독/구독해제 로직 분리

'use strict';

// @FEAT:modal-management @COMP:route @TYPE:helper
function openSubscribeModal(strategyId) {
    openModal('accountModal', {
        onOpen: () => renderSubscribeAccountPicker(strategyId)
    });
}

async function renderSubscribeAccountPicker(strategyId) {
    const modalContent = document.getElementById('accountModalContent');
    renderState(modalContent, 'loading');

    try {
        const accounts = await apiCall('/api/accounts', { autoErrorToast: false });

        let html = `
        <div class="space-y-6">
          <div class="bg-info bg-opacity-10 border border-info rounded-lg p-4">
            <div class="flex items-start">
                <svg class="h-5 w-5 text-info mt-0.5 mr-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 100-16 8 8 0 000 16zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>
                <div>
                    <h4 class="text-sm font-medium text-info">구독 설정 안내</h4>
                    <p class="text-sm text-info mt-1">각 계좌마다 가중치/레버리지/최대 보유 심볼 수를 개별 설정할 수 있습니다.</p>
                </div>
            </div>
          </div>`;

        const accountList = accounts.accounts || [];
        if (accountList.length === 0) {
            html += '<div class="text-center py-8 text-muted">등록된 계좌가 없습니다.</div>';
        } else {
            accountList.forEach(acc => {
                html += `
                <div class="card-inner">
                  <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-3">
                        <div class="w-8 h-8 bg-accent bg-opacity-20 rounded-full flex items-center justify-center">
                            <span class="text-sm font-bold text-accent">${acc.exchange.toUpperCase().charAt(0)}</span>
                        </div>
                        <div>
                            <div class="font-medium text-primary">${acc.exchange.toUpperCase()} - ${acc.name}</div>
                            <div class="text-xs text-muted">내 계좌</div>
                        </div>
                    </div>
                    <button class="btn btn-primary btn-sm" onclick="openSubscribeSettings(${strategyId}, ${acc.id}, '${acc.exchange.toUpperCase()} - ${acc.name}')">구독 설정</button>
                  </div>
                </div>`;
            });
        }
        html += '</div>';
        modalContent.innerHTML = html;
    } catch (error) {
        renderState(modalContent, 'error', {
            message: error.message,
            onRetry: () => renderSubscribeAccountPicker(strategyId)
        });
        showToast(error.message, 'error');
    }
}

function openSubscribeSettings(strategyId, accountId, accountLabel) {
    const modalContent = document.getElementById('accountModalContent');
    modalContent.innerHTML = `
        <div class="space-y-6">
            <div class="flex items-center justify-between">
                <h4 class="text-lg font-medium text-primary">구독 설정</h4>
                <button onclick="renderSubscribeAccountPicker(${strategyId})" class="btn btn-secondary btn-sm">
                    돌아가기
                </button>
            </div>
            <div class="text-sm text-muted">대상 계좌: ${accountLabel}</div>
            <form id="subscribeSettingsForm" onsubmit="submitSubscribeSettings(event, ${strategyId}, ${accountId})">
                <div class="space-y-4">
                    <div class="form-group">
                        <label class="form-label">가중치</label>
                        <input type="number" step="0.1" min="0.1" max="10" value="1.0" name="weight" required class="form-input" placeholder="1.0">
                        <p class="text-sm text-muted mt-1">전체 자본 대비 이 계좌에 할당할 비율 (1.0 = 100%)</p>
                    </div>
                    <div class="form-group">
                        <label class="form-label">레버리지</label>
                        <input type="number" step="0.1" min="1" max="100" value="1.0" name="leverage" required class="form-input" placeholder="1.0">
                        <p class="text-sm text-muted mt-1">사용할 레버리지 배수</p>
                    </div>
                    <div class="form-group">
                        <label class="form-label">최대 보유 심볼 수 (선택사항)</label>
                        <input type="number" min="1" max="100" name="max_symbols" class="form-input" placeholder="예: 10">
                        <p class="text-sm text-muted mt-1">이 계좌에서 동시에 보유할 수 있는 최대 심볼 수</p>
                    </div>
                </div>
                <div class="flex space-x-3 mt-6">
                    <button type="button" onclick="renderSubscribeAccountPicker(${strategyId})" class="btn btn-secondary flex-1">취소</button>
                    <button type="submit" class="btn btn-primary flex-1">구독</button>
                </div>
            </form>
        </div>
    `;
}

function submitSubscribeSettings(event, strategyId, accountId) {
    event.preventDefault();
    const form = document.getElementById('subscribeSettingsForm');
    const fd = new FormData(form);
    const weight = parseFloat(fd.get('weight'));
    const leverage = parseFloat(fd.get('leverage'));
    const maxSymbolsRaw = (fd.get('max_symbols') || '').toString().trim();

    if (!(weight > 0 && weight <= 10)) {
        showToast('가중치는 0.1~10.0 사이여야 합니다.', 'error');
        return;
    }
    if (!(leverage >= 1 && leverage <= 100)) {
        showToast('레버리지는 1~100 사이여야 합니다.', 'error');
        return;
    }
    const body = { account_id: accountId, weight, leverage };
    if (maxSymbolsRaw) {
        const ms = parseInt(maxSymbolsRaw);
        if (!(ms >= 1 && ms <= 100)) {
            showToast('최대 심볼 수는 1~100 사이의 정수여야 합니다.', 'error');
            return;
        }
        body.max_symbols = ms;
    }
    fetch(`/api/strategies/${strategyId}/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
        body: JSON.stringify(body)
    })
    .then(handleApiResponse)
    .then(data => {
        if (data.success) {
            const payload = getPayload(data);
            showToast('구독이 완료되었습니다.', 'success');
            closeAccountModal();
            loadSubscribedStrategies();
        } else {
            showToast('구독 실패: ' + getErrorMessage(data), 'error');
        }
    })
    .catch(err => showToast('구독 중 오류: ' + err.message, 'error'));
}

async function subscribeStrategy(strategyId, accountId) {
    // 입력값 수집 및 검증
    const weightEl = document.getElementById(`weight-${accountId}`);
    const leverageEl = document.getElementById(`leverage-${accountId}`);
    const maxSymbolsEl = document.getElementById(`maxsymbols-${accountId}`);

    const weight = parseFloat(weightEl?.value || '1.0');
    const leverage = parseFloat(leverageEl?.value || '1.0');
    const maxSymbolsRaw = maxSymbolsEl?.value?.trim();

    if (!(weight > 0 && weight <= 10)) {
        showToast('가중치는 0.1~10.0 사이여야 합니다.', 'error');
        return;
    }
    if (!(leverage >= 1 && leverage <= 100)) {
        showToast('레버리지는 1~100 사이여야 합니다.', 'error');
        return;
    }

    const body = { account_id: accountId, weight, leverage };
    if (maxSymbolsRaw) {
        const ms = parseInt(maxSymbolsRaw);
        if (!(ms >= 1 && ms <= 100)) {
            showToast('최대 심볼 수는 1~100 사이의 정수여야 합니다.', 'error');
            return;
        }
        body.max_symbols = ms;
    }

    try {
        await apiCall(`/api/strategies/${strategyId}/subscribe`, {
            method: 'POST',
            body
        });
        showToast('구독이 완료되었습니다.', 'success');
        closeAccountModal();
        loadSubscribedStrategies();
    } catch (error) {
        // apiCall이 자동으로 에러 토스트 표시
    }
}

async function unsubscribeStrategy(strategyId, accountId) {
    if (!confirm('이 전략에서 해당 계좌의 구독을 해제하시겠습니까? 활성 포지션이 있으면 해제할 수 없습니다.')) {
        return;
    }

    try {
        await apiCall(`/api/strategies/${strategyId}/subscribe/${accountId}`, { method: 'DELETE' });
        showToast('구독이 해제되었습니다.', 'success');
        loadSubscribedStrategies();
    } catch (error) {
        // apiCall이 자동으로 에러 토스트 표시
    }
}

// @FEAT:modal-management @COMP:route @TYPE:helper
async function openPublicDetail(strategyId) {
    const modalContent = document.getElementById('accountModalContent');

    await openModal('accountModal', {
        onOpen: async () => {
            renderState(modalContent, 'loading');

            try {
                const data = await apiCall(`/api/strategies/public/${strategyId}`, { autoErrorToast: false });
                const s = data.strategy;

                if (!s) {
                    throw new Error('전략 정보를 찾을 수 없습니다.');
                }

                modalContent.innerHTML = `
                    <div class="space-y-4">
                        <div>
                            <div class="text-lg font-semibold text-primary">${s.name}</div>
                            <div class="text-sm text-muted">${s.description || ''}</div>
                            <div class="text-xs text-secondary mt-1">마켓: ${s.market_type.toUpperCase()}</div>
                        </div>
                        <div class="flex justify-end space-x-2">
                            <button class="btn btn-secondary" onclick="renderSubscribeAccountPicker(${s.id})">계좌 선택하여 구독</button>
                        </div>
                    </div>
                `;
            } catch (error) {
                renderState(modalContent, 'error', {
                    message: error.message,
                    onRetry: () => openPublicDetail(strategyId)
                });
            }
        }
    });
}
