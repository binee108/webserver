# Exchange Warmup Methods (거래소 웜업 메서드)

## 1. 개요 (Purpose)

거래소 연동을 위한 사전 준비 데이터를 수집하고 관리하는 통합 웜업 시스템. 정밀도 캐시, 마켓 정보, 지원 거래소 목록 등 핵심 데이터를 초기화하여 시스템 안정성과 성능을 확보합니다.

**존재 이유**: 거래소 API 호출 최소화, 데이터 일관성 보장, 관리자 패널 접근성 개선.

---

## 2. 실행 플로우 (Execution Flow)

```
웜업 요청 (백그라운드/관리자)
    ↓
계좌 상태 확인 (활성/비활성)
    ↓
거래소별 그룹화 (중복 호출 방지)
    ↓
Rate Limit 체크
    ↓
API 호출 및 데이터 수집
    ↓
캐시 업데이트 및 결과 반환
```

**핵심 단계**:
1. **계좌 그룹화**: 중복 API 호출 방지를 위한 거래소별 계좌 그룹화
2. **Rate Limit**: API 호출 제한 준수
3. **데이터 수집**: 마켓 정보, 정밀도, 지원 거래소 목록 등
4. **캐시 업데이트**: 수집된 데이터를 Redis 캐시에 저장
5. **결과 집계**: 성공/실패 여부와 상세 정보 반환

---

## 3. 데이터 플로우 (Data Flow)

**Input**: 웜업 요청 (API/백그라운드 스케줄러)
**Process**:
- 활성 계좌 조회 및 거래소별 그룹화
- Rate Limit 적용 및 API 클라이언트 획득
- 거래소별 데이터 수집 (마켓 정보, 정밀도 등)
- 캐시 업데이트 및 상태 관리
- 오류 처리 및 재시도 로직

**Output**: Dict[str, Any] 형태의 실행 결과
```python
{
    'success': bool,                    # 전체 성공 여부
    'refreshed_exchanges': List[str],   # 갱신된 거래소 목록
    'total_markets': int,               # 전체 마켓 수
    'execution_time': float,            # 실행 시간 (초)
    'exchange_details': Dict[str, Dict]  # 거래소별 상세 정보
}
```

---

## 4. 핵심 메서드 상세

### 4.1 `refresh_api_based_market_info()` - **CRITICAL**

**목적**: 모든 활성 계좌의 마켓 정보를 API를 통해 갱신 (관리자 패널 접근성 수정)

**중요성**:
- **관리자 패널 접근성 복구**: 마켓 정보 누락으로 인한 관리자 패널 접근 실패 문제 해결
- **실시간 데이터 동기화**: 여러 거래소의 최신 마켓 정보 유지
- **백그라운드 지원**: 정기적인 데이터 갱신 스케줄링 가능

**실행 로직**:
```python
# 1. 활성 계좌 조회
active_accounts = Account.query.filter_by(is_active=True).all()

# 2. 거래소별 그룹화 (중복 호출 방지)
exchange_groups = {}
for account in active_accounts:
    exchange_name = account.exchange.lower()
    if exchange_name not in exchange_groups:
        exchange_groups[exchange_name] = account

# 3. 거래소별 마켓 정보 갱신
for exchange_name, account in exchange_groups.items():
    # Rate limit 적용
    self.rate_limiter.acquire_slot(account.exchange)

    # API 호출 및 데이터 처리
    client = self._get_client(account)
    market_info = client.get_exchange_info()
```

**성능 메트릭**:
- 평균 실행 시간: 5-15초 (거래소 수 및 네트워크 상태에 따라)
- 메모리 사용: 1MB-5MB (마켓 수에 따라)
- Rate Limit: 거래소별 1회 호출
- 네트워크: 1MB-10MB 데이터 전송

### 4.2 `warm_up_market_precision_cache()`

**목적**: 특정 계좌의 거래소에 대한 가격 정밀도 캐시를 웜업

**사용처**: 계좌 생성 시, 정밀도 캐시 초기화 필요 시

### 4.3 `warm_up_all_market_info()`

**목적**: 단일 계좌의 마켓 정보를 웜업 (단일 계좌 기반)

**사용처**: 계좌별 마켓 정보 초기화

### 4.4 `warm_up_supported_exchanges_cache()`

**목적**: 지원되는 거래소 목록 캐시를 웜업

**사용처**: 시스템 시작 시, 거래소 목록 업데이트 필요 시

### 4.5 `warm_up_all_market_precision_cache()`

**목적**: 모든 활성 계좌의 정밀도 캐시를 웜업

**사용처**: 전체 정밀도 캐시 재구축 필요 시

---

## 5. 관리자 패널 연동

### 5.1 API 엔드포인트

```python
# POST /admin/api/refresh-market-info
@admin_verification_required
def admin_refresh_market_info():
    """마켓 정보 갱신 API (관리자 전용)"""
    result = exchange_service.refresh_api_based_market_info()
    return jsonify(result)
```

### 5.2 프론트엔드 연동

**JavaScript 호출 예시**:
```javascript
// 관리자 패널에서 마켓 정보 갱신
async function refreshMarketInfo() {
    try {
        const response = await fetch('/admin/api/refresh-market-info', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });

        const result = await response.json();
        if (result.success) {
            showSuccess(`마켓 정보 갱신 완료: ${result.total_markets}개 마켓`);
            updateMarketInfoDisplay(result.exchange_details);
        } else {
            showError('마켓 정보 갱신 실패');
        }
    } catch (error) {
        showError('갱신 중 오류 발생: ' + error.message);
    }
}
```

### 5.3 관리자 UI 버튼

**HTML 템플릿**:
```html
<button id="refresh-market-btn"
        class="btn btn-primary"
        onclick="refreshMarketInfo()">
    <i class="fas fa-sync-alt"></i> 마켓 정보 갱신
</button>

<div id="market-status" class="mt-3">
    <!-- 마켓 정보 상태 표시 -->
</div>
```

---

## 6. 성능 최적화 및 캐시 전략

### 6.1 Rate Limit 관리

**전략**: 거래소별 API 호출 제한 준수
```python
# 거래소별 Rate Limit 적용
self.rate_limiter.acquire_slot(account.exchange)
```

### 6.2 캐시 키 관리

**Redis 캐시 키 형식**:
```
market:info:{exchange_name}           # 마켓 정보
precision:cache:{exchange_name}       # 정밀도 캐시
supported:exchanges                   # 지원 거래소 목록
```

### 6.3 데이터 수집 최적화

**중복 호출 방지**:
- 동일 거래소의 여러 계좌를 그룹화하여 단일 API 호출
- 성공한 데이터는 캐시에 저장하여 재사용
- 실패 시에도 다른 거래소는 계속 처리

---

## 7. 트러블슈팅 (Troubleshooting)

### 7.1 일반적인 문제

**문제 1: 관리자 패널 접근 실패**
- **원인**: 마켓 정보 캐시 누락 또는 손상
- **해결**: `refresh_api_based_market_info()` 실행으로 캐시 재구축

**문제 2: 일부 거래소 갱신 실패**
- **원인**: 네트워크 지연, 거래소 점검, 인증 만료
- **해결**: 개별 계좌 상태 확인, 재인증, 나중에 재시도

**문제 3: 실행 시간 과다**
- **원인**: 활성 계좌 수 증가, 네트워크 지연
- **해결**: 백그라운드 스케줄링, 비동기 처리 고려

### 7.2 로그 분석

**성공 로그**:
```
INFO: 마켓 정보 갱신 시작: 3개 거래소
INFO: 바이낸스 갱신 성공: 1521개 마켓
INFO: 마켓 정보 갱신 완료: 15.67초, 총 4521개 마켓
```

**실패 로그**:
```
ERROR: 바이낸스 API 호출 실패: Invalid API key
WARNING: 일부 거래소 갱신 실패, 성공: 2/3
```

### 7.3 모니터링 지표

**핵심 메트릭**:
- API 호출 성공률 (목표: 95% 이상)
- 평균 실행 시간 (목표: 15초 이내)
- 캐시 적중률 (목표: 80% 이상)
- 활성 계좌 수 및 거래소별 분포

---

## 8. 사용 예시

### 8.1 백그라운드 스케줄링

```python
# APScheduler를 사용한 정기 실행
@app.scheduler.task('interval', id='market_info_warmup', hours=6)
def scheduled_market_info_refresh():
    """6시간마다 마켓 정보 갱신"""
    result = exchange_service.refresh_api_based_market_info()
    if not result['success']:
        logger.error("정기 마켓 정보 갱신 실패")
```

### 8.2 수동 실행

```python
# 관리자가 수동으로 실행
exchange_service = ExchangeService()
result = exchange_service.refresh_api_based_market_info()

if result['success']:
    print(f"✅ 성공: {len(result['refreshed_exchanges'])}개 거래소")
    print(f"📊 마켓 수: {result['total_markets']}")
    print(f"⏱️ 실행 시간: {result['execution_time']:.2f}초")
else:
    print("❌ 일부 거래소 갱신 실패")
    for exchange, details in result['exchange_details'].items():
        if not details['success']:
            print(f"   - {exchange}: {details.get('error', 'Unknown error')}")
```

---

## 9. 의존성 관계

**핵심 의존성**:
- `@FEAT:admin-panel` - 관리자 패널 UI 및 API 엔드포인트
- `@FEAT:rate-limiter` - API 호출 제한 관리
- `@FEAT:exchange-integration` - 거래소 클라이언트 연동
- `@COMP:service` - ExchangeService 핵심 서비스

**데이터 의존성**:
- `Account` 모델 - 활성 계좌 조회
- Redis 캐시 - 마켓 정보 및 정밀도 저장
- 거래소 API - 실시간 데이터 수집

---

## 10. 보안 고려사항

### 10.1 인증 및 권한

- **관리자 전용**: 모든 웜업 관련 API는 관리자 권한 필요
- **비밀번호 재확인**: 민감한 데이터 갱신 작업은 추가 인증 필요
- **세션 관리**: 관리자 세션 타임아웃 및 재인증 정책 준수

### 10.2 데이터 보호

- **API 키 보호**: 거래소 API 키는 암호화된 상태로 관리
- **캐시 무효화**: 민감한 데이터는 적절한 TTL로 자동 만료
- **오류 정보 제한**: 상세 오류 정보는 관리자에게만 노출

---

## 11. 향후 개선 방향

### 11.1 성능 개선

- **비동기 처리**: 대규모 거래소 지원 시 async/await 도입
- **분산 캐싱**: 여러 인스턴스 간 캐시 동기화
- **智能 스케줄링**: 거래소별 최적 갱신 시간 계산

### 11.2 모니터링 강화

- **실시간 대시보드**: 웜업 상태 및 성능 지표 시각화
- **알림 시스템**: 실패 시 자동 텔레그램 알림
- **히스토리 추적**: 갱신 이력 및 성능 트렌드 분석

---

## 12. 변경 이력

### v1.2.0 (2024-01-XX)
- **CRITICAL**: `refresh_api_based_market_info()` 메서드 추가
- **기능**: 관리자 패널 접근성 문제 해결
- **개선**: 여러 계좌 기반 마켓 정보 갱신 지원

### v1.1.0 (2023-12-XX)
- 정밀도 캐시 웜업 메서드 추가
- 지원 거래소 목록 캐싱 기능 개선
- Rate Limit 적용 로직 강화

### v1.0.0 (2023-11-XX)
- 초기 웜업 시스템 구현
- 기본 마켓 정보 웜업 기능
- Redis 캐시 연동