"""환경 변수 관리 헬퍼 모듈

@FEAT:cli-migration @COMP:util @TYPE:helper
"""
import secrets
import getpass
from pathlib import Path
from typing import Dict, Optional

from cli.config import SystemConfig
from cli.helpers.printer import Colors


class EnvHelper:
    """환경 설정 관리 헬퍼

    EnvSetupWizard 클래스의 로직을 독립 모듈로 분리:
    - setup_environment()
    - write_env_file()
    - _write_env_section()

    Note: 환경별 기본값은 cli.config.SystemConfig에서 가져옴
    """

    def __init__(self, printer, network, root_dir: Path):
        """초기화

        Args:
            printer: StatusPrinter 인스턴스
            network: NetworkHelper 인스턴스
            root_dir: 프로젝트 루트 디렉토리
        """
        self.printer = printer
        self.network = network
        self.root_dir = root_dir
        self.env_type = None
        self.env_config = {}
        self.docker_compose = True  # 기본값: Docker 사용

    def print_banner(self):
        """설정 마법사 배너 출력"""
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN}🔧 환경 설정 마법사{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")

    def get_input(self, prompt: str, default: Optional[str] = None) -> str:
        """사용자 입력 받기

        Args:
            prompt (str): 입력 프롬프트
            default (str, optional): 기본값

        Returns:
            str: 사용자 입력 또는 기본값
        """
        if default:
            prompt_text = f"{prompt} [{Colors.YELLOW}{default}{Colors.RESET}]: "
        else:
            prompt_text = f"{prompt}: "

        value = input(prompt_text).strip()
        return value if value else default

    def get_password_input(self, prompt: str, default: Optional[str] = None) -> str:
        """비밀번호 입력 받기

        Args:
            prompt (str): 입력 프롬프트
            default (str, optional): 기본값

        Returns:
            str: 비밀번호
        """
        if default:
            prompt_text = f"{prompt} [기본값 사용]: "
            value = getpass.getpass(prompt_text)
            return value if value else default
        else:
            return getpass.getpass(f"{prompt}: ")

    def check_env_file(self) -> bool:
        """기존 .env 파일 확인

        Returns:
            bool: 새로 설정할지 여부
        """
        env_file = self.root_dir / '.env'
        if env_file.exists():
            print(f"{Colors.GREEN}✅ .env 파일이 이미 존재합니다.{Colors.RESET}")
            overwrite = self.get_input("새로 설정하시겠습니까? (y/n)", "n")
            return overwrite.lower() == 'y'
        return True

    def select_environment(self):
        """환경 선택"""
        print(f"{Colors.CYAN}📋 환경 선택{Colors.RESET}\n")
        print("어떤 환경을 설정하시겠습니까?")
        print("1) Development (개발)")
        print("2) Staging (스테이징)")
        print("3) Production (운영)")

        choice = self.get_input("선택 [1-3]", "1")

        env_map = {
            '1': 'development',
            '2': 'staging',
            '3': 'production'
        }

        self.env_type = env_map.get(choice, 'development')
        print(f"선택된 환경: {Colors.GREEN}{self.env_type.capitalize()}{Colors.RESET}\n")

    def setup_basic_config(self):
        """기본 설정"""
        print(f"{Colors.CYAN}📝 기본 설정{Colors.RESET}\n")

        # SECRET_KEY 설정
        print("SECRET_KEY 생성 방법:")
        print("- Enter: 자동 생성 (권장)")
        print("- 직접 입력: 32자 이상 랜덤 문자열")

        secret_key = self.get_input("SECRET_KEY", "자동 생성")
        if secret_key == "자동 생성":
            secret_key = secrets.token_hex(32)
            print(f"SECRET_KEY가 자동 생성되었습니다: {Colors.GREEN}****{secret_key[-8:]}{Colors.RESET}")

        self.env_config['SECRET_KEY'] = secret_key

        # Flask 환경 자동 설정
        self.env_config['FLASK_ENV'] = SystemConfig.ENV_DEFAULTS[self.env_type]['FLASK_ENV']
        print(f"Flask 환경 모드가 자동으로 설정됩니다: {Colors.GREEN}{self.env_config['FLASK_ENV']}{Colors.RESET}\n")

    def setup_database(self):
        """데이터베이스 설정"""
        print(f"{Colors.CYAN}🗄️  PostgreSQL 데이터베이스 설정{Colors.RESET}\n")

        use_docker = self.get_input("Docker Compose를 사용하시겠습니까? (y/n)", "y")
        self.docker_compose = use_docker.lower() == 'y'

        if self.docker_compose:
            print("\n데이터베이스가 Docker 컨테이너로 자동 구성됩니다.")

            # 환경별 기본 데이터베이스 이름
            db_names = {
                'development': 'trading_dev',
                'staging': 'trading_staging',
                'production': 'trading_prod'
            }

            db_name = self.get_input("데이터베이스 이름", db_names[self.env_type])
            db_user = self.get_input("데이터베이스 사용자", "trader")

            # Production 환경에서는 강력한 비밀번호 권장
            if self.env_type == 'production':
                print(f"{Colors.YELLOW}⚠️  Production 환경입니다. 강력한 비밀번호를 사용하세요!{Colors.RESET}")
                db_password = self.get_password_input("데이터베이스 비밀번호")
            else:
                db_password = self.get_password_input("데이터베이스 비밀번호", "password123")

            self.env_config['DATABASE_URL'] = f"postgresql://{db_user}:{db_password}@postgres:5432/{db_name}"
        else:
            print("\n외부 PostgreSQL 서버 정보를 입력하세요.")
            db_host = self.get_input("데이터베이스 호스트")
            db_port = self.get_input("데이터베이스 포트", "5432")
            db_name = self.get_input("데이터베이스 이름")
            db_user = self.get_input("데이터베이스 사용자")
            db_password = self.get_password_input("데이터베이스 비밀번호")

            self.env_config['DATABASE_URL'] = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

        print(f"연결 문자열: {Colors.GREEN}postgresql://****@****{Colors.RESET}\n")


    def setup_ssl(self):
        """SSL/HTTPS 설정"""
        print(f"{Colors.CYAN}🔒 SSL/HTTPS 설정{Colors.RESET}\n")
        print("SSL이 기본적으로 활성화됩니다.\n")

        print("SSL 도메인 설정:")
        print("1) localhost (개발/테스트용)")
        print("2) 공인 IP 주소")
        print("3) 도메인 이름 (추후 정식 서비스 시)")

        choice = self.get_input("선택 [1-3]", "1")

        if choice == "2":
            # 현재 공인 IP 자동 감지 시도
            print("공인 IP 감지 중...")
            external_ip = self.network.get_external_ip()
            if external_ip:
                print(f"감지된 공인 IP: {Colors.GREEN}{external_ip}{Colors.RESET}")
                use_detected = self.get_input("이 IP를 사용하시겠습니까? (y/n)", "y")
                if use_detected.lower() == 'y':
                    self.env_config['SSL_DOMAIN'] = external_ip
                else:
                    ip = self.get_input("공인 IP 주소를 입력하세요")
                    self.env_config['SSL_DOMAIN'] = ip
            else:
                ip = self.get_input("공인 IP 주소를 입력하세요")
                self.env_config['SSL_DOMAIN'] = ip
        elif choice == "3":
            domain = self.get_input("도메인 이름을 입력하세요")
            self.env_config['SSL_DOMAIN'] = domain
        else:
            self.env_config['SSL_DOMAIN'] = 'localhost'

        print(f"SSL 도메인: {Colors.GREEN}{self.env_config['SSL_DOMAIN']}{Colors.RESET}")

        # 공통 SSL 설정
        self.env_config['ENABLE_SSL'] = 'true'
        self.env_config['FORCE_HTTPS'] = 'true'
        self.env_config['SSL_CERT_DIR'] = 'certs'
        self.env_config['PORT'] = '443'
        self.env_config['HSTS_MAX_AGE'] = '31536000'
        print()

    def setup_telegram(self):
        """Telegram 설정"""
        print(f"{Colors.CYAN}💬 Telegram 알림 설정{Colors.RESET}\n")

        use_telegram = self.get_input("Telegram 봇을 설정하시겠습니까? (y/n)", "n")

        if use_telegram.lower() == 'y':
            bot_token = self.get_input("Bot Token (Enter: 건너뛰기)", "")
            chat_id = self.get_input("Chat ID (Enter: 건너뛰기)", "")

            if bot_token:
                self.env_config['TELEGRAM_BOT_TOKEN'] = bot_token
            if chat_id:
                self.env_config['TELEGRAM_CHAT_ID'] = chat_id

            if bot_token and chat_id:
                print(f"{Colors.GREEN}✅ Telegram 설정 완료{Colors.RESET}")
            else:
                print(f"{Colors.YELLOW}⚠️  Telegram 설정이 불완전합니다{Colors.RESET}")
        else:
            print("Telegram 설정을 건너뜁니다.")
        print()

    def setup_logging(self):
        """로깅 설정"""
        print(f"{Colors.CYAN}📊 로깅 설정{Colors.RESET}\n")

        # 환경별 기본 로그 레벨
        default_log = SystemConfig.ENV_DEFAULTS[self.env_type]['LOG_LEVEL']
        default_bg_log = SystemConfig.ENV_DEFAULTS[self.env_type]['BACKGROUND_LOG_LEVEL']

        if self.env_type == 'development':
            print(f"로그 레벨이 자동으로 {Colors.GREEN}DEBUG{Colors.RESET}로 설정됩니다.")
        elif self.env_type == 'staging':
            print(f"로그 레벨이 자동으로 {Colors.GREEN}INFO{Colors.RESET}로 설정됩니다.")
        else:
            print(f"로그 레벨이 자동으로 {Colors.GREEN}WARNING{Colors.RESET}으로 설정됩니다.")

        log_file = self.get_input("로그 파일 경로", "logs/app.log")

        self.env_config['LOG_LEVEL'] = default_log
        self.env_config['LOG_FILE'] = log_file
        self.env_config['BACKGROUND_LOG_LEVEL'] = default_bg_log
        print()

    def setup_dev_specific(self):
        """개발 환경 전용 설정"""
        print(f"{Colors.CYAN}🔧 개발 환경 추가 설정{Colors.RESET}\n")

        skip_test = self.get_input("거래소 연결 테스트 건너뛰기 (y/n)", "n")
        self.env_config['SKIP_EXCHANGE_TEST'] = 'True' if skip_test.lower() == 'y' else 'False'
        print()

    def confirm_and_save(self) -> bool:
        """설정 확인 및 저장

        Returns:
            bool: 저장 성공 여부
        """
        print(f"{Colors.CYAN}✅ 설정 확인{Colors.RESET}\n")
        print(f"{'='*50}")
        print(f"{Colors.BOLD}환경 설정 요약{Colors.RESET}")
        print(f"{'='*50}")
        print(f"환경: {Colors.GREEN}{self.env_type.capitalize()}{Colors.RESET}")
        print(f"데이터베이스: PostgreSQL {'(Docker)' if self.docker_compose else '(외부)'}")
        print(f"SSL/HTTPS: {Colors.GREEN}활성화{Colors.RESET}")
        print(f"  - 도메인: {self.env_config.get('SSL_DOMAIN', 'localhost')}")
        print(f"  - HTTPS 강제: {self.env_config.get('FORCE_HTTPS', 'true')}")
        print(f"DEBUG 모드: {self.env_config.get('DEBUG', SystemConfig.ENV_DEFAULTS[self.env_type].get('DEBUG', 'False'))}")

        if 'TELEGRAM_BOT_TOKEN' in self.env_config:
            print(f"Telegram: {Colors.GREEN}설정됨{Colors.RESET}")
        else:
            print(f"Telegram: {Colors.YELLOW}미설정{Colors.RESET}")

        print(f"로그 레벨: {self.env_config.get('LOG_LEVEL', 'INFO')}")
        print(f"{'='*50}\n")

        confirm = self.get_input("이 설정으로 .env 파일을 생성하시겠습니까? (y/n)", "y")

        if confirm.lower() != 'y':
            print(f"{Colors.YELLOW}설정이 취소되었습니다.{Colors.RESET}")
            return False

        # .env 파일 생성
        env_file = self.root_dir / '.env'

        # 모든 설정 병합 (공통 설정 + 환경별 설정 + 사용자 입력)
        final_config = {}
        final_config.update(SystemConfig.COMMON_DEFAULTS)
        final_config.update(SystemConfig.ENV_DEFAULTS[self.env_type])
        final_config.update(self.env_config)

        # .env 파일 작성
        with open(env_file, 'w') as f:
            f.write(f"# Environment Configuration\n")
            f.write(f"# Generated by EnvSetupWizard\n")
            f.write(f"# Environment: {self.env_type}\n\n")

            # 섹션별로 정리해서 작성
            sections = {
                'Flask 설정': ['FLASK_ENV', 'SECRET_KEY', 'DEBUG'],
                '데이터베이스 설정': ['DATABASE_URL'],
                'SSL/HTTPS 설정': ['ENABLE_SSL', 'FORCE_HTTPS', 'SSL_DOMAIN', 'SSL_CERT_DIR', 'PORT', 'HSTS_MAX_AGE'],
                '로깅 설정': ['LOG_LEVEL', 'LOG_FILE', 'BACKGROUND_LOG_LEVEL'],
                '세션 설정': ['SESSION_COOKIE_SECURE', 'SESSION_COOKIE_HTTPONLY', 'SESSION_COOKIE_SAMESITE', 'PERMANENT_SESSION_LIFETIME'],
                'APScheduler 설정': ['SCHEDULER_API_ENABLED'],
                '개발 설정': ['SKIP_EXCHANGE_TEST'],
                'Telegram 설정': ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
            }

            for section, keys in sections.items():
                section_has_content = False
                section_content = []

                for key in keys:
                    if key in final_config:
                        section_has_content = True
                        value = final_config[key]
                        # 비밀번호나 토큰은 마스킹하지 않고 그대로 저장
                        section_content.append(f"{key}={value}")

                if section_has_content:
                    f.write(f"# {section}\n")
                    for line in section_content:
                        f.write(f"{line}\n")
                    f.write("\n")

        print(f"{Colors.GREEN}✅ .env 파일이 성공적으로 생성되었습니다!{Colors.RESET}")
        print(f"파일 위치: {env_file}")
        return True

    def setup_environment(self, env_type: Optional[str] = None) -> bool:
        """환경 설정 마법사 실행

        Args:
            env_type (str, optional): 환경 타입 ("development", "staging", "production")

        Returns:
            bool: 성공 시 True
        """
        if not self.check_env_file():
            return False

        self.print_banner()

        if env_type:
            self.env_type = env_type
        else:
            self.select_environment()

        self.setup_basic_config()
        self.setup_database()
        self.setup_ssl()
        self.setup_telegram()
        self.setup_logging()

        if self.env_type == 'development':
            self.setup_dev_specific()

        return self.confirm_and_save()
