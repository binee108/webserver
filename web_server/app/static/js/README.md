# 실시간 포지션 가격 업데이트 시스템

이 시스템은 포지션 페이지에서 실시간으로 현재가격과 미실현 손익(PnL)을 업데이트하는 WebSocket 기반 시스템입니다.

## 파일 구조

```
app/static/js/
├── websocket-manager.js              # 기본 WebSocket 관리 클래스
├── position-realtime-manager.js      # 포지션 실시간 업데이트 통합 관리자
├── exchanges/
│   ├── binance-websocket.js         # Binance 거래소 WebSocket 클라이언트
│   ├── bybit-websocket.js           # Bybit 거래소 WebSocket 클라이언트
│   └── okx-websocket.js             # OKX 거래소 WebSocket 클라이언트
└── README.md                        # 이 파일

app/static/css/
└── position-realtime.css            # 실시간 업데이트 관련 CSS 스타일
```

## 주요 기능

### 1. 멀티 거래소 지원
- **Binance**: 현물(Spot) 및 선물(Futures) 지원
- **Bybit**: 현물(Spot), 선형 선물(Linear), 역방향 선물(Inverse) 지원  
- **OKX**: 현물(Spot), 선물(Futures), 무기한 계약(Swap) 지원

### 2. 실시간 가격 업데이트
- WebSocket을 통한 실시간 가격 데이터 수신
- 자동 재연결 및 오류 처리
- 가격 변동 시각적 인디케이터

### 3. 미실현 PnL 계산
- 진입가격 대비 실시간 손익 계산
- 백분율 및 절대값 표시
- 수익/손실에 따른 색상 구분

### 4. 연결 상태 모니터링
- 실시간 연결 상태 표시
- 거래소별 연결 상태 확인
- 구독 중인 심볼 수 표시

## 사용법

### 1. 자동 초기화
포지션 페이지(`positions.html`)에 접속하면 자동으로 실시간 업데이트가 시작됩니다.

### 2. 연결 상태 확인
- 페이지 우상단의 "연결 상태" 버튼 클릭
- 거래소별 연결 상태 및 구독 정보 확인

### 3. 실시간 인디케이터
- 포지션 제목 옆의 상태 표시:
  - 🟡 "연결 시도 중": 초기 연결 중
  - 🟢 "실시간 연결됨": 정상 연결됨

## 코드 구조

### WebSocketManager (기본 클래스)
```javascript
class WebSocketManager {
    // 기본 WebSocket 연결 및 재연결 관리
    // 메시지 큐, ping/pong 처리
    // 구독 관리
}
```

### 거래소별 WebSocket 클래스
```javascript
class BinanceWebSocket extends WebSocketManager {
    // Binance 특화 구현
    // 심볼 정규화, 메시지 파싱
    // 가격 데이터 콜백 처리
}
```

### PositionRealtimeManager (통합 관리자)
```javascript
class PositionRealtimeManager {
    // 여러 거래소 WebSocket 인스턴스 관리
    // 포지션 데이터와 가격 데이터 매칭
    // UI 업데이트 처리
}
```

## 설정 및 확장

### 새로운 거래소 추가
1. `exchanges/` 폴더에 새 WebSocket 클래스 생성
2. `WebSocketManager`를 상속받아 구현
3. `PositionRealtimeManager`의 `exchangeConfigs`에 설정 추가

```javascript
// 예시: exchanges/example-websocket.js
class ExampleWebSocket extends WebSocketManager {
    constructor(options = {}) {
        super('wss://example.com/ws', options);
        // 거래소별 초기화
    }
    
    subscribeToPrice(symbol, callback) {
        // 가격 구독 구현
    }
    
    handleMessage(data) {
        // 메시지 처리 구현
    }
}
```

### 시장 타입 추가
`determineMarketType()` 함수에 새로운 패턴 추가:

```javascript
determineMarketType(positionData) {
    const symbol = positionData.symbol.toUpperCase();
    
    if (symbol.includes('NEWTYPE')) {
        return 'newmarket';
    }
    
    // 기존 로직...
}
```

## 성능 최적화

### 1. 연결 관리
- 같은 거래소의 여러 심볼을 하나의 WebSocket 연결로 처리
- 자동 재연결으로 안정성 확보
- 불필요한 구독 방지

### 2. UI 업데이트
- DOM 조작 최소화
- CSS 애니메이션으로 부드러운 전환
- 가격 변동 시에만 업데이트

### 3. 메모리 관리
- 페이지 이탈 시 자동 연결 해제
- 불필요한 데이터 캐시 정리

## 디버깅

### 콘솔 로그 확인
브라우저 개발자 도구에서 다음 로그 확인:
- `Position Realtime Manager initialized`
- `Connected to [exchange] [marketType] WebSocket`
- `Subscribed to [symbol] on [exchange]`
- `Price update for [symbol]: $[price]`

### 연결 문제 해결
1. 네트워크 상태 확인
2. 거래소 API 상태 확인
3. 심볼 형식 검증 (각 거래소별 상이)
4. 브라우저 WebSocket 지원 확인

## 보안 고려사항

### 1. 공개 데이터만 사용
- 가격 데이터는 공개 WebSocket 스트림 사용
- API 키나 개인정보 전송 없음

### 2. 입력 검증
- 심볼명 정규화 및 검증
- XSS 방지를 위한 DOM 업데이트 검증

### 3. 연결 제한
- 동시 연결 수 제한
- 재연결 시도 횟수 제한

## 문제 해결

### 자주 발생하는 문제

1. **연결 실패**
   - 거래소 API 상태 확인
   - 네트워크 방화벽 설정 확인

2. **가격 업데이트 안됨**
   - 심볼 형식 확인 (거래소별 상이)
   - 시장 운영 시간 확인

3. **페이지 성능 저하**
   - 동시 구독 심볼 수 확인
   - 브라우저 메모리 사용량 확인

### 지원 연락처
시스템 관련 문의는 개발팀으로 연락주세요. 