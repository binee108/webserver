// @FEAT:strategy-capital @COMP:service @TYPE:core
// Depends on: strategies-api.js (apiCall, renderState), strategies-modal.js (openModal, closeCapitalModal), strategies-core.js (getCSRFToken)

// WHY: 자본 재분배 관리 로직 분리

'use strict';

// @FEAT:modal-management @COMP:route @TYPE:helper
function openCapitalModal(strategyId) {
    openModal('capitalModal', {
        onOpen: () => loadCapitalModal(strategyId)
    });
}

async function loadCapitalModal(strategyId) {
    const modalContent = document.getElementById('capitalModalContent');
    renderState(modalContent, 'loading');

    try {
        const data = await apiCall(`/api/strategies/${strategyId}/accounts`, { autoErrorToast: false });
        renderCapitalModal(strategyId, data.accounts || []);
    } catch (error) {
        renderState(modalContent, 'error', {
            message: error.message,
            onRetry: () => loadCapitalModal(strategyId)
        });
    }
}

function renderCapitalModal(strategyId, accounts) {
    const modalContent = document.getElementById('capitalModalContent');

    let html = `
        <div class="space-y-6">
            <div class="bg-info bg-opacity-10 border border-info rounded-lg p-4">
                <div class="flex items-start">
                    <svg class="h-5 w-5 text-info mt-0.5 mr-3" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M18 10a8 8 0 100-16 8 8 0 000 16zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
                    </svg>
                    <div>
                        <h4 class="text-sm font-medium text-info">자본 배분 안내</h4>
                        <p class="text-sm text-info mt-1">자본 배분은 계좌 연결 시 자동으로 설정됩니다. 수동 조정은 향후 업데이트에서 지원될 예정입니다.</p>
                    </div>
                </div>
            </div>
    `;

    if (accounts.length === 0) {
        html += '<div class="text-center py-8 text-muted">연결된 계좌가 없습니다.</div>';
    } else {
        html += '<div class="space-y-4">';

        accounts.forEach(account => {
            const allocated = Number(account.allocated_capital ?? 0);
            const currentPnl = Number(account.current_pnl ?? 0);
            html += `
                <div class="card-inner">
                    <div class="flex items-center justify-between mb-3">
                        <div class="flex items-center space-x-3">
                            <div class="w-8 h-8 bg-accent bg-opacity-20 rounded-full flex items-center justify-center">
                                <span class="text-sm font-bold text-accent">${account.exchange.toUpperCase().charAt(0)}</span>
                            </div>
                            <div>
                                <div class="font-medium text-primary">${account.exchange.charAt(0).toUpperCase() + account.exchange.slice(1)} - ${account.name}</div>
                                <div class="text-sm text-muted">가중치: ${account.weight} | 레버리지: ${account.leverage}x</div>
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="badge badge-success">$${allocated.toFixed(2)}</div>
                            <div class="text-sm text-muted mt-1">할당된 자본</div>
                        </div>
                    </div>

                    ${currentPnl !== 0 ? `
                        <div class="flex items-center justify-between">
                            <span class="text-sm text-muted">현재 PnL</span>
                            <span class="badge ${currentPnl >= 0 ? 'badge-success' : 'badge-error'}">
                                ${currentPnl >= 0 ? '+' : ''}$${currentPnl.toFixed(2)}
                            </span>
                        </div>
                    ` : ''}
                </div>
            `;
        });

        html += '</div>';

        // 총 할당 자본 표시
        const totalAllocated = accounts.reduce((sum, acc) => sum + (Number(acc.allocated_capital) || 0), 0);
        const totalPnl = accounts.reduce((sum, acc) => sum + (Number(acc.current_pnl) || 0), 0);

        html += `
            <div class="border-t border-color pt-4">
                <div class="flex items-center justify-between">
                    <span class="font-medium text-primary">총 할당 자본</span>
                    <span class="badge badge-info">$${totalAllocated.toFixed(2)}</span>
                </div>
                ${totalPnl !== 0 ? `
                    <div class="flex items-center justify-between mt-2">
                        <span class="font-medium text-primary">총 PnL</span>
                        <span class="badge ${totalPnl >= 0 ? 'badge-success' : 'badge-error'}">
                            ${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}
                        </span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    html += '</div>';
    modalContent.innerHTML = html;
}

// @FEAT:capital-management @COMP:ui @TYPE:core
/**
 * 전략 자본 재할당 트리거
 * Phase 5.1: force=true 고정, 2단계 확인 모달 추가
 */
async function triggerCapitalReallocation(event) {
    event.preventDefault();

    // 2단계 확인 모달
    const confirmed = confirm(
        "⚠️ 주의: 다음 작업이 즉시 실행됩니다:\n\n" +
        "1. 모든 활성 포지션 무시\n" +
        "2. 거래소별 자본 완전 재할당\n" +
        "3. 기존 설정 덮어쓰기\n\n" +
        "이 작업은 되돌릴 수 없습니다.\n" +
        "계속하시겠습니까?"
    );

    if (!confirmed) {
        return;
    }

    const button = event.target.closest('button');

    // 버튼 비활성화 및 로딩 상태
    button.disabled = true;
    const originalText = button.innerHTML;
    button.innerHTML = '<svg class="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> 재할당 중...';

    try {
        const response = await fetch('/api/capital/auto-rebalance-all', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ force: true })  // 항상 force=true
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '재할당 실패');
        }

        if (data.success) {
            const { total_accounts, rebalanced, skipped, forced } = data.data;

            if (total_accounts === 0) {
                showToast('활성 계좌가 없습니다', 'warning');
            } else if (rebalanced > 0) {
                showToast(
                    `${rebalanced}개 계좌 재할당 완료 (강제 실행) - 총 ${total_accounts}개 중 ${skipped}개 건너뜀`,
                    'success'
                );
            } else {
                showToast(
                    `모든 계좌가 조건을 만족하지 않습니다 (${skipped}개 건너뜀)`,
                    'info'
                );
            }
        } else {
            throw new Error(data.error || '알 수 없는 오류');
        }
    } catch (error) {
        console.error('자본 재할당 오류:', error);
        showToast(`재할당 실패: ${error.message}`, 'error');
    } finally {
        // 버튼 복원
        button.disabled = false;
        button.innerHTML = originalText;
    }
}
