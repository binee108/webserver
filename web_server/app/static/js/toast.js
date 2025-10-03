'use strict';

/**
 * 통합 토스트 알림 시스템
 * 모든 페이지에서 일관된 토스트 메시지 표시
 */
(function (window) {
    function ensureToastContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }

    function showToast(message, type = 'info', duration = 5000) {
        const toastContainer = ensureToastContainer();

        const toast = document.createElement('div');
        toast.className = `toast ${type} slide-in`;
        toast.innerHTML = `
            <div class="toast-content">
                <span>${message}</span>
                <button type="button" class="toast-close" aria-label="닫기">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                    </svg>
                </button>
            </div>
        `;

        const closeButton = toast.querySelector('.toast-close');
        const removeToast = () => {
            toast.classList.remove('slide-in');
            toast.classList.add('slide-out');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        };

        closeButton.addEventListener('click', removeToast);
        toastContainer.appendChild(toast);

        if (duration > 0) {
            setTimeout(removeToast, duration);
        }

        return toast;
    }

    // 전역으로 노출
    window.showToast = showToast;
})(window);
