"""SSL 인증서 관리 헬퍼 모듈

@FEAT:cli-migration @COMP:util @TYPE:helper
"""
from pathlib import Path
from typing import Optional


class SSLHelper:
    """SSL 인증서 관리 헬퍼

    TradingSystemManager의 SSL 관련 메서드들을 독립 모듈로 분리:
    - generate_ssl_certificates()
    - _check_existing_certificate()
    """

    def __init__(self, printer, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            root_dir: 프로젝트 루트 디렉토리
        """
        self.printer = printer
        self.root_dir = root_dir

    def generate_ssl_certificates(self, domain: Optional[str] = "localhost") -> bool:
        """SSL 인증서 생성 (Pure Python, OpenSSL 도구 불필요)

        Args:
            domain (str): 도메인 이름 또는 IP 주소

        Returns:
            bool: 성공 시 True
        """
        self.printer.print_status("SSL 인증서 확인 중...", "info")

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
            except ImportError:
                self.printer.print_status("cryptography 라이브러리가 설치되지 않았습니다.", "error")
                self.printer.print_status("다음 명령으로 설치하세요: pip install cryptography", "info")
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
                        self.printer.print_status("유효한 SSL 인증서가 이미 존재합니다", "success")
                        return True
                except Exception:
                    pass  # 인증서 읽기 실패시 새로 생성

            self.printer.print_status("SSL 인증서 생성 중...", "info")

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
                x509.NameAttribute(NameOID.COMMON_NAME, domain),
            ])

            # SubjectAlternativeName 설정
            san_list = [x509.DNSName("localhost")]

            # IP 주소 추가
            try:
                # 기본 로컬 IP
                san_list.append(x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")))
                san_list.append(x509.IPAddress(ipaddress.IPv6Address("::1")))

                # domain이 IP 주소인 경우 추가
                if domain != "localhost":
                    try:
                        # IPv4 시도
                        ip_addr = ipaddress.IPv4Address(domain)
                        san_list.append(x509.IPAddress(ip_addr))
                    except ipaddress.AddressValueError:
                        try:
                            # IPv6 시도
                            ip_addr = ipaddress.IPv6Address(domain)
                            san_list.append(x509.IPAddress(ip_addr))
                        except ipaddress.AddressValueError:
                            # IP가 아닌 도메인 이름
                            san_list.append(x509.DNSName(domain))

            except Exception:
                pass

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
                x509.SubjectAlternativeName(san_list),
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

            self.printer.print_status("SSL 인증서가 성공적으로 생성되었습니다", "success")
            self.printer.print_status(f"  인증서: {cert_file}", "info")
            self.printer.print_status(f"  개인키: {key_file}", "info")
            self.printer.print_status("  유효기간: 365일", "info")
            self.printer.print_status(f"  도메인: {domain}, localhost, 127.0.0.1, ::1", "info")

            return True

        except Exception as e:
            self.printer.print_status(f"SSL 인증서 생성 중 오류 발생: {e}", "error")
            return False
