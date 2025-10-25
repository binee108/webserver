# 선물 거래소 검증 기능

## 개요

**목표**: Strategies 페이지에서 선물(FUTURES/PERPETUAL) 전략에 선물 미지원 거래소(Upbit, Bithumb) 계좌 연동 시도 시, 프론트엔드에서 사용자 친화적 메시지로 조기 차단하는 기능

**효과**:
- 사용자 경험 개선 (즉시 피드백)
- 백엔드 검증과 함께 이중 방어 (보안 강화)
- API 오류 호출 감소

---

## 아키텍처

### 이중 검증 구조

```
사용자 계좌 연동 시도
    ↓
[프론트엔드] EXCHANGE_METADATA 확인
    ├─ 선물 미지원 거래소 → 차단 (조기 피드백)
    └─ 지원 거래소 → API 호출
    ↓
[백엔드] strategy_service._validate_market_type_support()
    ├─ 선물 미지원 거래소 → StrategyError (우회 방지)
    └─ 지원 거래소 → 계좌 연동 완료
```

### 단일 소스 원칙

- **ExchangeMetadata**: 거래소 메타데이터의 유일한 진실의 근원
- 백엔드와 프론트엔드 모두 동일한 메타데이터 참조
- 메타데이터 변경 시 자동으로 양쪽 검증 동기화

**메타데이터 구조**:
```python
'binance': {
    'supported_markets': [MarketType.SPOT, MarketType.FUTURES],
    ...
}
'upbit': {
    'supported_markets': [MarketType.SPOT],  # FUTURES 미포함
    ...
}
```

---

## Phase 1: 거래소 메타데이터 API

### API 엔드포인트

**URL**: `GET /api/system/exchange-metadata`
**인증**: `@login_required` (로그인 필수)
**캐싱**: 프론트엔드 세션 메모리 (페이지 로드 시 1회)

**응답 형식**:
```json
{
  "success": true,
  "payload": {
    "binance": {
      "supports_futures": true,
      "supports_perpetual": true
    },
    "bybit": {
      "supports_futures": false,
      "supports_perpetual": true
    },
    "upbit": {
      "supports_futures": false,
      "supports_perpetual": false
    },
    "bithumb": {
      "supports_futures": false,
      "supports_perpetual": false
    }
  }
}
```

### 백엔드 구현

**파일**: `app/routes/system.py` (Lines 306-331)

```python
# @FEAT:futures-validation @COMP:route @TYPE:core
@bp.route('/system/exchange-metadata', methods=['GET'])
@login_required
def get_exchange_metadata():
    """거래소 메타데이터 조회 (선물 지원 여부)"""
    try:
        metadata = {}
        for exchange_name in ExchangeMetadata.METADATA.keys():
            metadata[exchange_name] = {
                'supports_futures': ExchangeMetadata.supports_market_type(
                    exchange_name, MarketType.FUTURES
                ),
                'supports_perpetual': ExchangeMetadata.supports_market_type(
                    exchange_name, MarketType.PERPETUAL
                )
            }
        return jsonify({
            'success': True,
            'payload': metadata
        }), 200
    except Exception as e:
        current_app.logger.error(f'거래소 메타데이터 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
```

**핵심 메서드**:
- `ExchangeMetadata.supports_market_type()` - 거래소별 마켓 타입 지원 여부 확인
  - 단일 소스: `metadata.py:173-177`
  - 반환: `bool` (True/False)

**에러 처리**:
- JSON 직렬화 실패 → 500 Internal Server Error
- 데이터베이스 오류 없음 (메모리 기반 메타데이터)

### 프론트엔드 통합

**파일**: `app/templates/strategies.html` (Lines 441-456)

```javascript
// @FEAT:futures-validation @COMP:route @TYPE:integration
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
```

**동작**:
1. 페이지 로드 시 API 자동 호출 (비동기)
2. 메타데이터를 전역 변수 `window.EXCHANGE_METADATA`에 캐싱
3. 로드 실패 시 `null`로 설정 (백엔드 검증으로 fallback)

---

---

## Phase 2: 프론트엔드 검증 로직

### 개요
계좌 연동 시도 시 프론트엔드에서 선물 미지원 거래소를 조기 차단하여 사용자 경험을 개선합니다.

### 구현 내용

#### 전역 변수

**파일**: `app/templates/strategies.html` (Line 458-471)

```javascript
// @FEAT:futures-validation @COMP:route @TYPE:validation
// 전략 데이터를 전역 변수로 설정 (Jinja2 렌더링)
window.strategies = [
    {
        id: 1,
        name: 'test1',
        market_type: 'SPOT',
        is_active: true,
        is_public: false,
        description: ''
    }
    // ... 전략 목록
];
```

**용도**: 각 전략의 `market_type` 확인 (SPOT vs FUTURES)

#### 검증 로직

**파일**: `app/templates/strategies.html` (Line 1247-1297)
**함수**: `connectAccount(strategyId, accountId, event)`

```javascript
// @FEAT:futures-validation @COMP:route @TYPE:validation
function connectAccount(strategyId, accountId, event) {
    // 1. 메타데이터 로드 확인
    if (!window.EXCHANGE_METADATA) {
        // fallback: 백엔드 검증 의존
        showConnectionForm(strategyId, accountId, 'connect');
        return;
    }

    // 2. 전략 정보 조회
    const strategy = window.strategies?.find(s => s.id === parseInt(strategyId));
    if (!strategy) {
        showToast('전략 정보를 찾을 수 없습니다', 'error');
        return;
    }

    // 3. 계좌 거래소 정보 추출 (data-exchange 속성)
    const accountButton = event?.target?.closest('button');
    const accountExchange = accountButton?.dataset?.exchange;

    if (!accountExchange) {
        showConnectionForm(strategyId, accountId, 'connect');
        return;
    }

    // 4. 선물 전략인 경우 거래소 지원 여부 검증
    if (strategy.market_type === 'FUTURES') {
        const exchangeMeta = window.EXCHANGE_METADATA[accountExchange.toLowerCase()];

        if (exchangeMeta && !exchangeMeta.supports_futures && !exchangeMeta.supports_perpetual) {
            // 5. 지원 거래소 목록 생성 및 에러 메시지 표시
            const supportedExchanges = Object.entries(window.EXCHANGE_METADATA)
                .filter(([_, meta]) => meta.supports_futures || meta.supports_perpetual)
                .map(([name, _]) => name.charAt(0).toUpperCase() + name.slice(1))
                .join(', ');

            showToast(
                `이 거래소(${accountExchange})는 선물 거래를 지원하지 않습니다. 지원 거래소: ${supportedExchanges}`,
                'error'
            );
            return;
        }
    }

    // 검증 통과 시 연결 폼 표시
    showConnectionForm(strategyId, accountId, 'connect');
}
```

### 검증 흐름

```
사용자 계좌 연동 클릭
    ↓
connectAccount() 함수 실행
    ├─ 1. EXCHANGE_METADATA 확인 (null 시 fallback)
    ├─ 2. 전략 market_type 조회 (window.strategies)
    ├─ 3. 계좌 거래소 정보 추출 (data-exchange 속성)
    ├─ 4. FUTURES 전략 검증
    │   ├─ 지원 거래소 → Step 5
    │   └─ 미지원 거래소 → 토스트 에러 + 지원 목록 표시 + 종료
    └─ 5. 연결 폼 표시 (showConnectionForm)
```

### 사용자 경험 개선

- ✅ **조기 차단**: 400 에러 발생 전 프론트엔드에서 즉시 차단
- ✅ **명확한 피드백**: 토스트 메시지로 사용자에게 문제 설명
- ✅ **대안 제시**: 지원 거래소 목록 함께 표시
- ✅ **API 절감**: 불필요한 백엔드 호출 감소 (네트워크 비용 최적화)
- ✅ **Fallback 안전성**: 메타데이터 로드 실패 시 백엔드 검증으로 우회

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| **백엔드** | Flask (routes/system.py), ExchangeMetadata (metadata.py) |
| **프론트엔드** | Vanilla JavaScript (async/await), Fetch API |
| **메타데이터** | Python Enum (MarketType: SPOT, FUTURES, PERPETUAL) |
| **캐싱** | 브라우저 메모리 (window 전역 변수) |

---

## 참고

**메타데이터 소스**:
```
app/exchanges/metadata.py
├── ExchangeMetadata.METADATA (중앙 관리)
├── MarketType enum
└── supports_market_type() 메서드
```

**로그 확인**:
- 프론트엔드: 브라우저 콘솔 (`console.log`)
- 백엔드: `/web_server/logs/app.log` (로그 레벨: INFO 이상)

**테스트 방법**:
```bash
# 백엔드 API 테스트
curl -k https://222.98.151.163/api/system/exchange-metadata

# 프론트엔드 확인
# Strategies 페이지 로드 후 F12 > Console
# window.EXCHANGE_METADATA 값 확인
```

---

**상태**: Phase 1-2 Complete (API + Validation)
**작성일**: 2025-10-23
**최종 업데이트**: Phase 2 완료 (2025-10-23)
