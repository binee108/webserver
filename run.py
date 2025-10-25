#!/usr/bin/env python3
"""
암호화폐 트레이딩 시스템 CLI
신규 모듈식 구조 + 레거시 폴백 지원

@FEAT:cli-migration @COMP:route @TYPE:core

역할:
- 신규 CLI Manager를 통해 명령어 실행
- 실패 시 레거시 run_legacy.py로 폴백
- 키보드 인터럽트 및 예외 처리
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))


def main():
    """CLI 진입점 - 신규 CLI Manager 사용, 실패 시 레거시 폴백"""
    try:
        # 신규 CLI Manager 사용
        from cli.manager import TradingSystemCLI

        cli = TradingSystemCLI()
        return cli.run(sys.argv[1:])

    except (ImportError, AttributeError, NotImplementedError) as e:
        # 신규 모듈이 아직 구현되지 않은 경우
        print(f"\n⚠️  신규 CLI 모듈 미구현, 레거시 모드로 전환")
        print(f"    사유: {type(e).__name__}: {e}\n")

        # 레거시 폴백
        from run_legacy import main as legacy_main
        return legacy_main()

    except Exception as e:
        # 예상치 못한 오류 발생 시 레거시로 폴백
        print(f"\n⚠️  신규 CLI 실패, 레거시 모드로 전환")
        print(f"    사유: {type(e).__name__}: {e}\n")

        # 레거시 폴백
        from run_legacy import main as legacy_main
        return legacy_main()


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        print("\n\n⚠️  작업이 중단되었습니다.")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 치명적 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
