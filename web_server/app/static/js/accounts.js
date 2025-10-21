// @FEAT:account-management @COMP:route @TYPE:core
'use strict';

(function (window, document) {
    // showToast는 toast.js에서 전역으로 제공됨

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    function getErrorMessage(data, fallback = '알 수 없는 오류가 발생했습니다.') {
        if (!data || typeof data !== 'object') {
            return fallback;
        }

        if (typeof data.error === 'string') {
            return data.error;
        }

        if (data.error && typeof data.error === 'object' && data.error.message) {
            return data.error.message;
        }

        if (typeof data.message === 'string') {
            return data.message;
        }

        return fallback;
    }

    async function apiRequest(url, { method = 'GET', headers = {}, body, parse = true } = {}) {
        const config = {
            method,
            headers: {
                'X-CSRFToken': getCsrfToken(),
                ...headers,
            },
        };

        if (body !== undefined && body !== null) {
            if (body instanceof FormData) {
                config.body = body;
            } else {
                if (!config.headers['Content-Type']) {
                    config.headers['Content-Type'] = 'application/json';
                }
                config.body = typeof body === 'string' ? body : JSON.stringify(body);
            }
        }

        const response = await fetch(url, config);

        if (!parse) {
            if (!response.ok) {
                throw new Error(`요청이 실패했습니다. (HTTP ${response.status})`);
            }
            return response;
        }

        let data;
        try {
            data = await response.json();
        } catch (error) {
            const parseError = new Error('서버 응답을 해석할 수 없습니다.');
            parseError.cause = error;
            parseError.httpStatus = response.status;
            throw parseError;
        }

        if (!response.ok || data?.success === false) {
            const message = getErrorMessage(data, `요청이 실패했습니다. (HTTP ${response.status})`);
            const apiError = new Error(message);
            apiError.payload = data;
            apiError.httpStatus = response.status;
            throw apiError;
        }

        return data;
    }

    function extractPayload(data) {
        if (!data || typeof data !== 'object') {
            return {};
        }
        return data.data || {};
    }

    function formatTimestamp(isoString) {
        if (!isoString) {
            return '---';
        }
        const date = new Date(isoString);
        if (Number.isNaN(date.getTime())) {
            return isoString;
        }
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day} ${hours}:${minutes}`;
    }

    function normalizeNumber(value) {
        const num = Number(value);
        return Number.isFinite(num) ? num : null;
    }

    function updateAccountBalanceDisplay(accountId, totalBalance, snapshotAt, marketSummaries = null) {
        const spotBalanceCell = document.getElementById(`account-spot-balance-${accountId}`);
        const futuresBalanceCell = document.getElementById(`account-futures-balance-${accountId}`);
        const snapshotCell = document.getElementById(`account-balance-date-${accountId}`);
        const updatedCell = document.getElementById(`account-updated-${accountId}`);

        let spotBalance = null;
        let futuresBalance = null;

        if (Array.isArray(marketSummaries)) {
            marketSummaries.forEach((summary) => {
                const total = normalizeNumber(summary.total_balance);
                if (summary.market_type === 'spot') {
                    spotBalance = total;
                } else if (summary.market_type === 'futures') {
                    futuresBalance = total;
                }
            });
        }

        if (spotBalanceCell) {
            if (typeof spotBalance === 'number' && !Number.isNaN(spotBalance)) {
                spotBalanceCell.textContent = `$${spotBalance.toFixed(2)}`;
            } else {
                spotBalanceCell.textContent = '---';
            }
            spotBalanceCell.classList.add('highlight-update');
            window.setTimeout(() => spotBalanceCell.classList.remove('highlight-update'), 600);
        }

        if (futuresBalanceCell) {
            if (typeof futuresBalance === 'number' && !Number.isNaN(futuresBalance)) {
                futuresBalanceCell.textContent = `$${futuresBalance.toFixed(2)}`;
            } else {
                futuresBalanceCell.textContent = '---';
            }
            futuresBalanceCell.classList.add('highlight-update');
            window.setTimeout(() => futuresBalanceCell.classList.remove('highlight-update'), 600);
        }

        if (snapshotCell) {
            snapshotCell.textContent = snapshotAt ? formatTimestamp(snapshotAt) : '---';
        }

        if (updatedCell) {
            updatedCell.textContent = formatTimestamp(new Date().toISOString());
        }
    }

    async function refreshAccountBalance(accountId) {
        const data = await apiRequest(`/api/accounts/${accountId}/balance`, { method: 'GET' });
        const payload = extractPayload(data).balance || {};
        const totalBalance = normalizeNumber(payload.total_balance);

        updateAccountBalanceDisplay(
            accountId,
            totalBalance,
            payload.snapshot_at,
            payload.market_summaries
        );

        return totalBalance;
    }

    function openAddAccountModal() {
        document.getElementById('modalTitle').textContent = '계좌 추가';
        document.getElementById('accountForm').reset();
        document.getElementById('accountId').value = '';

        const apiSecretField = document.getElementById('secret_api');
        apiSecretField.required = true;
        apiSecretField.placeholder = '';

        const passphraseField = document.getElementById('passphrase');
        passphraseField.placeholder = '';

        document.getElementById('accountModal').classList.remove('hidden');
    }

    function closeAccountModal() {
        document.getElementById('accountModal').classList.add('hidden');
    }

    async function editAccount(event, accountId) {
        const button = event?.currentTarget || event?.target?.closest('button');
        const originalContent = button?.innerHTML;

        if (button) {
            button.disabled = true;
            button.innerHTML = '<div class="loading-spinner"></div>불러오는 중...';
        }

        try {
            const data = await apiRequest(`/api/accounts/${accountId}`, { method: 'GET' });
            const payload = extractPayload(data);
            const accountData = payload.account;

            if (!accountData) {
                throw new Error('계좌 정보를 찾을 수 없습니다.');
            }

            document.getElementById('modalTitle').textContent = '계좌 수정';
            document.getElementById('accountId').value = accountId;
            document.getElementById('exchange').value = accountData.exchange || '';
            document.getElementById('name').value = accountData.name || '';
            document.getElementById('public_api').value = accountData.public_api_full || '';

            const apiSecretField = document.getElementById('secret_api');
            const passphraseField = document.getElementById('passphrase');

            apiSecretField.value = '';
            apiSecretField.placeholder = '변경하지 않으려면 비워두세요';
            apiSecretField.required = false;

            passphraseField.value = '';
            passphraseField.placeholder = '변경하지 않으려면 비워두세요';

            document.getElementById('is_testnet').checked = Boolean(accountData.is_testnet);
            document.getElementById('accountModal').classList.remove('hidden');
        } catch (error) {
            showToast(error.message || '계좌 정보를 불러오는 중 오류가 발생했습니다.', 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.innerHTML = originalContent;
            }
        }
    }

    async function deleteAccount(event, accountId) {
        if (!window.confirm('정말로 이 계좌를 삭제하시겠습니까?')) {
            return;
        }

        const button = event?.currentTarget || event?.target?.closest('button');
        const originalContent = button?.innerHTML;

        if (button) {
            button.disabled = true;
            button.innerHTML = '<div class="loading-spinner"></div>삭제 중...';
        }

        try {
            await apiRequest(`/api/accounts/${accountId}`, { method: 'DELETE' });
            showToast('계좌가 성공적으로 삭제되었습니다.', 'success');
            window.setTimeout(() => window.location.reload(), 1500);
        } catch (error) {
            showToast(error.message || '삭제 중 오류가 발생했습니다.', 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.innerHTML = originalContent;
            }
        }
    }

    async function testConnection(event, accountId) {
        const button = event?.currentTarget || event?.target?.closest('button');
        const originalContent = button?.innerHTML;

        if (button) {
            button.disabled = true;
            button.innerHTML = '<div class="loading-spinner"></div>테스트 중...';
        }

        try {
            const data = await apiRequest(`/api/accounts/${accountId}/test`, { method: 'POST' });
            const payload = extractPayload(data);
            const totalBalance = normalizeNumber(payload.total_balance);

            updateAccountBalanceDisplay(
                accountId,
                totalBalance,
                payload.snapshot_at,
                payload.market_summaries
            );

            if (totalBalance !== null) {
                showToast(`연결 테스트가 성공했습니다! 총 자산: $${totalBalance.toFixed(2)}`, 'success');
            } else {
                showToast('연결 테스트가 성공했습니다.', 'success');
            }
        } catch (error) {
            showToast(error.message || '연결 테스트 중 오류가 발생했습니다.', 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.innerHTML = originalContent;
            }
        }
    }

    // @FEAT:capital-management @COMP:route @TYPE:core
    async function triggerCapitalReallocation(event) {
        /**
         * Phase 2.2: 자본 재할당 수동 트리거
         *
         * API: POST /api/capital/auto-rebalance-all
         * 응답: {success, data: {total_accounts, rebalanced, skipped, results}}
         */
        const button = event?.currentTarget || event?.target?.closest('button');
        const originalContent = button?.innerHTML;

        if (button) {
            button.disabled = true;
            button.innerHTML = '<div class="loading-spinner"></div>재할당 중...';
        }

        try {
            const data = await apiRequest('/api/capital/auto-rebalance-all', { method: 'POST' });
            const payload = extractPayload(data);

            const totalAccounts = payload.total_accounts || 0;
            const rebalanced = payload.rebalanced || 0;
            const skipped = payload.skipped || 0;

            if (totalAccounts === 0) {
                showToast('활성 계좌가 없습니다.', 'info');
            } else if (rebalanced > 0) {
                showToast(`자본 재할당 완료: ${rebalanced}개 계좌 처리됨 (${skipped}개 건너뜀)`, 'success');
            } else {
                showToast(`자본 재할당: 모든 계좌가 재할당 조건을 만족하지 않습니다.`, 'info');
            }
        } catch (error) {
            console.error('자본 재할당 오류:', error);
            showToast(error.message || '자본 재할당 중 오류가 발생했습니다', 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.innerHTML = originalContent;
            }
        }
    }

    async function refreshAllBalances(event) {
        const button = event?.currentTarget || event?.target?.closest('button');
        const originalContent = button?.innerHTML;

        if (button) {
            button.disabled = true;
            button.innerHTML = '<div class="loading-spinner"></div>전체 새로고침...';
        }

        const rows = document.querySelectorAll('[data-account-id]');
        const accountIds = Array.from(rows).map((row) => row.dataset.accountId).filter(Boolean);

        if (!accountIds.length) {
            showToast('갱신할 계좌가 없습니다.', 'warning');
            if (button) {
                button.disabled = false;
                button.innerHTML = originalContent;
            }
            return;
        }

        let successCount = 0;
        for (const accountId of accountIds) {
            try {
                const totalBalance = await refreshAccountBalance(accountId);
                if (totalBalance !== null) {
                    successCount += 1;
                }
            } catch (error) {
                showToast(`계좌 ${accountId} 잔고 갱신 실패: ${error.message}`, 'error');
            }
        }

        if (successCount > 0) {
            showToast(`${successCount}개 계좌 잔고가 업데이트되었습니다.`, 'success');
        } else {
            showToast('계좌 잔고를 갱신하지 못했습니다.', 'error');
        }

        if (button) {
            button.disabled = false;
            button.innerHTML = originalContent;
        }
    }

    // @FEAT:account-management @COMP:route @TYPE:core
    async function submitAccount(event) {
        /**
         * 계좌 추가/수정 폼 제출 핸들러
         *
         * Phase 2 수정 (2025-10-13):
         * - 계좌 수정 시 변경되지 않은 API 키 필드를 요청에서 제외
         * - 백엔드의 불필요한 캐시 무효화 방지
         *
         * Edge Cases:
         * - 새 계좌 추가: 모든 API 키 필드 필수
         * - 계좌 수정: 빈 문자열/null인 필드는 요청에 포함하지 않음
         *
         * Related Issue: Variable Shadowing 버그 수정 (Phase 1)
         */
        event.preventDefault();

        const form = document.getElementById('accountForm');
        const formData = new FormData(form);
        const accountId = document.getElementById('accountId').value;

        const apiSecret = formData.get('secret_api');
        const passphrase = formData.get('passphrase');

        if (!accountId && (!apiSecret || apiSecret.toString().trim() === '')) {
            showToast('새 계좌 추가 시 API Secret은 필수입니다.', 'error');
            return;
        }

        const payload = {
            name: formData.get('name'),
            exchange: formData.get('exchange'),
            is_testnet: formData.get('is_testnet') === 'on',
        };

        if (!accountId) {
            // 새 계좌 추가: 모든 API 키 필수
            payload.public_api = formData.get('public_api');
            payload.secret_api = apiSecret;
            payload.passphrase = passphrase || '';
        } else {
            // 계좌 수정: 변경된 필드만 포함 (Phase 2 개선)
            const publicApi = formData.get('public_api');
            if (publicApi && publicApi.toString().trim() !== '') {
                payload.public_api = publicApi;
            }
            if (apiSecret && apiSecret.toString().trim() !== '') {
                payload.secret_api = apiSecret;
            }
            if (passphrase && passphrase.toString().trim() !== '') {
                payload.passphrase = passphrase;
            }
        }

        const url = accountId ? `/api/accounts/${accountId}` : '/api/accounts';
        const method = accountId ? 'PUT' : 'POST';

        const submitButton = form.querySelector('button[type="submit"]');
        const originalText = submitButton?.innerHTML;
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<div class="loading-spinner"></div>저장 중...';
        }

        try {
            await apiRequest(url, { method, body: payload });
            showToast('계좌가 성공적으로 저장되었습니다.', 'success');
            closeAccountModal();
            window.setTimeout(() => window.location.reload(), 1500);
        } catch (error) {
            showToast(error.message || '저장 중 오류가 발생했습니다.', 'error');
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.innerHTML = originalText;
            }
        }
    }

    function attachModalListeners() {
        const modal = document.getElementById('accountModal');
        if (modal) {
            modal.addEventListener('click', (event) => {
                if (event.target === modal) {
                    closeAccountModal();
                }
            });
        }

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeAccountModal();
            }
        });
    }

    function initialize() {
        attachModalListeners();
    }

    document.addEventListener('DOMContentLoaded', initialize);

    window.openAddAccountModal = openAddAccountModal;
    window.closeAccountModal = closeAccountModal;
    window.editAccount = editAccount;
    window.deleteAccount = deleteAccount;
    window.testConnection = testConnection;
    window.submitAccount = submitAccount;
    window.refreshAllBalances = refreshAllBalances;
    window.triggerCapitalReallocation = triggerCapitalReallocation;
})(window, document);
