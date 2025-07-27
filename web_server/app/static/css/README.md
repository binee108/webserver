# Trading System CSS Architecture

## 구조 개요

이 디렉토리는 트레이딩 자동화 시스템의 모든 CSS 스타일을 포함합니다. 다음과 같은 모듈식 구조로 구성되어 있습니다:

## 파일 구조

### 1. `main.css` - 메인 통합 파일
- 모든 CSS 모듈을 import하는 엔트리 포인트
- 전역 리셋 및 기본 스타일
- 레이아웃 및 유틸리티 클래스
- 반응형 브레이크포인트
- 접근성 스타일

### 2. `themes.css` - 테마 관리
- CSS 변수를 사용한 라이트/다크 테마 시스템
- 색상 팔레트 정의
- 그라디언트 및 그림자 스타일
- 테마 토글 컴포넌트

### 3. `components.css` - 컴포넌트 스타일
- 재사용 가능한 UI 컴포넌트
- 카드, 버튼, 모달, 탭 등
- 애니메이션 및 트랜지션
- 로딩 상태 및 토스트 알림

### 4. `position-realtime.css` - 기존 특수 스타일
- 실시간 포지션 화면 관련 스타일

## 사용법

### 템플릿에서 CSS 사용하기

```html
<!-- base.html에서 -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}">
```

### 테마 시스템 사용하기

CSS 변수를 사용하여 라이트/다크 테마를 자동으로 지원합니다:

```css
.my-component {
    background-color: var(--bg-card);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
}
```

### 주요 CSS 변수

#### 색상
- `--bg-primary`: 기본 배경색
- `--bg-secondary`: 보조 배경색
- `--bg-card`: 카드 배경색
- `--text-primary`: 기본 텍스트 색상
- `--text-secondary`: 보조 텍스트 색상
- `--text-muted`: 흐린 텍스트 색상
- `--accent-primary`: 메인 액센트 색상

#### 상태별 색상
- `--success`: 성공/수익 색상 (#10b981)
- `--error`: 오류/손실 색상 (#ef4444)
- `--warning`: 경고 색상 (#f59e0b)
- `--info`: 정보 색상 (#3b82f6)

### 주요 컴포넌트 클래스

#### 카드
```html
<div class="card rounded-xl p-6">
    <!-- 카드 내용 -->
</div>
```

#### 버튼
```html
<button class="btn btn-primary">Primary Button</button>
<button class="btn btn-secondary">Secondary Button</button>
```

#### 통계 카드
```html
<div class="stats-card">
    <div class="stats-content">
        <div class="stats-info">
            <h3>레이블</h3>
            <p class="stats-value">$1,234.56</p>
            <p class="stats-subtitle">설명</p>
        </div>
        <div class="stats-icon bg-blue-100">
            <!-- 아이콘 SVG -->
        </div>
    </div>
</div>
```

#### 토글 스위치
```html
<div class="toggle-switch active">
    <div class="toggle-circle"></div>
</div>
```

#### 모달
```html
<div class="modal-overlay">
    <div class="modal-content">
        <div class="modal-header">
            <h2>제목</h2>
            <button class="modal-close">×</button>
        </div>
        <div class="modal-body">
            <!-- 모달 내용 -->
        </div>
    </div>
</div>
```

## 테마 전환

JavaScript에서 테마를 전환하려면:

```javascript
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}
```

## 그리드 시스템

### 전략 그리드
```html
<div class="strategy-grid">
    <!-- 전략 카드들 -->
</div>
```

### 통계 그리드
```html
<div class="stats-grid">
    <!-- 통계 카드들 -->
</div>
```

## 애니메이션

### 페이드 인
```html
<div class="fade-in">
    <!-- 애니메이션 요소 -->
</div>
```

### 슬라이드 다운
```html
<div class="slide-down">
    <!-- 애니메이션 요소 -->
</div>
```

### 로딩 스피너
```html
<div class="loading-spinner"></div>
```

## 유틸리티 클래스

### 텍스트 색상
- `.text-primary`: 기본 텍스트
- `.text-secondary`: 보조 텍스트
- `.text-muted`: 흐린 텍스트
- `.text-success`: 성공 색상
- `.text-error`: 오류 색상
- `.text-warning`: 경고 색상
- `.text-info`: 정보 색상

### 간격
- `.space-y-4`: 세로 간격
- `.space-x-4`: 가로 간격
- `.p-4`, `.px-4`, `.py-4`: 패딩
- `.m-4`, `.mb-4`, `.mt-4`: 마진

### 디스플레이
- `.hidden`: 숨김
- `.flex`: 플렉스
- `.grid`: 그리드
- `.block`: 블록

## 반응형 지원

모바일 우선 반응형 디자인을 지원합니다:

- `@media (max-width: 640px)`: 모바일
- `@media (max-width: 768px)`: 태블릿

## 브라우저 지원

- Chrome (최신)
- Firefox (최신)
- Safari (최신)
- Edge (최신)

## 접근성

- 키보드 네비게이션 지원
- 고대비 모드 지원
- 모션 감소 옵션 지원
- 포커스 표시자

## 커스터마이징

새로운 컴포넌트를 추가하려면:

1. `components.css`에 스타일 추가
2. CSS 변수 사용으로 테마 호환성 확보
3. 반응형 브레이크포인트 고려
4. 접근성 가이드라인 준수 