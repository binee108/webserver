// @FEAT:strategy-rendering @COMP:util @TYPE:core
// Rendering utilities for strategies page - Badges, metrics, account items
// Depends on: strategies-core.js (getCurrencySymbol, METRIC_ICONS)
'use strict';

// @FEAT:strategy-rendering @COMP:util @TYPE:core
// WHY: 배지 생성 로직 3곳(Lines 80-110, 854-867, 1674-1683) 중복 제거.
//      활성/비활성, 선물/현물, 공개/비공개 배지 통합하여 일관성 확보.
//      대소문자 혼합 처리로 데이터 정규화.
/**
 * 활성/비활성 상태 배지 생성
 * @param {boolean} isActive - 활성 여부
 * @returns {string} 상태 배지 HTML
 * @example renderStatusBadge(true)
 */
function renderStatusBadge(isActive) {
    if (isActive === null || isActive === undefined) {
        return '';
    }
    const statusClass = isActive ? 'active' : 'inactive';
    const text = isActive ? '활성' : '비활성';
    return `<span class="status-badge ${statusClass}"><div class="status-dot ${statusClass}"></div>${text}</span>`;
}

// @FEAT:strategy-rendering @COMP:util @TYPE:core
// WHY: 마켓 타입 배지 생성 중복 제거 (Lines 789-797, 854-867 등).
//      대소문자 혼합 처리(.toUpperCase()) 추가로 데이터 정규화 강화.
/**
 * 마켓 타입(선물/현물) 배지 생성
 * @param {string} marketType - 마켓 타입 ('FUTURES', 'SPOT', 'futures', 'spot' 등)
 * @returns {string} 마켓 타입 배지 HTML
 * @example renderMarketTypeBadge('FUTURES')
 */
function renderMarketTypeBadge(marketType) {
    if (!marketType) {
        return '';
    }
    const normalized = marketType.toUpperCase();
    const isFutures = normalized === 'FUTURES';
    const typeClass = isFutures ? 'futures' : 'spot';
    const typeText = isFutures ? '선물' : '현물';

    // SVG path 분리 (유지보수성 향상)
    const iconPath = isFutures
        ? 'M13 6a3 3 0 11-6 0 3 3 0 016 0zM18 8a2 2 0 11-4 0 2 2 0 014 0zM14 15a4 4 0 00-8 0v3h8v-3z'
        : 'M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z';

    const svgAttrs = isFutures
        ? 'd'
        : 'fill-rule="evenodd" d';

    return `<span class="market-type-badge ${typeClass}"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path ${svgAttrs}="${iconPath}"${!isFutures ? ' clip-rule="evenodd"' : ''}/></svg>${typeText}</span>`;
}

// @FEAT:strategy-rendering @COMP:util @TYPE:core
// WHY: 공개/비공개 배지 생성 중복 제거 (Lines 772, 854-867 등).
//      배지 스타일 통일로 UI 일관성 향상.
/**
 * 공개/비공개 배지 생성
 * @param {boolean} isPublic - 공개 여부
 * @returns {string} 공개 여부 배지 HTML
 * @example renderPublicBadge(true)
 */
function renderPublicBadge(isPublic) {
    if (isPublic === null || isPublic === undefined) {
        return '';
    }
    const badgeClass = isPublic ? 'badge-accent' : 'badge-secondary';
    const text = isPublic ? '공개' : '비공개';
    return `<span class="badge ${badgeClass} ml-2">${text}</span>`;
}

// @FEAT:strategy-rendering @COMP:util @TYPE:core
// WHY: 메트릭 아이템 렌더링 패턴(아이콘+값+라벨) 3곳 중복 제거(Lines 800-840, 854-867 등).
//      공통 레이아웃 정의로 UI/UX 일관성 및 유지보수성 향상.
/**
 * 메트릭 아이템 렌더링 (아이콘, 값, 라벨)
 * @param {string} iconPath - SVG 경로 데이터
 * @param {number|string} value - 표시할 값
 * @param {string} label - 라벨 텍스트
 * @returns {string} 메트릭 아이템 HTML
 * @example renderMetricItem(METRIC_ICONS.accounts, 3, '계좌')
 */
function renderMetricItem(iconPath, value, label) {
    if (!iconPath || value === null || value === undefined || !label) {
        return '';
    }
    return `
    <div class="metric-item">
      <svg class="metric-icon" viewBox="0 0 20 20" fill="currentColor">
        <path d="${iconPath}"/>
      </svg>
      <div class="metric-content">
        <div class="metric-value">${value}</div>
        <div class="metric-label">${label}</div>
      </div>
    </div>`;
}

// @FEAT:strategy-rendering @COMP:util @TYPE:core
// WHY: 계좌 아이템 렌더링 중복 제거 (Lines 231-240, 854-867, 1674-1683 등).
//      options 패턴으로 유연한 재사용성 제공 (액션 표시 선택 가능).
//      getCurrencySymbol() 활용으로 환율 기호 통일.
/**
 * 계좌 아이템 렌더링
 * @param {Object} account - 계좌 정보 객체
 * @param {string} account.exchange - 거래소명
 * @param {string} account.name - 계좌명
 * @param {number} account.id - 계좌 ID (account_id도 지원)
 * @param {number} account.allocated_capital - 배분 자본금
 * @param {number} account.weight - 가중치
 * @param {number} account.max_symbols - 최대 심볼 수
 * @param {number} account.leverage - 레버리지
 * @param {boolean} account.is_active - 활성 여부
 * @param {Object} [options={}] - 옵션
 * @param {boolean} [options.showActions=false] - 설정/구독 해제 버튼 표시 여부
 * @param {string|number} [options.strategyId=null] - 전략 ID (showActions=true 시 필수)
 * @param {boolean} [options.showInactiveTag=false] - 비활성 태그 표시 여부
 * @returns {string} 계좌 아이템 HTML
 * @example renderAccountItem(account, { showActions: true, strategyId: 123 })
 */
function renderAccountItem(account, options = {}) {
    if (!account) {
        return '';
    }
    const { showActions = false, strategyId = null, showInactiveTag = false } = options;
    const currencySymbol = getCurrencySymbol(account.exchange);
    const allocatedCapital = account.allocated_capital || 0;
    const accountId = account.account_id || account.id;
    const accountLabel = `${account.exchange.toUpperCase()} - ${account.name}`;

    let inactiveTagHtml = '';
    if (showInactiveTag && account.is_active === false) {
        inactiveTagHtml = '<span class="badge badge-secondary ml-2">비활성</span>';
    }

    let detailsHtml = '';
    if (account.weight !== undefined || account.max_symbols || account.leverage) {
        const maxStr = account.max_symbols ? `최대: ${account.max_symbols}개` : '최대: -';
        detailsHtml = `<p>가중치: ${account.weight} | ${maxStr} | 레버리지: ${account.leverage}x</p>`;
    }

    let actionsHtml = '';
    if (showActions && strategyId) {
        actionsHtml = `
      <div class="flex items-center space-x-2">
        <button class="btn btn-secondary btn-xs" onclick="openSubscribeSettings(${strategyId}, ${accountId}, '${accountLabel}')">설정</button>
        <button class="btn btn-error btn-xs" onclick="unsubscribeStrategy(${strategyId}, ${accountId})">구독 해제</button>
      </div>`;
    }

    return `
    <div class="strategy-account-item">
      <div class="strategy-account-info">
        <p>${accountLabel}${inactiveTagHtml}</p>
        ${detailsHtml}
      </div>
      <div class="strategy-account-amount">
        <p class="amount tabular-nums">${currencySymbol}${allocatedCapital.toFixed(2)}</p>
        <p class="currency">USDT</p>
      </div>
      ${actionsHtml}
    </div>`;
}

// @FEAT:strategy-rendering @COMP:util @TYPE:core
// WHY: 전략 카드 배지 섹션 렌더링 통합 (renderStatusBadge, renderMarketTypeBadge, renderPublicBadge 조합).
//      중복되는 배지 HTML 생성 로직 3곳 통합으로 유지보수성 및 일관성 향상.
/**
 * 전략 카드 배지 섹션 렌더링
 * @param {Object} strategy - 전략 정보 객체
 * @param {boolean} strategy.is_active - 활성 여부
 * @param {string} strategy.market_type - 마켓 타입 (FUTURES, SPOT)
 * @param {boolean} strategy.is_public - 공개 여부
 * @returns {string} 배지 섹션 HTML
 * @example renderStrategyBadges(strategy)
 */
function renderStrategyBadges(strategy) {
    if (!strategy) {
        return '';
    }
    const statusBadge = renderStatusBadge(strategy.is_active);
    const marketBadge = renderMarketTypeBadge(strategy.market_type);
    const publicBadge = renderPublicBadge(strategy.is_public);
    return `
    <div class="strategy-badges">
      ${statusBadge}
      ${marketBadge}
      ${publicBadge}
    </div>`;
}

// @FEAT:strategy-rendering @COMP:util @TYPE:core
// WHY: 전략 메트릭 섹션 렌더링 통합 (renderMetricItem 조합).
//      계좌 수, 포지션 수 메트릭 중복 제거로 일관성 강화.
/**
 * 전략 메트릭 섹션 렌더링 (계좌 수, 포지션 수)
 * @param {Object} strategy - 전략 정보 객체
 * @param {number} [strategy.connected_accounts] - 연결된 계좌 배열
 * @param {number} [strategy.position_count=0] - 포지션 수
 * @returns {string} 메트릭 섹션 HTML
 * @example renderStrategyMetrics(strategy)
 */
function renderStrategyMetrics(strategy) {
    if (!strategy) {
        return '';
    }
    const accountCount = (strategy.connected_accounts || []).length;
    const positionCount = strategy.position_count || 0;
    return `
    <div class="metric-grid">
      ${renderMetricItem(METRIC_ICONS.accounts, accountCount, '내 연결 계좌')}
      ${renderMetricItem(METRIC_ICONS.positions, positionCount, '포지션')}
    </div>`;
}
