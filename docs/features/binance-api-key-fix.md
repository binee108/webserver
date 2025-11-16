# Binance API Key Format Fix

**Feature Tag**: `@FEAT:binance-api-key-fix`
**Component**: `@COMP:service`
**Type**: `@TYPE:core`
**Issue**: #63
**Status**: ✅ Phase 1 Complete

## 개요

Issue #63 Binance API 키 형식 오류 [-2014]를 해결하는 긴급 수정 패치입니다. 기존의 빈 API 키를 가진 기본 클라이언트 재사용 문제를 해결하고, 계정별 동적 클라이언트 생성을 통해 실제 인증된 API 호출을 복원합니다.

## 문제 상황

### 에러 증상
```
Binance API Error [-2014]: API-key format invalid
```

### 원인 분석
1. ExchangeService가 빈 API 키("")를 가진 기본 클라이언트 재사용
2. Account 모델의 암호화된 API 키를 활용하지 않음
3. 인증 없는 클라이언트로 API 호출 시도

## 해결 방안

### 핵심 변경사항
- `ExchangeService._get_client()` 메소드 완전 재구현
- Account.api_key property 활용한 동적 클라이언트 생성
- crypto_factory를 통한 실제 인증 클라이언트 생성

### 변경 전
```python
# 기존: 미리 생성된 빈 클라이언트 재사용
client = self._crypto_exchanges[account.exchange]  # API 키가 없음!
```

### 변경 후
```python
# 신규: 계정별 동적 클라이언트 생성
client = crypto_factory.create(
    exchange_name=account.exchange.lower(),
    api_key=account.api_key,      # ✅ 복호화된 실제 API 키
    secret=account.api_secret,    # ✅ 복호화된 실제 시크릿
    testnet=account.is_testnet
)
```

## 기술 구현

### 메소드 흐름
1. **Account 객체 수신**: 암호화된 API 키 정보 포함
2. **거래소 타입 확인**: 크립토 vs 증권 분기
3. **동적 클라이언트 생성**: crypto_factory.create() 호출
4. **인증 정보 전달**: Account property에서 복호화된 키 사용
5. **Fallback 처리**: 실패 시 기존 방식으로 안정성 확보

### 주요 코드 변경
- **파일**: `web_server/app/services/exchange.py`
- **메소드**: `_get_client()` (lines 354-398)
- **태그 추가**: `@FEAT:exchange-integration @COMP:service @TYPE:core`

## 영향 범위

### 직접 영향
- 모든 Binance API 호출
- Account 인증이 필요한 거래소 기능
- 주문, 잔고 조회, 거래 내역 등

### 간접 영향
- ExchangeService를 사용하는 모든 서비스
- 거래소 연동 기능 (webhook, manual trading 등)

## 성능 고려사항

### 비용 분석
- **클라이언트 생성**: 비용 높음 (초기화 필요)
- **API 키 복호화**: 비용 낮음 (Account property)
- **Factory 패턴**: 중복 생성 최소화

### 개선 제안
- 클라이언트 캐싱 레이어 추가
- Account별 클라이언트 풀 관리
- LRU 캐시로 메모리 효율화

## 테스트 결과

### 성공 시나리오
- ✅ 계정별 API 키로 정상 인증
- ✅ 모든 Binance API 기능 복원
- ✅ 주문/조회 거래 정상 동작

### 안정성 확인
- ✅ 예외 처리로 서비스 안정성 확보
- ✅ Fallback 메커니즘 동작 확인
- ✅ 로그를 통한 문제 추적 가능

## 관련 기능

- **@FEAT:exchange-integration**: 전체 거래소 연동 기능
- **@FEAT:account-management**: Account 모델 및 인증
- **@FEAT:crypto-factory**: 거래소 클라이언트 생성 팩토리

## 유지보수 가이드

### 모니터링 포인트
- 클라이언트 생성 빈도 및 성능
- API 키 복호화 관련 에러
- Binance API 호출 성공률

### 잠재적 위험
- 클라이언트 생성 과부하로 인한 성능 저하
- Account API 키 만료로 인한 인증 실패
- Factory 패턴 의존성으로 인한 단일 장애점

### 향후 개선 방향
1. 클라이언트 풀링 구현으로 성능 최적화
2. API 키 캐싱으로 복호화 비용 절감
3. 회로 차단기 패턴으로 장애 격리

## 변경 이력

| 날짜 | 변경 내용 | 담당자 |
|------|-----------|--------|
| 2025-11-16 | Issue #63 해결을 위한 _get_client() 재구현 | backend-developer |
| 2025-11-16 | 성능 고려사항 및 fallback 메커니즘 추가 | documentation-manager |

---

*이 문서는 Issue #63 해결을 위한 긴급 패치의 기술적 내용을 기록합니다.*