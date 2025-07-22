#!/usr/bin/env python3
"""
트레이딩 자동화 시스템 메인 실행 파일
"""
import os
import ssl
from app import create_app

def get_ssl_context():
    """SSL 컨텍스트 생성"""
    # SSL 활성화 여부 확인
    if not os.environ.get('ENABLE_SSL', 'true').lower() in ['true', '1', 'yes', 'on']:
        return None
    
    cert_dir = os.environ.get('SSL_CERT_DIR', 'certs')
    cert_file = os.path.join(cert_dir, 'cert.pem')
    key_file = os.path.join(cert_dir, 'key.pem')
    
    # 인증서 파일이 없으면 생성
    if not os.path.exists(cert_file) or not os.path.exists(key_file):
        print("SSL certificates not found. Generating new ones...")
        try:
            import subprocess
            subprocess.run(['python', 'generate_ssl_cert.py'], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error generating SSL certificates: {e}")
            print("Falling back to HTTP mode...")
            return None
        except FileNotFoundError:
            print("generate_ssl_cert.py not found. Please run it manually.")
            print("Falling back to HTTP mode...")
            return None
    
    # SSL 컨텍스트 생성
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
        print(f"SSL enabled with certificate: {cert_file}")
        return context
    except Exception as e:
        print(f"Error loading SSL certificates: {e}")
        print("Falling back to HTTP mode...")
        return None

app = create_app()

if __name__ == '__main__':
    # 개발 환경에서만 debug=True
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    # SSL 컨텍스트 가져오기
    ssl_context = get_ssl_context()
    
    # 포트 결정 (SSL이면 443, 아니면 5001)
    if ssl_context:
        default_port = 443
        protocol = "HTTPS"
    else:
        default_port = 5001
        protocol = "HTTP"
    
    port = int(os.environ.get('PORT', default_port))
    
    print(f"Starting {protocol} server on port {port}...")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        ssl_context=ssl_context
    ) 