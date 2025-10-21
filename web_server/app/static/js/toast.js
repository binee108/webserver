'use strict';

/**
 * Toast Notification System with Debug Logging
 *
 * @FEAT:toast-system @COMP:util @TYPE:core
 *
 * Features:
 * - Toast creation and display with animations
 * - FIFO queue management (MAX_TOASTS = 10)
 * - Auto-removal with configurable duration
 * - DEBUG mode lifecycle logging (7 log points)
 *
 * Debug Logging:
 * - Tracks full toast lifecycle: creation → display → removal
 * - Logs container management, toast counts, performance metrics
 * - DEBUG mode only (zero production impact)
 * - Enable: ?debug=true URL parameter or enableDebugMode() in console
 *
 * Log Points:
 * 1-3: Container management (creation/existence checks)
 * 4-5: Toast display (trigger, completion with elapsed time)
 * 6-7: Toast removal (start, completion with remaining count)
 *
 * Dependencies:
 * - logger.js (optional): Structured logging with DEBUG mode
 * - Fallback: No-op functions if logger.js not loaded
 *
 * @see docs/FEATURE_CATALOG.md for complete feature documentation
 */
(function (window) {
    // Logger 참조 (logger.js 미로드 시 no-op 폴백으로 프로덕션 안전 보장)
    const logger = window.logger || {
        debug: () => {},  // DEBUG 전용 - 조용히 무시
        info: console.info.bind(console),
        warn: console.warn.bind(console),
        error: console.error.bind(console)
    };

    /**
     * Ensures toast container exists in DOM
     * Creates container dynamically if not found
     *
     * @returns {HTMLElement} Toast container element
     * @debug Logs container creation/existence status
     */
    function ensureToastContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            logger.debug('Toast', 'Container not found, creating dynamically');
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
            logger.debug('Toast', 'Container created', { id: container.id });
        } else {
            logger.debug('Toast', 'Container already exists');
        }
        return container;
    }

    /**
     * Displays a toast notification with optional auto-removal
     *
     * @param {string} message - Toast message content (truncated to 100 chars in logs)
     * @param {string} type - Toast type: 'success', 'info', 'warning', 'error'
     * @param {number} duration - Auto-removal delay in ms (0 = no auto-removal)
     * @debug Logs toast trigger, display completion, elapsed time, current count
     */
    function showToast(message, type = 'info', duration = 5000) {
        const startTime = performance.now();  // 토스트 생성 소요시간 측정용
        const truncatedMsg = message.length > 100 ? message.substring(0, 100) + '...' : message;  // 로그 가독성

        logger.debug('Toast', 'Toast triggered', {
            type,
            duration,
            message: truncatedMsg
        });

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
        /**
         * Removes toast with slide-out animation
         * Called by close button click or auto-removal timeout
         *
         * @debug Logs removal start and completion with remaining toast count
         */
        const removeToast = () => {
            logger.debug('Toast', 'Removing toast', { type });
            toast.classList.remove('slide-in');
            toast.classList.add('slide-out');
            setTimeout(() => {
                if (toast.parentNode) {
                    const remainingCount = toastContainer.children.length - 1;  // 제거 후 예상 개수
                    toast.remove();
                    logger.debug('Toast', 'Toast removed', { type, remaining: remainingCount });
                }
            }, 300);
        };

        closeButton.addEventListener('click', removeToast);
        toastContainer.appendChild(toast);

        if (duration > 0) {
            setTimeout(removeToast, duration);
        }

        const currentCount = toastContainer.children.length;
        const elapsed = (performance.now() - startTime).toFixed(2);

        logger.debug('Toast', 'Toast displayed', {
            type,
            count: currentCount,
            elapsed: `${elapsed}ms`
        });

        return toast;
    }

    // 전역으로 노출
    window.showToast = showToast;
})(window);

/**
 * Usage Examples:
 *
 * Basic Usage:
 *   showToast('작업 완료', 'success', 3000);
 *   showToast('오류 발생', 'error', 5000);
 *
 * Debug Mode:
 *   // URL 파라미터로 활성화
 *   https://example.com/page?debug=true
 *
 *   // 콘솔에서 활성화
 *   enableDebugMode();
 *   showToast('Test', 'info', 2000);
 *   // 예상 로그:
 *   // 🔍 Toast Toast triggered { type: 'info', duration: 2000, message: 'Test' }
 *   // 🔍 Toast Toast displayed { type: 'info', count: 1, elapsed: '1.23ms' }
 *   // ... (2초 후)
 *   // 🔍 Toast Removing toast { type: 'info' }
 *   // 🔍 Toast Toast removed { type: 'info', remaining: 0 }
 *
 *   // 디버그 모드 비활성화
 *   disableDebugMode();
 *
 * No Logger Fallback:
 *   // logger.js 미로드 시에도 에러 없이 작동
 *   // debug 로그만 무시되고 info/warn/error는 console 사용
 */
