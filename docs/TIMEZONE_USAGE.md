# Timezone Utility 사용 가이드

> 📌 **Quick Navigation**: [빠른 시작](#빠른-시작) | [API 사용법](#api-사용법) | [브라우저 호환성](#브라우저-호환성) | [문제 해결](#문제-해결)

범용 시간대 유틸리티는 자동 시간대 감지, 시간대 변환, 다양한 형식의 시간 포맷팅을 제공하는 JavaScript 클래스입니다. IE11부터 최신 브라우저까지 완벽 호환되며, 성능 최적화를 위한 캐시 시스템을 내장하고 있습니다.

## 요구사항

- **브라우저**: IE11+, Chrome, Firefox, Safari, Edge
- **JavaScript**: ES5+ 지원
- **의존성**: 없음 (순수 JavaScript 구현)

---

## 빠른 시작

### 기본 사용법

```javascript
// 스크립트 로드
<script src="/static/js/timezone.js"></script>

// 기본 사용
const utils = window.timeZoneUtils;

// 사용자 시간대 자동 감지
const userTz = utils.detectUserTimeZone();
console.log('사용자 시간대:', userTz);

// 현재 시간 포맷팅
const now = new Date();
const formatted = utils.formatToLocalTime(now.getTime());
console.log('로컬 시간:', formatted);

// 특정 시간대로 변환
const utcTime = utils.convertTimezone(now.getTime(), 'UTC', 'Asia/Seoul');
console.log('한국 시간:', utils.formatToLocalTime(utcTime.getTime(), { timezone: 'Asia/Seoul' }));
```

### 즉시 시작

```javascript
// 싱글톤 인스턴스 사용 (권장)
const utils = window.timeZoneUtils;

// 가장 일반적인 사용 예시
const currentTime = utils.formatToLocalTime(Date.now());
const userTimezone = utils.detectUserTimeZone();
const timezoneInfo = utils.getTimezoneInfo();

console.log(`현재 시간: ${currentTime}`);
console.log(`사용자 시간대: ${userTimezone}`);
console.log(`시간대 정보:`, timezoneInfo);
```

---

## API 사용법

### 클래스 생성자

```javascript
const utils = new TimeZoneUtils();
```

### 핵심 메서드

#### `detectUserTimeZone()`
사용자의 시간대를 자동으로 감지합니다.

```javascript
const timezone = utils.detectUserTimeZone();
// 반환값: 'Asia/Seoul', 'America/New_York', 'UTC+09:00' 등
```

#### `getTimezoneInfo(timezone?)`
시간대에 대한 상세 정보를 반환합니다.

```javascript
const info = utils.getTimezoneInfo('Asia/Seoul');
// 반환값:
{
    identifier: 'Asia/Seoul',
    name: 'Korea Standard Time',
    offset: 540,  // 분 단위
    offsetString: '+09:00',
    currentTime: '2025-11-14 15:30:45 (+09:00)',
    isDST: false,
    rawOffset: 540
}
```

#### `formatToLocalTime(timestamp, options?)`
타임스탬프를 로컬 시간으로 포맷팅합니다.

```javascript
// 기본 사용
const formatted = utils.formatToLocalTime(1672531200000);
// '2025-01-01 00:00:00 (+09:00)'

// 옵션 지정
const formatted = utils.formatToLocalTime(timestamp, {
    timezone: 'America/New_York',
    format: 'YYYY-MM-DD HH:mm',
    locale: 'en-US',
    includeOffset: true,
    use24Hour: true
});
```

#### `convertTimezone(timestamp, sourceTimezone, targetTimezone)`
시간대 간 변환을 수행합니다.

```javascript
const sourceDate = new Date('2025-01-01 00:00:00');
const converted = utils.convertTimezone(
    sourceDate.getTime(),
    'Asia/Seoul',
    'America/New_York'
);

console.log(converted); // 변환된 Date 객체
```

#### `formatBatch(timestamps, options?)`
배치 처리를 위한 시간 포맷팅 (성능 최적화).

```javascript
const timestamps = [1672531200000, 1672617600000, 1672704000000];
const results = utils.formatBatch(timestamps, {
    format: 'MM-DD HH:mm',
    use24Hour: true
});
// ['01-01 00:00', '01-02 00:00', '01-03 00:00']
```

### 유틸리티 메서드

#### `clearCache()`
모든 캐시를 초기화합니다.

```javascript
utils.clearCache();
```

#### `getPerformanceMetrics()`
성능 메트릭스를 조회합니다.

```javascript
const metrics = utils.getPerformanceMetrics();
// {
//     cacheHits: 25,
//     cacheMisses: 5,
//     conversions: 30,
//     cacheHitRate: '83.33%'
// }
```

#### `isValidTimezone(timezone)`
시간대 식별자 유효성 검증.

```javascript
const isValid = utils.isValidTimezone('Asia/Seoul'); // true
const isValid = utils.isValidTimezone('Invalid/Timezone'); // false
```

---

## 시간대 목록

### 지원하는 주요 시간대

#### 북미
- `America/New_York` - 동부 표준시 (EST/EDT)
- `America/Chicago` - 중부 표준시 (CST/CDT)
- `America/Denver` - 산악 표준시 (MST/MDT)
- `America/Los_Angeles` - 태평양 표준시 (PST/PDT)
- `America/Phoenix` - 애리조나 표준시 (MST, no DST)

#### 유럽
- `Europe/London` - 그리니치 표준시 (GMT/BST)
- `Europe/Paris` - 중부 유럽 시간 (CET/CEST)
- `Europe/Berlin` - 중부 유럽 시간 (CET/CEST)
- `Europe/Moscow` - 모스크바 시간 (MSK, no DST)

#### 아시아
- `Asia/Seoul` - 한국 표준시 (KST, no DST)
- `Asia/Tokyo` - 일본 표준시 (JST, no DST)
- `Asia/Shanghai` - 중국 표준시 (CST, no DST)
- `Asia/Hong_Kong` - 홍콩 시간 (HKT, no DST)
- `Asia/Singapore` - 싱가포르 시간 (SGT, no DST)
- `Asia/Dubai` - 두바이 시간 (GST, no DST)
- `Asia/Kolkata` - 인도 표준시 (IST, no DST)

#### 오세아니아
- `Australia/Sydney` - 시드니 시간 (AEST/AEDT)
- `Australia/Melbourne` - 멜버른 시간 (AEST/AEDT)
- `Australia/Perth` - 퍼스 시간 (AWST, no DST)
- `Pacific/Auckland` - 오클랜드 시간 (NZST/NZDT)

#### 기타
- `UTC` - 협정 세계시
- `GMT` - 그리니치 평균시

### UTC 오프셋 사용

```javascript
// 직접 UTC 오프셋 지정
const utcOffsetTime = utils.formatToLocalTime(timestamp, {
    timezone: 'UTC+09:00'
});

const utcMinusTime = utils.formatToLocalTime(timestamp, {
    timezone: 'UTC-05:00'
});
```

---

## 브라우저 호환성

### 지원 브라우저

| 브라우저 | 최소 버전 | 기능 지원 | 성능 최적화 |
|---------|-----------|-----------|-------------|
| Chrome | 24+ | ✅ 완벽 | ✅ 최적화 |
| Firefox | 29+ | ✅ 완벽 | ✅ 최적화 |
| Safari | 10+ | ✅ 완벽 | ✅ 최적화 |
| Edge | 12+ | ✅ 완벽 | ✅ 최적화 |
| IE | 11+ | ⚠️ 제한적 | ⚠️ 기본 기능 |
| Opera | 15+ | ✅ 완벽 | ✅ 최적화 |

### 호환성 주의사항

#### IE11 제한사항
- `Intl` API가 지원되지 않음
- 수동 시간대 감지만 가능
- 기본 포맷팅만 지원

```javascript
// IE11에서의 대체 사용법
if (!window.Intl) {
    console.warn('IE11 환경에서는 시간대 감지 기능이 제한됩니다.');
    const utils = new TimeZoneUtils();
    const timezone = utils.detectUserTimeZone(); // 제한된 감지
}
```

#### 기능 축소 환경
- 최신 `Intl` API가 없는 환경에서는 수동 시간대 매핑만 사용
- 캐시 기능이 비활성화될 수 있음

---

## 성능 최적화

### 캐시 시스템

유틸리티는 두 종류의 캐시를 내장하고 있습니다:

#### 1. 시간대 정보 캐시 (24시간 TTL)
```javascript
// 시간대 정보 캐시
this._offsetCache = new Map();
this._cacheTimestamps = new Map();
this._CACHE_TTL = 24 * 60 * 60 * 1000; // 24시간
```

#### 2. 포맷팅 결과 캐시 (5분 TTL)
```javascript
// 포맷팅 결과 캐시
this._formatCache = new Map();
this._formatCacheTimestamps = new Map();
this._FORMAT_CACHE_TTL = 5 * 60 * 1000; // 5분
```

### 성능 모니터링

```javascript
// 성능 메트릭스 확인
const metrics = utils.getPerformanceMetrics();
console.log(`캐시 적중률: ${metrics.cacheHitRate}`);
console.log(`전체 변환 수: ${metrics.conversions}`);
```

### 배치 처리

```javascript
// 많은 수의 타임스탬프 처리 시 배치 사용
const largeTimestamps = Array.from({length: 1000}, (_, i) => Date.now() + i * 60000);
const results = utils.formatBatch(largeTimestamps, { use24Hour: true });
```

---

## 문제 해결

### 자주 발생하는 문제

#### 1. 시간대 감지 실패

**문제**: `detectUserTimeZone()`이 'UTC'를 반환

**원인**:
- 브라우저가 `Intl.DateTimeFormat`을 지원하지 않음
- 네트워크 제한으로 시간대 감지 실패

**해결**:
```javascript
const timezone = utils.detectUserTimeZone();
if (timezone === 'UTC') {
    console.log('수동 시간대 설정 필요');
    // 사용자에게 시간대 선택 UI 표시
}
```

#### 2. 특정 시간대 지원 안됨

**문제**: `getTimezoneInfo()`에서 오류 발생

**원인**:
- 지원하지 않는 시간대 식별자 사용
- 오타 또는 존재하지 않는 시간대

**해결**:
```javascript
if (!utils.isValidTimezone('Custom/Timezone')) {
    console.log('지원하지 않는 시간대입니다.');
    // 유효한 시간대 목록 제공
}
```

#### 3. 포맷팅 결과 예상과 다름

**문제**: 포맷팅된 시간이 예상과 다르게 나타남

**원인**:
- 시간대 설정 오류
- 타임스탬프 값이 유효하지 않음

**해결**:
```javascript
// 타임스탬프 유효성 검증
if (utils.isValidTimezone(targetTimezone)) {
    const result = utils.formatToLocalTime(timestamp, { timezone: targetTimezone });
    console.log('포맷팅 결과:', result);
}
```

### 디버깅 모드

```javascript
// 개발 환경에서의 디버깅
window.timeZoneUtils.DEBUG = true;

// 캐시 상태 확인
console.log('캐시 상태:', {
    offsetCacheSize: utils._offsetCache.size,
    formatCacheSize: utils._formatCache.size
});
```

### 성능 문제 진단

```javascript
// 성능 메트릭스 분석
const metrics = utils.getPerformanceMetrics();
const hitRate = parseFloat(metrics.cacheHitRate);

if (hitRate < 50) {
    console.warn('캐시 적중률이 낮습니다. 성능 개선이 필요할 수 있습니다.');
    // 캐시 정책 검토 또는 데이터 전달 방식 변경
}
```

---

## 사용 예제

### 웹 애플리케이션 통합

#### 1. 전역 시간대 관리자

```javascript
// 전역 시간대 관리자 클래스
class GlobalTimezoneManager {
    constructor() {
        this.utils = window.timeZoneUtils;
        this.currentTimezone = this.utils.detectUserTimeZone();
        this.initialize();
    }

    initialize() {
        // 사용자 시간대 자동 감지
        this.detectUserTimezone();

        // 초기 이벤트 바인딩
        this.bindEvents();
    }

    detectUserTimezone() {
        this.currentTimezone = this.utils.detectUserTimeZone();
        this.updateUI();
        console.log('감지된 시간대:', this.currentTimezone);
    }

    updateTimezone(newTimezone) {
        if (this.utils.isValidTimezone(newTimezone)) {
            this.currentTimezone = newTimezone;
            this.updateUI();
            this.emitTimezoneChanged();
        }
    }

    updateUI() {
        // 전체 애플리케이션의 시간 표시 업데이트
        document.querySelectorAll('[data-time-format]').forEach(element => {
            const timestamp = parseInt(element.dataset.timestamp);
            const formatted = this.utils.formatToLocalTime(timestamp, {
                timezone: this.currentTimezone
            });
            element.textContent = formatted;
        });
    }

    bindEvents() {
        // 시간대 변경 이벤트 리스너
        document.addEventListener('timezone-changed', (e) => {
            this.updateTimezone(e.detail.timezone);
        });
    }

    emitTimezoneChanged() {
        // 시간대 변경 이벤트 발생
        const event = new CustomEvent('timezone-changed', {
            detail: { timezone: this.currentTimezone }
        });
        document.dispatchEvent(event);
    }
}

// 초기화
const timezoneManager = new GlobalTimezoneManager();
```

#### 2. 실시간 시간 업데이트

```javascript
// 실시간 시간 업데이트 클래스
class RealtimeClock {
    constructor(timezoneManager) {
        this.timezoneManager = timezoneManager;
        this.elements = new Map();
        this.intervalId = null;
    }

    start() {
        // 1초마다 시간 업데이트
        this.intervalId = setInterval(() => {
            this.updateAllClocks();
        }, 1000);
    }

    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    registerElement(elementId, timestamp) {
        this.elements.set(elementId, {
            element: document.getElementById(elementId),
            timestamp: timestamp
        });
    }

    updateAllClocks() {
        const now = Date.now();
        const timezone = this.timezoneManager.currentTimezone;

        this.elements.forEach((data, elementId) => {
            if (data.element) {
                // 현재 시간 또는 고정된 타임스탬프 표시
                const timestamp = data.timestamp ? data.timestamp : now;
                const formatted = this.timezoneManager.utils.formatToLocalTime(timestamp, {
                    timezone: timezone,
                    format: 'HH:mm:ss'
                });
                data.element.textContent = formatted;
            }
        });
    }
}

// 사용 예시
const clock = new RealtimeClock(timezoneManager);
clock.registerElement('server-time', Date.now());
clock.registerElement('user-time');
clock.start();
```

### 서버 시간 동기화

```javascript
// 서버 시간과의 동기화
class ServerTimeSync {
    constructor(timezoneManager) {
        this.utils = timezoneManager.utils;
        this.timezoneManager = timezoneManager;
        this.serverTimeOffset = 0;
        this.syncInterval = null;
    }

    async syncServerTime() {
        try {
            // 서버에서 시간 정보 가져오기
            const response = await fetch('/api/time');
            const data = await response.json();

            // 서버 시간과 로컬 시간의 차이 계산
            const localTime = Date.now();
            this.serverTimeOffset = data.server_time - localTime;

            console.log('서버 시간 동기화 완료:', {
                serverTime: data.server_time,
                localTime: localTime,
                offset: this.serverTimeOffset
            });

            return true;
        } catch (error) {
            console.error('서버 시간 동기화 실패:', error);
            return false;
        }
    }

    getServerTimestamp() {
        return Date.now() + this.serverTimeOffset;
    }

    formatServerTime(timestamp, options = {}) {
        const serverTimestamp = timestamp ? this.getServerTimestamp() : Date.now();
        return this.utils.formatToLocalTime(serverTimestamp, {
            ...options,
            timezone: this.timezoneManager.currentTimezone
        });
    }

    startAutoSync(interval = 300000) { // 5분마다 동기화
        this.syncInterval = setInterval(() => {
            this.syncServerTime();
        }, interval);

        // 즉시 한번 동기화
        this.syncServerTime();
    }

    stopAutoSync() {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
    }
}

// 사용 예시
const serverSync = new ServerTimeSync(timezoneManager);
serverSync.startAutoSync();

// 서버 시간 포맷팅
const serverTimeFormatted = serverSync.formatServerTime();
console.log('서버 시간 (사용자 시간대):', serverTimeFormatted);
```

---

## 고급 기능

### 사용자 정의 포맷팅 패턴

```javascript
// 확장된 포맷팅 패턴 지원
const customFormats = {
    'YYYY-MM-DD': '2025-11-14',
    'MM/DD/YYYY': '11/14/2025',
    'DD-MM-YYYY': '14-11-2025',
    'HH:mm:ss': '15:30:45',
    'h:mm A': '3:30 PM',
    'YYYY년 MM월 DD일': '2025년 11월 14일',
    'YYYY년 MM월 DD일 HH시 mm분 ss초': '2025년 11월 14일 15시 30분 45초'
};

const formatted = utils.formatToLocalTime(timestamp, {
    format: 'YYYY년 MM월 DD일 HH시 mm분 ss초',
    timezone: 'Asia/Seoul'
});
```

### 다국어 지원

```javascript
// 다국어 시간 포맷팅
const locales = {
    'ko': 'ko-KR',
    'en': 'en-US',
    'ja': 'ja-JP',
    'zh': 'zh-CN',
    'de': 'de-DE',
    'fr': 'fr-FR'
};

const formatted = utils.formatToLocalTime(timestamp, {
    locale: locales['ko'],
    timezone: 'Asia/Seoul',
    format: 'YYYY년 MM월 DD일'
});
```

### 계절 감지 및 자동 포맷팅

```javascript
// 계절에 따른 자동 포맷팅
function getSeasonalFormat(month) {
    if (month >= 3 && month <= 5) return '봄 - MM월 DD일';
    if (month >= 6 && month <= 8) return '여름 - MM월 DD일';
    if (month >= 9 && month <= 11) return '가을 - MM월 DD일';
    return '겨울 - MM월 DD일';
}

const now = new Date();
const seasonalFormat = getSeasonalFormat(now.getMonth() + 1);
const formatted = utils.formatToLocalTime(Date.now(), {
    format: seasonalFormat,
    timezone: 'Asia/Seoul'
});
```

---

## API 레퍼런스

### TimeZoneUtils 클래스

#### 생성자
```javascript
new TimeZoneUtils()
```

#### 공개 메서드

| 메서드 | 반환 타입 | 설명 |
|--------|-----------|------|
| `detectUserTimeZone()` | `string` | 사용자 시간대 감지 |
| `getTimezoneInfo(timezone?)` | `Object` | 시간대 정보 조회 |
| `formatToLocalTime(timestamp, options?)` | `string` | 로컬 시간 포맷팅 |
| `convertTimezone(timestamp, source, target)` | `Date` | 시간대 변환 |
| `formatBatch(timestamps, options?)` | `Array` | 배치 포맷팅 |
| `clearCache()` | `void` | 캐시 초기화 |
| `getPerformanceMetrics()` | `Object` | 성능 메트릭스 |
| `isValidTimezone(timezone)` | `boolean` | 시간대 유효성 검증 |

#### 옵션 객체

| 속성 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `timezone` | `string` | 사용자 시간대 | 대상 시간대 |
| `format` | `string` | `'YYYY-MM-DD HH:mm:ss'` | 포맷팅 패턴 |
| `locale` | `string` | `'en-US'` | 로케일 |
| `includeOffset` | `boolean` | `true` | 오프셋 포함 여부 |
| `use24Hour` | `boolean` | `true` | 24시간제 사용 여부 |

#### 반환 값 형식

**시간대 정보 객체**:
```typescript
interface TimezoneInfo {
    identifier: string;       // 시간대 식별자
    name: string;             // 표시 이름
    offset: number;           // 오프셋 (분)
    offsetString: string;     // 오프셋 문자열
    currentTime: string;      // 현재 시간
    isDST: boolean;          // 여름시간 적용 여부
    rawOffset?: number;      // 원본 오프셋
    error?: string;          // 오류 메시지
}
```

**성능 메트릭스 객체**:
```typescript
interface PerformanceMetrics {
    cacheHits: number;        // 캐시 적중 횟수
    cacheMisses: number;     // 캐시 미스 횟수
    conversions: number;      // 총 변환 횟수
    cacheHitRate: string;    // 캐시 적중률 (%)
}
```

---

## 최적화 가이드

### 성능 모범 사례

#### 1. 캐시 활용
```javascript
// 반복적인 변환 시 캐시 활용
const cacheKey = `format_${timestamp}_${timezone}`;
if (utils._formatCache.has(cacheKey)) {
    return utils._formatCache.get(cacheKey);
}
```

#### 2. 배치 처리
```javascript
// 여러 타임스탬프는 배치로 처리
const timestamps = data.map(item => item.timestamp);
const results = utils.formatBatch(timestamps, options);
```

#### 3. 불필요한 갱신 줄이기
```javascript
// 시간대 변경 시 필요한 요소만 갱신
function updateRelevantElements(timezone) {
    const relevantElements = document.querySelectorAll('[data-reload-on-timezone]');
    relevantElements.forEach(element => {
        updateElementTime(element, timezone);
    });
}
```

### 메모리 관리

#### 1. 캐시 크기 제한
```javascript
// 캐시 크기 제한 로직
const MAX_CACHE_SIZE = 1000;
if (utils._formatCache.size > MAX_CACHE_SIZE) {
    utils.clearCache();
}
```

#### 2. 불필요한 객체 생성 회피
```javascript
// 싱글톤 인스턴스 재사용
const utils = window.timeZoneUtils; // 매번 새로 생성하지 않음
```

### 이벤트 처리 최적화

#### 1. 디바운싱
```javascript
// 시간대 변경 이벤트 디바운싱
let debounceTimeout;
function handleTimezoneChange(timezone) {
    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(() => {
        updateTimezoneUI(timezone);
    }, 100);
}
```

#### 2. 이벤트 위임
```javascript
// 이벤트 위임을 통한 성능 향상
document.addEventListener('click', (e) => {
    const timezoneButton = e.target.closest('[data-timezone]');
    if (timezoneButton) {
        const timezone = timezoneButton.dataset.timezone;
        updateTimezone(timezone);
    }
});
```

---

## 릴리스 노트

### v1.0.0 (2025-11-14)

**새로운 기능**:
- ✅ 완전한 시간대 유틸리티 구현
- ✅ 자동 시간대 감지
- ✅ 다양한 시간대 변환
- ✅ 유연한 시간 포맷팅
- ✅ 브라우저 호환성 최적화 (IE11+)
- ✅ 성능 캐시 시스템
- ✅ 성능 모니터링
- ✅ 다국어 지원

**수정 사항**:
- 🐛 시간대 감지 정확도 향상
- 🐛 DST 처리 개선
- 🐛 캐시 관리 최적화

**주요 개선사항**:
- ⚡ Intl API 대체 방법 강화
- ⚡ 배치 처리 성능 개선
- ⚡ 오류 처리 개선
- ⚡ JSDoc 문서화 완성

---

## 지원 및 피드백

### 문의 방법
- GitHub Issues를 통한 버그 리포트
- 기능 요청 및 개선 제안
- 문서 오류 수정

### 기여 가이드
1. Fork 및 브랜치 생성
2. 기능 구현 또는 버그 수정
3. 테스트 작성
4. Pull Request 제출

---

*최종 업데이트: 2025-11-14*
*버전: v1.0.0*
*유지보수: Claude Code*