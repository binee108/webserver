// @FEAT:strategy-management @COMP:modal @TYPE:core
// Depends on: None (완전 독립)

// WHY: 7곳의 중복 모달 열기 패턴을 1개 함수로 통합하여 유지보수성 향상.
//      백드롭, ESC 키, overflow 제어를 자동화하여 일관성 확보.
//      onOpen 콜백으로 모달별 초기화 로직 분리.
/**
 * 모달을 열고 백드롭/ESC 키 이벤트를 설정합니다.
 * @param {string} modalId - 열 모달의 DOM ID
 * @param {Object} [options={}] - 옵션 객체
 * @param {Function} [options.onOpen] - 모달 열린 후 실행할 콜백 (modal 요소를 인자로 받음)
 * @param {boolean} [options.preventBackdropClose=false] - 백드롭 클릭으로 닫기 방지
 * @example
 * openModal('strategyModal', { onOpen: () => resetForm() })
 * @returns {HTMLElement|null} 열린 모달 요소, 실패 시 null
 */
async function openModal(modalId, options = {}) {
    const { onOpen = null, preventBackdropClose = false } = options;

    const modal = document.getElementById(modalId);
    if (!modal) {
        console.error(`[openModal] Modal not found: ${modalId}`);
        return null;
    }

    // preventBackdropClose 설정 저장
    if (preventBackdropClose) {
        modal.dataset.preventBackdropClose = 'true';
    } else {
        delete modal.dataset.preventBackdropClose;
    }

    // 모달 표시
    modal.classList.remove('hidden');

    // onOpen 콜백 실행
    if (onOpen) {
        await onOpen(modal);
    }

    return modal;
}

// WHY: 3곳의 중복 모달 닫기 패턴을 1개 함수로 통합.
//      일관된 숨김 처리 및 dataset 정리.
/**
 * 모달을 닫습니다.
 * @param {string} modalId - 닫을 모달의 DOM ID
 * @returns {boolean} 성공 시 true, 실패 시 false
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) {
        console.error(`[closeModal] Modal not found: ${modalId}`);
        return false;
    }

    modal.classList.add('hidden');
    delete modal.dataset.preventBackdropClose;

    return true;
}

// @FEAT:modal-management @COMP:route @TYPE:helper
function openAddStrategyModal() {
    openModal('strategyModal', {
        onOpen: () => {
            document.getElementById('strategyModalTitle').textContent = '전략 추가';
            document.getElementById('strategyForm').reset();
            document.getElementById('strategyId').value = '';
        }
    });
}

// @FEAT:modal-management @COMP:route @TYPE:helper
function closeStrategyModal() {
    closeModal('strategyModal');
}

// @FEAT:modal-management @COMP:route @TYPE:helper
function closeAccountModal() {
    closeModal('accountModal');
}

// @FEAT:modal-management @COMP:route @TYPE:helper
function closeCapitalModal() {
    closeModal('capitalModal');
}
