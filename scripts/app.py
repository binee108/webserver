#!/usr/bin/env python3
"""
트레이딩 자동화 시스템 메인 실행 파일
"""
import os
import sys

# 경로 설정을 더 안정적으로 처리
def setup_python_path():
    """Python 경로 설정"""
    # 현재 스크립트의 디렉토리에서 상대 경로 계산
    script_dir = os.path.dirname(os.path.abspath(__file__))
    web_server_path = os.path.join(script_dir, '..', 'web_server')
    config_path = os.path.join(script_dir, '..', 'config')
    
    # 경로가 존재하는지 확인하고 sys.path에 추가
    if os.path.exists(web_server_path):
        sys.path.insert(0, os.path.abspath(web_server_path))
    else:
        print(f"Warning: web_server path not found at {web_server_path}")
    
    if os.path.exists(config_path):
        sys.path.insert(0, os.path.abspath(config_path))
    else:
        print(f"Warning: config path not found at {config_path}")

# 경로 설정 실행
setup_python_path()

try:
    # Flask CLI를 위해 app 모듈을 명시적으로 import
    import app
    from app import create_app
except ImportError as e:
    print(f"Error importing app: {e}")
    print("Current Python path:")
    for path in sys.path:
        print(f"  - {path}")
    sys.exit(1)

def check_health_endpoint():
    """헬스체크 엔드포인트 확인"""
    try:
        from app.routes import health
        return True
    except ImportError:
        print("Warning: Health endpoint not found. Creating basic health check...")
        return False

app = create_app()

if __name__ == '__main__':
    # 개발 환경에서만 debug=True
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    # HTTP 서버로만 실행 (Nginx가 SSL 터미네이션 처리)
    port = int(os.environ.get('PORT', 5001))
    
    print(f"Starting Flask HTTP server on port {port}...")
    print("SSL termination will be handled by Nginx reverse proxy.")
    
    # 헬스체크 엔드포인트 확인
    check_health_endpoint()
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        threaded=True  # 멀티스레드 모드 활성화로 블로킹 문제 해결
    ) 