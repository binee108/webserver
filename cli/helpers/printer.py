"""CLI 출력 헬퍼 모듈

@FEAT:cli-migration @COMP:util @TYPE:helper
"""
import platform


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


class StatusPrinter:
    """상태 메시지 출력 헬퍼

    TradingSystemManager의 print_status(), print_banner() 로직을 독립 모듈로 분리
    """

    def __init__(self):
        """초기화 - Windows에서 컬러 비활성화"""
        if platform.system() == 'Windows':
            Colors.disable_on_windows()

    def print_status(self, message: str, status: str = "info"):
        """상태 메시지 출력

        Args:
            message (str): 출력할 메시지
            status (str): 상태 타입 ("info", "success", "error", "warning")
        """
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

    def print_banner(self, worktree_env=None, flask_port=None, postgres_port=None, compose_project_name=None):
        """시작 배너 출력

        Args:
            worktree_env (dict, optional): 워크트리 환경 정보
            flask_port (int, optional): Flask 포트 번호
            postgres_port (int, optional): PostgreSQL 포트 번호
            compose_project_name (str, optional): Docker Compose 프로젝트 이름
        """
        print("=" * 60 + f"{Colors.RESET}\n")
        print("🚀 암호화폐 트레이딩 시스템")
        print("   Cryptocurrency Trading System")

        # 워크트리 환경 표시
        if worktree_env:
            print(f"\n{Colors.CYAN}📂 워크트리 환경: {worktree_env['name']}{Colors.RESET}")
            print(f"{Colors.BLUE}   Flask 포트: {flask_port}, PostgreSQL 포트: {postgres_port}{Colors.RESET}")
            print(f"{Colors.YELLOW}   프로젝트명: {compose_project_name}{Colors.RESET}")
        else:
            print(f"\n{Colors.GREEN}🏠 메인 프로젝트{Colors.RESET}")

        print("=" * 60 + f"{Colors.RESET}\n")

    def print_section(self, title: str):
        """섹션 제목 출력

        Args:
            title (str): 섹션 제목
        """
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}▶ {title}{Colors.RESET}")

    def print_separator(self, message: str = ""):
        """구분선 출력

        Args:
            message (str, optional): 구분선과 함께 표시할 메시지
        """
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        if message:
            self.print_status(message, "info")
            print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
