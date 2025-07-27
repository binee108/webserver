# ERR_TOO_MANY_REDIRECTS 문제 해결 문서

## 문제 상황
외부 IP 주소(`https://220.127.44.59`)로 Flask 애플리케이션에 접근할 때 ERR_TOO_MANY_REDIRECTS 오류가 발생했습니다.
- `https://localhost` 접근: 정상 동작 ✅
- `https://220.127.44.59` 접근: 301 리다이렉트 루프 발생 ❌

## 근본 원인
**Flask/Werkzeug의 호스트명 검증 메커니즘**이 IP 주소 형태의 호스트명을 받았을 때, 이를 "부적절한" 호스트명으로 판단하고 URL 정규화를 시도하면서 리다이렉트 루프가 발생했습니다.

### 상세 분석
1. 브라우저에서 `https://220.127.44.59/dashboard` 요청
2. Nginx가 `Host: 220.127.44.59` 헤더와 함께 Flask로 전달
3. Flask/Werkzeug가 IP 주소 호스트명을 감지하고 URL 정규화 시도
4. `Location: https://220.127.44.59/dashboard`로 301 리다이렉트 응답
5. 브라우저가 동일한 URL로 재요청 → 무한 반복

## 해결책
**Nginx 프록시 설정에서 Host 헤더를 `localhost`로 재작성**하여 Flask가 IP 주소 대신 도메인명을 받도록 수정했습니다.

### 핵심 수정 사항
`/config/nginx-ssl.conf`:
```nginx
location / {
    proxy_pass http://flask_app;
    # IP 주소 호스트명으로 인한 리다이렉트 루프 방지
    proxy_set_header Host localhost;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;  # 원본 호스트 보존
    
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}
```

## 작동 원리
1. 클라이언트가 `https://220.127.44.59` 요청
2. Nginx가 `Host: localhost`로 변경하여 Flask에 전달
3. Flask는 `localhost` 호스트명을 정상으로 인식하고 처리
4. 원본 호스트는 `X-Forwarded-Host` 헤더에 보존되어 필요시 사용 가능

## 불필요했던 수정 사항들
다음 수정들은 문제 해결과 무관했으므로 제거되었습니다:
- ❌ Flask 설정의 `PREFERRED_URL_SCHEME` 변경
- ❌ `url_map.redirect_defaults = False` 설정
- ❌ ProxyFix 미들웨어 비활성화
- ❌ 커스텀 URL 생성 함수 추가
- ❌ 호스트 검증 우회 미들웨어
- ❌ 디버깅용 로깅 코드
- ❌ 테스트 라우트 추가

## 최종 구조

### 요청 흐름
```
브라우저 (https://220.127.44.59)
    ↓
Nginx (Host 헤더 재작성: localhost)
    ↓
Flask (정상적인 localhost 요청으로 처리)
    ↓
정상 응답 (302 로그인 리다이렉트 또는 200 페이지 로드)
```

### 수정된 파일
1. **필수 수정**: `/config/nginx-ssl.conf` - Host 헤더 재작성
2. **코드 정리**: `/web_server/app/__init__.py` - 불필요한 코드 제거

## 검증 결과
- ✅ `https://220.127.44.59/dashboard` → 302 Found (정상 로그인 리다이렉트)
- ✅ `https://220.127.44.59/auth/login` → 200 OK (페이지 정상 로드)
- ✅ `https://localhost/dashboard` → 302 Found (기존 기능 유지)

## 결론
복잡한 Flask 코드 수정 없이 **Nginx 프록시 설정 한 줄 수정**으로 문제가 해결되었습니다. 
핵심은 Flask가 IP 주소 호스트명을 받지 않도록 프록시 레벨에서 차단하는 것이었습니다.