// @FEAT:strategy-crud @COMP:service @TYPE:core
// Depends on: strategies-api.js (apiCall, setButtonLoading), strategies-modal.js (closeStrategyModal)

// WHY: 전략 생성/수정/삭제 로직 분리

'use strict';

async function editStrategy(strategyId) {
    try {
        const data = await apiCall(`/api/strategies/${strategyId}`, { autoErrorToast: false });
        const strategy = data.strategy;

        if (!strategy) {
            throw new Error('전략 데이터를 찾을 수 없습니다.');
        }

        document.getElementById('strategyModalTitle').textContent = '전략 수정';
        document.getElementById('strategyId').value = strategy.id;
        document.getElementById('name').value = strategy.name || '';
        document.getElementById('description').value = strategy.description || '';
        document.getElementById('group_name').value = strategy.group_name || '';
        document.getElementById('market_type').value = strategy.market_type ? strategy.market_type.toLowerCase() : '';
        document.getElementById('is_active').checked = strategy.is_active || false;
        document.getElementById('is_public').checked = strategy.is_public || false;

        document.getElementById('strategyModal').classList.remove('hidden');
    } catch (error) {
        showToast('전략 정보를 불러오는 중 오류가 발생했습니다: ' + error.message, 'error');
    }
}

async function deleteStrategy(strategyId) {
    if (!confirm('정말로 이 전략을 삭제하시겠습니까? 연결된 계좌와 포지션이 있는 경우 삭제할 수 없습니다.')) {
        return;
    }

    try {
        await apiCall(`/api/strategies/${strategyId}`, { method: 'DELETE' });
        showToast('전략이 성공적으로 삭제되었습니다.', 'success');
        setTimeout(() => location.reload(), 1500);
    } catch (error) {
        // apiCall이 자동으로 에러 토스트 표시
    }
}

async function submitStrategy(event) {
    event.preventDefault();

    const form = document.getElementById('strategyForm');
    const formData = new FormData(form);
    const strategyId = document.getElementById('strategyId').value;

    const data = {
        name: formData.get('name'),
        description: formData.get('description'),
        group_name: formData.get('group_name'),
        market_type: formData.get('market_type'),
        is_active: formData.get('is_active') === 'on',
        is_public: formData.get('is_public') === 'on'
    };

    const url = strategyId ? `/api/strategies/${strategyId}` : '/api/strategies';
    const method = strategyId ? 'PUT' : 'POST';
    const submitButton = form.querySelector('button[type="submit"]');

    setButtonLoading(submitButton, true, '저장 중...');

    try {
        await apiCall(url, { method, body: data });
        showToast(strategyId ? '전략이 성공적으로 수정되었습니다.' : '전략이 성공적으로 생성되었습니다.', 'success');
        closeStrategyModal();
        setTimeout(() => location.reload(), 1500);
    } catch (error) {
        // apiCall이 자동으로 에러 토스트 표시
    } finally {
        setButtonLoading(submitButton, false);
    }
}
