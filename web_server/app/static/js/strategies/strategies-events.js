// @FEAT:strategy-management @COMP:ui @TYPE:core
// Depends on: strategies-core.js, strategies-rendering.js, strategies-api.js, strategies-modal.js, strategies-ui.js, strategies-data.js, strategies-subscription.js, strategies-crud.js, strategies-accounts.js, strategies-capital.js

// WHY: 이벤트 리스너 초기화 로직 분리 (DOMContentLoaded)
// Event initialization for strategy page - modal management, form submissions, and user interactions

'use strict';

// 전략 토글 이벤트
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.strategy-toggle').forEach(toggle => {
        toggle.addEventListener('change', function() {
            const strategyId = this.dataset.strategyId;
            const isActive = this.checked;
            const toggleElement = this;

            fetch(`/api/strategies/${strategyId}/toggle`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                }
            })
            .then(handleApiResponse)
            .then(data => {
                if (data.success) {
                    showToast(data.message, 'success');

                    // 상태 배지 업데이트
                    const strategyCard = document.getElementById(`strategy-card-${strategyId}`);
                    if (strategyCard) {
                        const statusBadge = strategyCard.querySelector('.status-badge');
                        const payload = getPayload(data);
                        const activeState = typeof payload.is_active === 'boolean' ? payload.is_active : isActive;

                        if (statusBadge) {
                            if (activeState) {
                                statusBadge.className = 'status-badge active';
                                statusBadge.innerHTML = '<div class="status-dot active"></div>활성';
                            } else {
                                statusBadge.className = 'status-badge inactive';
                                statusBadge.innerHTML = '<div class="status-dot inactive"></div>비활성';
                            }
                        }
                    }
                } else {
                    showToast('상태 변경 실패: ' + getErrorMessage(data), 'error');
                    // 토글 상태 되돌리기
                    toggleElement.checked = !isActive;
                }
            })
            .catch(error => {
                showToast('상태 변경 중 오류가 발생했습니다: ' + error.message, 'error');
                // 토글 상태 되돌리기
                toggleElement.checked = !isActive;
            });
        });
    });

    // @FEAT:modal-management @COMP:util @TYPE:core
    // WHY: 이벤트 위임 패턴으로 메모리 효율성 개선 (querySelectorAll 루프 제거).
    //      preventBackdropClose dataset 지원으로 특수 케이스 처리.
    //      ESC 키는 최상위 모달만 닫도록 개선 (모달 중첩 시).

    // 백드롭 클릭으로 모달 닫기 (이벤트 위임)
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-overlay') && !e.target.classList.contains('hidden')) {
            // preventBackdropClose 체크
            if (e.target.dataset.preventBackdropClose !== 'true') {
                e.target.classList.add('hidden');
                delete e.target.dataset.preventBackdropClose;
            }
        }
    });

    // ESC 키로 최상위 모달 닫기
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const visibleModals = document.querySelectorAll('.modal-overlay:not(.hidden)');
            if (visibleModals.length > 0) {
                const topModal = visibleModals[visibleModals.length - 1]; // 최상위 모달
                if (topModal.dataset.preventBackdropClose !== 'true') {
                    topModal.classList.add('hidden');
                    delete topModal.dataset.preventBackdropClose;
                }
            }
        }
    });
});
