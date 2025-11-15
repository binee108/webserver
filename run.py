#!/usr/bin/env python3
"""
암호화폐 트레이딩 시스템 CLI
모듈식 구조

@FEAT:cli-migration @COMP:route @TYPE:core

역할:
- CLI Manager를 통해 명령어 실행
- 키보드 인터럽트 및 예외 처리
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))


def main():
    """CLI 진입점 - CLI Manager를 통한 명령어 실행"""
    from cli.manager import TradingSystemCLI

    cli = TradingSystemCLI()
    return cli.run(sys.argv[1:])


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
