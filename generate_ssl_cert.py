#!/usr/bin/env python3
"""
자체 서명 SSL 인증서 생성 스크립트
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta

def check_openssl():
    """OpenSSL 설치 여부 확인"""
    try:
        subprocess.run(['openssl', 'version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def generate_ssl_certificate(cert_dir='certs', domain='localhost'):
    """자체 서명 SSL 인증서 생성"""
    
    # 인증서 디렉토리 생성
    if not os.path.exists(cert_dir):
        os.makedirs(cert_dir)
        print(f"Created directory: {cert_dir}")
    
    cert_file = os.path.join(cert_dir, 'cert.pem')
    key_file = os.path.join(cert_dir, 'key.pem')
    
    # 기존 인증서가 있고 유효하면 건너뛰기
    if os.path.exists(cert_file) and os.path.exists(key_file):
        try:
            # 인증서 만료일 확인
            result = subprocess.run([
                'openssl', 'x509', '-in', cert_file, '-noout', '-enddate'
            ], capture_output=True, text=True, check=True)
            
            # 만료일 파싱 (예: notAfter=Jan  1 00:00:00 2025 GMT)
            enddate_str = result.stdout.strip().split('=')[1]
            try:
                enddate = datetime.strptime(enddate_str, '%b %d %H:%M:%S %Y %Z')
                if enddate > datetime.now() + timedelta(days=30):  # 30일 이상 남았으면 유효
                    print(f"Valid SSL certificate already exists: {cert_file}")
                    return cert_file, key_file
            except ValueError:
                pass  # 날짜 파싱 실패시 새로 생성
        except subprocess.CalledProcessError:
            pass  # 인증서 확인 실패시 새로 생성
    
    print("Generating new SSL certificate...")
    
    # OpenSSL을 사용하여 자체 서명 인증서 생성
    try:
        # 개인키 생성
        subprocess.run([
            'openssl', 'genrsa', '-out', key_file, '2048'
        ], check=True, capture_output=True)
        
        # 인증서 생성 (365일 유효)
        subprocess.run([
            'openssl', 'req', '-new', '-x509', '-key', key_file,
            '-out', cert_file, '-days', '365',
            '-subj', f'/C=KR/ST=Seoul/L=Seoul/O=Trading System/CN={domain}'
        ], check=True, capture_output=True)
        
        print(f"SSL certificate generated successfully:")
        print(f"  Certificate: {cert_file}")
        print(f"  Private key: {key_file}")
        print(f"  Valid for: 365 days")
        print(f"  Domain: {domain}")
        
        return cert_file, key_file
        
    except subprocess.CalledProcessError as e:
        print(f"Error generating SSL certificate: {e}")
        sys.exit(1)

def main():
    """메인 함수"""
    if not check_openssl():
        print("Error: OpenSSL is not installed or not found in PATH")
        print("Please install OpenSSL first:")
        print("  macOS: brew install openssl")
        print("  Ubuntu/Debian: sudo apt-get install openssl")
        print("  CentOS/RHEL: sudo yum install openssl")
        sys.exit(1)
    
    # 도메인 설정 (환경변수나 기본값 사용)
    domain = os.environ.get('SSL_DOMAIN', 'localhost')
    cert_dir = os.environ.get('SSL_CERT_DIR', 'certs')
    
    try:
        cert_file, key_file = generate_ssl_certificate(cert_dir, domain)
        
        # 파일 권한 설정 (개인키는 더 엄격하게)
        os.chmod(key_file, 0o600)  # 소유자만 읽기/쓰기
        os.chmod(cert_file, 0o644)  # 소유자 읽기/쓰기, 그룹/기타 읽기
        
        print("\nSSL certificate setup completed!")
        print("You can now start the HTTPS server.")
        print("\nNote: This is a self-signed certificate.")
        print("Your browser will show a security warning that you need to accept.")
        
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()