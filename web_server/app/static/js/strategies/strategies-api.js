// @FEAT:api-integration @COMP:util @TYPE:core
// API integration utilities for strategies page - API calls, state rendering, response handling
// Depends on: strategies-core.js (getCSRFToken)
'use strict';

// === Integrated API & State Rendering Functions ===

// @FEAT:api-integration @COMP:util @TYPE:core
// WHY: 18곳의 중복 fetch 호출 패턴을 1개 함수로 통합하여 유지보수성 향상.
//      CSRF 토큰, 에러 처리, 토스트 표시를 자동화하여 일관성 확보.
//      향후 새 API 호출 추가 시 3-5줄로 구현 가능 (기존 15-20줄 대비).
/**
 * 통합 API 호출 함수
 * @param {string} url - API 엔드포인트 URL
 * @param {Object} options - 옵션
 * @param {string} [options.method='GET'] - HTTP 메서드
 * @param {Object} [options.body] - 요청 바디 (자동으로 JSON.stringify)
 * @param {Object} [options.headers] - 추가 헤더
 * @param {Function} [options.onError] - 커스텀 에러 핸들러
 * @param {boolean} [options.autoErrorToast=true] - 자동 에러 토스트 표시 여부
 * @param {boolean} [options.throwOnFailure=true] - data.success === false일 때 에러로 간주 여부
 * @returns {Promise<Object>} API 응답 데이터 (data.data || data.payload || {})
 */
async function apiCall(url, options = {}) {
    const {
        method = 'GET',
        body = null,
        headers = {},
        onError = null,
        autoErrorToast = true,
        throwOnFailure = true
    } = options;

    try {
        // 1. fetch 옵션 구성
        const fetchOptions = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
                ...headers
            }
        };

        if (body && method !== 'GET') {
            fetchOptions.body = JSON.stringify(body);
        }

        // 2. API 호출
        const response = await fetch(url, fetchOptions);
        const data = await response.json();

        // 3. 응답 검증
        if (!response.ok) {
            const error = new Error(getErrorMessage(data, 'API 요청 실패'));
            error.status = response.status;
            error.responseData = data;
            throw error;
        }

        // 4. data.success === false 체크 (옵션에 따라)
        if (data.success === false && throwOnFailure) {
            const error = new Error(getErrorMessage(data, '요청 처리 중 오류가 발생했습니다.'));
            error.responseData = data;
            throw error;
        }

        // 5. 데이터 추출 (기존 getPayload 로직 유지)
        return getPayload(data);

    } catch (error) {
        // 6. 에러 처리
        console.error('API call error:', error);

        // 커스텀 에러 핸들러
        if (onError) {
            onError(error);
        }

        // 자동 에러 토스트
        if (autoErrorToast) {
            showToast(error.message || 'API 요청 중 오류가 발생했습니다.', 'error');
        }

        throw error;
    }
}

// @FEAT:ui-state-management @COMP:util @TYPE:core
// WHY: 20곳의 인라인 로딩/에러 HTML을 1개 함수로 통합하여 UI 일관성 확보.
//      재시도 버튼에 전역 핸들러 방식 사용으로 클로저 직렬화 문제 해결.
/**
 * 통합 상태 렌더링 함수
 * @param {HTMLElement} element - 렌더링 대상 요소
 * @param {string} state - 상태 ('loading', 'error', 'empty', 'success')
 * @param {Object} options - 옵션
 * @param {string} [options.message] - 메시지 (error, empty 상태에서 사용)
 * @param {Function} [options.onRetry] - 재시도 함수 (error 상태에서 사용)
 * @param {string} [options.emptyIcon='inbox'] - 빈 데이터 아이콘 (empty 상태)
 */
function renderState(element, state, options = {}) {
    const { message = '', onRetry = null, emptyIcon = 'inbox' } = options;

    let html = '';

    switch (state) {
        case 'loading':
            html = `
                <div class="flex justify-center items-center py-12">
                    <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                </div>
            `;
            break;

        case 'error':
            // 전역 핸들러 방식으로 재시도 버튼 구현
            const retryId = onRetry ? `retry-${Date.now()}-${Math.random().toString(36).substr(2, 9)}` : null;
            if (onRetry) {
                window._retryHandlers = window._retryHandlers || {};
                window._retryHandlers[retryId] = onRetry;
            }
            const retryButton = retryId ? `
                <button class="btn btn-primary btn-sm mt-4" onclick="window._retryHandlers['${retryId}']()">
                    <i class="fas fa-redo mr-2"></i>다시 시도
                </button>
            ` : '';

            html = `
                <div class="flex flex-col items-center justify-center py-12 text-gray-500">
                    <i class="fas fa-exclamation-circle text-5xl mb-4 text-red-500"></i>
                    <p class="text-lg">${message || '데이터를 불러오는 중 오류가 발생했습니다.'}</p>
                    ${retryButton}
                </div>
            `;
            break;

        case 'empty':
            html = `
                <div class="flex flex-col items-center justify-center py-12 text-gray-400">
                    <i class="fas fa-${emptyIcon} text-5xl mb-4"></i>
                    <p class="text-lg">${message || '데이터가 없습니다.'}</p>
                </div>
            `;
            break;

        default:
            console.warn('Unknown state:', state);
            return;
    }

    element.innerHTML = html;
}

// @FEAT:ui-state-management @COMP:util @TYPE:helper
// WHY: 3곳의 버튼 로딩 상태 관리를 표준화하여 disabled/복구 실패 방지.
//      originalText를 dataset에 저장하여 복구 시 안전하게 원복.
/**
 * 버튼 로딩 상태 토글
 * @param {HTMLButtonElement} button - 버튼 요소
 * @param {boolean} isLoading - 로딩 상태
 * @param {string} [loadingText='처리 중...'] - 로딩 시 표시할 텍스트
 */
function setButtonLoading(button, isLoading, loadingText = '처리 중...') {
    if (isLoading) {
        button.disabled = true;
        button.dataset.originalText = button.innerHTML;
        button.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i>${loadingText}`;
    } else {
        button.disabled = false;
        button.innerHTML = button.dataset.originalText || button.innerHTML;
    }
}

// API 응답 처리 유틸리티 함수들
function getPayload(responseJson) {
    if (!responseJson || typeof responseJson !== 'object') {
        return {};
    }
    return responseJson.data || {};
}

function getErrorMessage(responseJson, fallback = '알 수 없는 오류가 발생했습니다.') {
    if (!responseJson || typeof responseJson !== 'object') {
        return fallback;
    }

    const error = responseJson.error;
    if (typeof error === 'string') {
        return error;
    }
    if (error && typeof error === 'object' && error.message) {
        return error.message;
    }

    return responseJson.message || fallback;
}

// handleApiResponse helper function
function handleApiResponse(response) {
    if (!response.ok) {
        return response.json().then(data => {
            throw new Error(data.error || data.message || 'API 요청 실패');
        });
    }
    return response.json();
}

// @FEAT:futures-validation @COMP:route @TYPE:integration
// NOTE: 이 함수는 apiCall()을 사용하지 않음
// WHY: 초기화 실패 시 console.warn만 표시하므로 사용자 토스트 불필요.
//      페이지 로드 시 1회 실행되는 비차단 초기화 로직.
// 거래소 메타데이터 로드 (페이지 로드 시 1회)
(async function loadExchangeMetadata() {
    try {
        const response = await fetch('/api/system/exchange-metadata');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        window.EXCHANGE_METADATA = data.payload || data; // 하위 호환
        console.log('✅ Exchange metadata loaded');
    } catch (error) {
        console.warn('⚠️ Failed to load exchange metadata, validation will be skipped:', error);
        window.EXCHANGE_METADATA = null;
    }
})();
