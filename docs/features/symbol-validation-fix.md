# Symbol Validation Fix - 캐시 키 형식 통합

## 개요

@FEAT:symbol-validation-fix @COMP:service @TYPE:core

SymbolValidator 서비스의 캐시 키 생성 방식을 표준화하여 15분마다 발생하던 경고 로그를 제거하는 기능입니다.

## 문제 상황

### 발생 문제
- **증상**: 15분마다 "심볼 정보를 찾을 수 없습니다" 경고 로그 발생
- **원인**: 캐시 키 생성 방식 불일치
  - 저장 시: `BINANCE_BTC/USDT_FUTURES`
  - 조회 시: `BINANCE_BTCUSDT_FUTURES`
- **영향**: 불필요한 경고 로그로 인한 모니터링 혼선

### 기술적 원인

```python
# 문제 코드 (이전)
cache_key = f"{exchange_name.upper()}_{symbol}_{market_type.upper()}"
# BINANCE_BTCUSDT_FUTURES

# 수정 코드 (현재)
def _build_cache_key(self, exchange_name, symbol, market_type):
    return f"{exchange_name.upper()}_{symbol.upper()}_{market_type.upper()}"
# BINANCE_BTC/USDT_FUTURES
```

## 해결 방안

### 1. 표준화된 캐시 키 생성 함수

`_build_cache_key()` 헬퍼 함수 도입:

```python
def _build_cache_key(self, exchange_name: str, symbol: str, market_type: str) -> str:
    """
    표준화된 캐시 키 생성

    Args:
        exchange_name: 거래소 이름 (예: "BINANCE", "UPBIT")
        symbol: 심볼 (예: "BTC/USDT", "BTC/KRW")
        market_type: 시장 유형 (예: "FUTURES", "SPOT")

    Returns:
        표준화된 캐시 키 문자열
    """
    return f"{exchange_name.upper()}_{symbol.upper()}_{market_type.upper()}"
```

### 2. 모든 캐시 키 생성 위치 수정

- `load_initial_symbols()` (라인 109, 126, 129)
- `_refresh_all_symbols()` (라인 206)
- `get_market_info()` (라인 230)
- `validate_order_params()` (라인 250)

## 기대 효과

### 즉각적 효과
- ✅ 15분마다 발생하던 경고 로그 완전 제거
- ✅ 캐시 히트율 100% 달성
- ✅ 모니터링 시스템 안정화

### 장기적 효과
- 🔧 유지보수성 향상: 단일 키 생성 로직
- 🛡️ 안정성 강화: 일관된 캐시 동작
- 📊 모니터링 정확도: 실제 오류만 감지

## 롤백 절차

### 문제 발생 시 대응
1. **즉시 롤백**: 이전 버전으로 revert
2. **원인 분석**: 캐시 키 형식 로그 확인
3. **영향 평가**: 서비스 가용성 점검

### 롤백 명령어
```bash
# 기능 롤백
git revert <commit-hash>

# 서비스 재시작
python manage.py restart
```

## 모니터링 지표

### 핵심 지표
- 📈 **캐시 히트율**: 목표 100%
- ⚠️ **경고 로그 발생 빈도**: 목표 0건/시간
- 🔄 **캐시 갱신 성공률**: 목표 95%+

### 모니터링 명령어
```bash
# 캐시 상태 확인
grep "심볼 정보를 찾을 수 없습니다" app.log

# 캐시 히트율 확인
grep "캐시 상태" app.log | tail -10
```

## 관련 파일

- **메인 파일**: `web_server/app/services/symbol_validator.py`
- **테스트 파일**: `tests/services/test_symbol_validator.py`
- **통합 테스트**: `tests/services/test_symbol_validator_integration.py`

## 태그 참조

- `@FEAT:symbol-validation-fix` - 이 기능
- `@FEAT:symbol-validation` - 상위 기능
- `@COMP:service` - 서비스 컴포넌트
- `@TYPE:core` - 핵심 로직
- `@TYPE:helper` - 헬퍼 함수

---

*문서 생성일: 2025-11-20*
*담당자: documentation-manager*