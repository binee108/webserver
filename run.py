#!/usr/bin/env python3
"""
암호화폐 트레이딩 시스템 통합 실행 스크립트
크로스 플랫폼 지원 (Windows, macOS, Linux)
"""

import os
import sys
import time
import subprocess
import platform
import webbrowser
import argparse
import socket
import urllib.request
from pathlib import Path

class Colors:
    """컬러 출력용 ANSI 코드"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    @classmethod
    def disable_on_windows(cls):
        """Windows에서 컬러 비활성화"""
        if platform.system() == 'Windows':
            for attr in dir(cls):
                if not attr.startswith('_') and attr not in ['disable_on_windows']:
                    setattr(cls, attr, '')

# Windows에서는 컬러 비활성화 (호환성)
if platform.system() == 'Windows':
    Colors.disable_on_windows()

class TradingSystemManager:
    """트레이딩 시스템 관리 클래스"""
    
    def __init__(self):
        self.root_dir = Path(__file__).parent
        self.web_server_dir = self.root_dir / "web_server"
        self.docker_compose_file = self.root_dir / "docker-compose.yml"
        
    def print_banner(self):
        """시스템 배너 출력"""
        print("=" * 60 + f"{Colors.RESET}\n")
        print("🚀 암호화폐 트레이딩 시스템")
        print("   Cryptocurrency Trading System")
        print("=" * 60 + f"{Colors.RESET}\n")
    
    def print_status(self, message, status="info"):
        """상태 메시지 출력"""
        if status == "success":
            print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")
        elif status == "error":
            print(f"{Colors.RED}❌ {message}{Colors.RESET}")
        elif status == "warning":
            print(f"{Colors.YELLOW}⚠️  {message}{Colors.RESET}")
        elif status == "info":
            print(f"{Colors.BLUE}ℹ️  {message}{Colors.RESET}")
        else:
            print(f"📝 {message}")
    
    def get_local_ip(self):
        """로컬 네트워크 IP 주소 가져오기"""
        try:
            # 임시 소켓을 만들어서 로컬 IP 확인
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return None
    
    def get_external_ip(self):
        """외부 IP 주소 가져오기"""
        try:
            # 여러 서비스를 시도해서 외부 IP 확인
            services = [
                "https://api.ipify.org",
                "https://icanhazip.com",
                "https://checkip.amazonaws.com"
            ]
            
            for service in services:
                try:
                    with urllib.request.urlopen(service, timeout=5) as response:
                        return response.read().decode().strip()
                except:
                    continue
            return None
        except Exception:
            return None
    
    def check_requirements(self):
        """시스템 요구사항 확인"""
        self.print_status("시스템 요구사항 확인 중...", "info")
        
        # Docker 설치 확인
        try:
            result = subprocess.run(['docker', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, 'docker')
            self.print_status(f"Docker 확인: {result.stdout.strip()}", "success")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.print_status("Docker가 설치되지 않았습니다.", "error")
            self.print_status("Docker Desktop을 설치해주세요: https://www.docker.com/get-started", "info")
            return False
        
        # Docker Compose 설치 확인
        try:
            result = subprocess.run(['docker-compose', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, 'docker-compose')
            self.print_status(f"Docker Compose 확인: {result.stdout.strip()}", "success")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.print_status("Docker Compose가 설치되지 않았습니다.", "error")
            return False
        
        # Docker 실행 상태 확인
        try:
            result = subprocess.run(['docker', 'info'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, 'docker info')
            self.print_status("Docker 서비스 실행 중", "success")
        except subprocess.CalledProcessError:
            self.print_status("Docker 서비스가 실행되고 있지 않습니다.", "error")
            self.print_status("Docker Desktop을 시작해주세요.", "info")
            return False
        
        return True
    
    def run_command(self, command, cwd=None, show_output=False):
        """명령어 실행"""
        try:
            if show_output:
                result = subprocess.run(command, shell=True, cwd=cwd, check=True)
            else:
                result = subprocess.run(command, shell=True, cwd=cwd, 
                                      capture_output=True, text=True, check=True)
            return result
        except subprocess.CalledProcessError as e:
            if not show_output and hasattr(e, 'stderr') and e.stderr:
                self.print_status(f"명령어 실행 오류: {command}", "error")
                self.print_status(f"오류 메시지: {e.stderr.strip()}", "error")
            raise e
    
    def wait_for_postgres(self, max_attempts=30):
        """PostgreSQL 준비 대기"""
        self.print_status("PostgreSQL 데이터베이스 준비 대기 중...", "info")
        
        for attempt in range(max_attempts):
            try:
                result = subprocess.run([
                    'docker-compose', 'exec', '-T', 'postgres', 
                    'pg_isready', '-U', 'trader', '-d', 'trading_system'
                ], capture_output=True, text=True, cwd=self.root_dir)
                
                if result.returncode == 0:
                    self.print_status("PostgreSQL 준비 완료!", "success")
                    return True
                    
            except subprocess.CalledProcessError:
                pass
            
            if attempt < max_attempts - 1:
                print(f"{Colors.YELLOW}  대기 중... ({attempt + 1}/{max_attempts}){Colors.RESET}")
                time.sleep(2)
        
        self.print_status("PostgreSQL 시작 시간 초과", "error")
        return False
    
    def generate_ssl_certificates(self):
        """SSL 인증서 생성 (Pure Python, OpenSSL 도구 불필요)"""
        self.print_status("SSL 인증서 확인 중...", "info")
        
        # SSL 인증서 파일 경로
        cert_dir = self.root_dir / "certs"
        cert_file = cert_dir / "cert.pem"
        key_file = cert_dir / "key.pem"
        
        try:
            # cryptography 라이브러리 import
            try:
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                from cryptography.hazmat.primitives import hashes, serialization
                from cryptography.hazmat.primitives.asymmetric import rsa
                from datetime import datetime, timedelta, timezone
                import ipaddress
            except ImportError as e:
                self.print_status("cryptography 라이브러리가 설치되지 않았습니다.", "error")
                self.print_status("다음 명령으로 설치하세요: pip install cryptography", "info")
                return False
            
            # 디렉토리 생성
            cert_dir.mkdir(exist_ok=True)
            
            # 이미 유효한 인증서가 있는지 확인
            if cert_file.exists() and key_file.exists():
                try:
                    with open(cert_file, 'rb') as f:
                        cert = x509.load_pem_x509_certificate(f.read())
                    
                    # 인증서 만료일 확인 (30일 이상 남았으면 유효)
                    if cert.not_valid_after > datetime.now(timezone.utc) + timedelta(days=30):
                        self.print_status("유효한 SSL 인증서가 이미 존재합니다", "success")
                        return True
                except Exception:
                    pass  # 인증서 읽기 실패시 새로 생성
            
            self.print_status("SSL 인증서 생성 중...", "info")
            
            # 개인키 생성
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            
            # 인증서 주체 정보 설정
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Seoul"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Seoul"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Trading System"),
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            ])
            
            # 인증서 생성
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.now(timezone.utc)
            ).not_valid_after(
                datetime.now(timezone.utc) + timedelta(days=365)
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    x509.IPAddress(ipaddress.IPv6Address("::1")),
                    x509.IPAddress(ipaddress.IPv4Address("220.127.44.59")),
                ]),
                critical=False,
            ).sign(private_key, hashes.SHA256())
            
            # 개인키를 파일에 저장
            with open(key_file, 'wb') as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # 인증서를 파일에 저장
            with open(cert_file, 'wb') as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            # 파일 권한 설정
            key_file.chmod(0o600)  # 개인키는 소유자만 읽기/쓰기
            cert_file.chmod(0o644)  # 인증서는 읽기 전용
            
            self.print_status("SSL 인증서가 성공적으로 생성되었습니다", "success")
            self.print_status(f"  인증서: {cert_file}", "info")
            self.print_status(f"  개인키: {key_file}", "info")
            self.print_status("  유효기간: 365일", "info")
            self.print_status("  도메인: localhost, 127.0.0.1, ::1", "info")
            
            return True
            
        except Exception as e:
            self.print_status(f"SSL 인증서 생성 중 오류 발생: {e}", "error")
            return False

    def start_system(self):
        """시스템 시작"""
        self.print_banner()
        
        if not self.check_requirements():
            return False
        
        try:
            # 기존 컨테이너 정리
            self.print_status("기존 컨테이너 정리 중...", "info")
            self.run_command("docker-compose down", cwd=self.root_dir)
            
            # SSL 인증서 생성/확인
            if not self.generate_ssl_certificates():
                return False
            
            # PostgreSQL 먼저 시작
            self.print_status("PostgreSQL 데이터베이스 시작 중...", "info")
            self.run_command("docker-compose up -d postgres", cwd=self.root_dir)
            
            # PostgreSQL 준비 대기
            if not self.wait_for_postgres():
                return False
            
            # Flask 앱 시작
            self.print_status("Flask 애플리케이션 시작 중...", "info")
            self.run_command("docker-compose up -d app", cwd=self.root_dir)
            
            # 앱 준비 대기
            self.print_status("Flask 애플리케이션 준비 대기 중...", "info")
            time.sleep(5)
            
            # 데이터베이스 테이블은 애플리케이션 시작 시 자동으로 생성됩니다
            self.print_status("데이터베이스 테이블 자동 생성 준비 완료", "success")
            
            # Nginx 시작 (마지막에)
            self.print_status("Nginx 리버스 프록시 시작 중...", "info")
            self.run_command("docker-compose up -d nginx", cwd=self.root_dir)
            
            # 네트워크 정보 수집
            local_ip = self.get_local_ip()
            external_ip = self.get_external_ip()
            
            # 시작 완료 메시지
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ 트레이딩 시스템이 성공적으로 시작되었습니다!{Colors.RESET}\n")
            
            print(f"{Colors.CYAN}🌐 웹 인터페이스 접근 주소:{Colors.RESET}")
            print(f"   로컬: https://localhost")
            if local_ip and local_ip != "127.0.0.1":
                print(f"   네트워크: https://{local_ip}")
            if external_ip:
                print(f"   외부: https://{external_ip}")
            print()
            
            print(f"{Colors.BLUE}🔧 내부 HTTP 접근:{Colors.RESET}")
            print(f"   로컬: http://localhost:5001 (직접 Flask 접근)")
            if local_ip and local_ip != "127.0.0.1":
                print(f"   네트워크: http://{local_ip}:5001")
            print()
            
            print(f"{Colors.RED}🚫 외부 HTTP: http://localhost → HTTPS로 리다이렉트{Colors.RESET}")
            print(f"{Colors.MAGENTA}🐘 PostgreSQL: localhost:5432{Colors.RESET}\n")
            
            print(f"{Colors.YELLOW}⚠️  브라우저에서 보안 경고가 나타나면:{Colors.RESET}")
            print("   Chrome: '고급' → '안전하지 않음(권장하지 않음)' → '계속 진행'")
            print("   Safari: '고급' → '계속 진행'\n")
            
            print(f"{Colors.WHITE}👤 기본 로그인 정보:{Colors.RESET}")
            print("   사용자명: admin")
            print("   비밀번호: admin123\n")
            
            print(f"{Colors.GREEN}🔗 웹훅 접근:{Colors.RESET}")
            print("   HTTPS (로컬): https://localhost/api/webhook")
            if external_ip:
                print(f"   HTTPS (외부): https://{external_ip}/api/webhook")
            print("   HTTP (내부): http://localhost:5001/api/webhook")
            print()
            
            print(f"{Colors.CYAN}📋 유용한 명령어:{Colors.RESET}")
            print("   python run.py stop     - 시스템 중지")
            print("   python run.py logs     - 로그 확인")
            print("   python run.py status   - 상태 확인")
            print("   python run.py restart  - 재시작")
            
            # 브라우저 자동 열기 (선택사항)
            try:
                time.sleep(5)  # 서비스 완전 시작 대기
                webbrowser.open('https://localhost')
            except:
                pass
            
            return True
            
        except subprocess.CalledProcessError as e:
            self.print_status(f"시스템 시작 실패: {e}", "error")
            return False
    
    def stop_system(self):
        """시스템 중지"""
        self.print_status("트레이딩 시스템 중지 중...", "info")
        
        try:
            self.run_command("docker-compose down", cwd=self.root_dir)
            self.print_status("시스템이 중지되었습니다.", "success")
            print(f"\n{Colors.BLUE}💡 데이터는 보존되었습니다. 다시 시작하려면 'python run.py start'를 실행하세요.{Colors.RESET}")
            print(f"{Colors.RED}🗑️  모든 데이터를 삭제하려면 'python run.py clean'을 실행하세요.{Colors.RESET}")
            return True
        except subprocess.CalledProcessError as e:
            self.print_status(f"시스템 중지 실패: {e}", "error")
            return False
    
    def restart_system(self):
        """시스템 재시작"""
        self.print_status("시스템 재시작 중...", "info")
        self.stop_system()
        time.sleep(2)
        return self.start_system()
    
    def show_logs(self, follow=False):
        """로그 확인"""
        try:
            cmd = "docker-compose logs"
            if follow:
                cmd += " -f"
            self.run_command(cmd, cwd=self.root_dir, show_output=True)
        except subprocess.CalledProcessError as e:
            self.print_status(f"로그 확인 실패: {e}", "error")
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}로그 확인을 중단했습니다.{Colors.RESET}")
    
    def show_status(self):
        """시스템 상태 확인"""
        self.print_status("시스템 상태 확인 중...", "info")
        
        try:
            result = self.run_command("docker-compose ps", cwd=self.root_dir)
            print(f"\n{Colors.CYAN}컨테이너 상태:{Colors.RESET}")
            print(result.stdout)
            
            # 서비스 접근 가능 여부 확인
            print(f"{Colors.CYAN}서비스 접근성 확인:{Colors.RESET}")
            
            # HTTPS 확인 (Nginx)
            try:
                import urllib.request
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                with urllib.request.urlopen('https://localhost/api/system/health', timeout=5, context=ctx) as response:
                    if response.status == 200:
                        self.print_status("HTTPS 서비스 (https://localhost): 정상", "success")
                    else:
                        self.print_status("HTTPS 서비스: 응답 이상", "warning")
            except Exception as e:
                self.print_status(f"HTTPS 서비스: 접근 불가 ({str(e)})", "error")
            
            # HTTP 리다이렉트 확인
            try:
                import urllib.request
                import urllib.error
                
                # 리다이렉트를 따르지 않는 요청 생성
                class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):
                        return None
                
                opener = urllib.request.build_opener(NoRedirectHandler)
                
                try:
                    response = opener.open('http://localhost', timeout=5)
                    self.print_status("HTTP 서비스: 리다이렉트 미작동 (보안 위험)", "warning")
                except urllib.error.HTTPError as e:
                    if e.code in [301, 302]:
                        self.print_status("HTTP → HTTPS 리다이렉트: 정상", "success")
                    else:
                        self.print_status(f"HTTP 리다이렉트: 비정상 응답 ({e.code})", "warning")
            except Exception:
                self.print_status("HTTP 리다이렉트: 확인 불가", "warning")
            
            # 직접 Flask 접근 확인 (내부용)
            try:
                import urllib.request
                with urllib.request.urlopen('http://localhost:5001/api/system/health', timeout=5) as response:
                    if response.status == 200:
                        self.print_status("내부 Flask HTTP (http://localhost:5001): 정상", "success")
                    else:
                        self.print_status("내부 Flask HTTP: 응답 이상", "warning")
            except Exception as e:
                self.print_status(f"내부 Flask HTTP: 접근 불가 ({str(e)})", "error")
                
        except subprocess.CalledProcessError as e:
            self.print_status(f"상태 확인 실패: {e}", "error")
    
    def clean_system(self):
        """시스템 완전 정리 (데이터, SSL 인증서, Docker 이미지 포함)"""
        self.print_status("시스템 완전 정리를 시작합니다...", "warning")
        
        # 상세한 경고 메시지
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  경고: 다음 항목들이 완전히 삭제됩니다:{Colors.RESET}")
        print(f"{Colors.RED}  • 모든 데이터베이스 데이터 (사용자, 거래기록, 설정 등){Colors.RESET}")
        print(f"{Colors.RED}  • SSL 인증서 파일 (./certs/ 디렉토리){Colors.RESET}")
        print(f"{Colors.RED}  • Docker 이미지 (재빌드 필요){Colors.RESET}")
        print(f"{Colors.RED}  • Docker 볼륨 및 네트워크{Colors.RESET}")
        print(f"{Colors.RED}  • 로그 파일{Colors.RESET}")
        print(f"\n{Colors.YELLOW}이 작업은 되돌릴 수 없습니다!{Colors.RESET}\n")
        
        try:
            # 확인 메시지
            if platform.system() == 'Windows':
                confirm = input("정말로 모든 데이터를 삭제하시겠습니까? (yes/no): ")
            else:
                confirm = input(f"{Colors.RED}정말로 모든 데이터를 삭제하시겠습니까? (yes/no): {Colors.RESET}")
            
            if confirm.lower() not in ['yes', 'y']:
                self.print_status("작업이 취소되었습니다.", "info")
                return True
            
            # 1. Docker 컨테이너, 볼륨, 이미지 삭제
            self.print_status("Docker 컨테이너, 볼륨, 이미지 삭제 중...", "info")
            try:
                self.run_command("docker-compose down --rmi all -v", cwd=self.root_dir)
                self.print_status("Docker 컨테이너, 볼륨, 이미지 삭제 완료", "success")
            except subprocess.CalledProcessError as e:
                self.print_status(f"Docker 정리 중 일부 오류 발생: {e}", "warning")
                # 기본 정리라도 시도
                try:
                    self.run_command("docker-compose down -v", cwd=self.root_dir)
                    self.print_status("기본 Docker 정리 완료", "success")
                except subprocess.CalledProcessError:
                    self.print_status("Docker 정리 실패", "error")
            
            # 2. SSL 인증서 삭제
            cert_dir = self.root_dir / "certs"
            if cert_dir.exists():
                self.print_status("SSL 인증서 삭제 중...", "info")
                try:
                    import shutil
                    shutil.rmtree(cert_dir)
                    self.print_status("SSL 인증서 삭제 완료", "success")
                except Exception as e:
                    self.print_status(f"SSL 인증서 삭제 실패: {e}", "error")
            else:
                self.print_status("SSL 인증서 디렉토리가 존재하지 않습니다", "info")
            
            # 3. Docker 시스템 정리
            self.print_status("Docker 시스템 정리 중...", "info")
            try:
                # 미사용 볼륨 정리
                result = self.run_command("docker volume prune -f")
                if result.stdout.strip():
                    self.print_status("미사용 Docker 볼륨 정리 완료", "success")
                
                # 미사용 네트워크 정리
                result = self.run_command("docker network prune -f")
                if result.stdout.strip():
                    self.print_status("미사용 Docker 네트워크 정리 완료", "success")
                
            except subprocess.CalledProcessError as e:
                self.print_status(f"Docker 시스템 정리 중 오류: {e}", "warning")
            
            # 4. 완료 메시지
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ 시스템 완전 정리가 완료되었습니다!{Colors.RESET}")
            print(f"\n{Colors.CYAN}다음에 시스템을 시작할 때:{Colors.RESET}")
            print(f"  • 새로운 SSL 인증서가 자동 생성됩니다")
            print(f"  • Docker 이미지가 다시 빌드됩니다")
            print(f"  • 완전히 새로운 데이터베이스로 시작됩니다")
            print(f"  • 기본 관리자 계정 (admin/admin123)이 다시 생성됩니다\n")
            
            return True
            
        except Exception as e:
            self.print_status(f"시스템 정리 중 예상치 못한 오류: {e}", "error")
            return False

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='암호화폐 트레이딩 시스템 관리')
    parser.add_argument('command', choices=['start', 'stop', 'restart', 'logs', 'status', 'clean'],
                       help='실행할 명령어')
    parser.add_argument('-f', '--follow', action='store_true',
                       help='로그를 실시간으로 확인 (logs 명령어와 함께 사용)')
    
    # 인수가 없으면 help 출력
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    
    args = parser.parse_args()
    
    manager = TradingSystemManager()
    
    try:
        if args.command == 'start':
            success = manager.start_system()
        elif args.command == 'stop':
            success = manager.stop_system()
        elif args.command == 'restart':
            success = manager.restart_system()
        elif args.command == 'logs':
            manager.show_logs(follow=args.follow)
            success = True
        elif args.command == 'status':
            manager.show_status()
            success = True
        elif args.command == 'clean':
            success = manager.clean_system()
        else:
            parser.print_help()
            success = False
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}작업이 중단되었습니다.{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        manager.print_status(f"예상치 못한 오류: {e}", "error")
        sys.exit(1)

if __name__ == "__main__":
    main()