#!/usr/bin/env python3
# @FEAT:precision-system @COMP:util @TYPE:helper
"""
Precision System Cache Migration Script

Revision 4 변경사항:
- MarketInfo.precision_provider는 이제 REQUIRED 필드
- 기존 캐시된 MarketInfo 객체는 precision_provider=None일 수 있음
- 이 스크립트는 배포 시 기존 캐시를 완전히 제거하여 새로 생성되도록 함

실행 방법:
    python web_server/scripts/migrate_precision_cache.py

또는 배포 스크립트에 통합:
    ./deploy.sh  # 내부에서 이 스크립트 자동 실행
"""

import sys
import logging
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def clear_file_cache():
    """파일 기반 캐시 제거"""
    cache_dir = project_root / 'web_server' / 'cache'
    if cache_dir.exists():
        import shutil
        logger.info(f"🗑️  Removing file cache: {cache_dir}")
        shutil.rmtree(cache_dir)
        logger.info("✅ File cache cleared")
    else:
        logger.info("ℹ️  No file cache found (already clean)")


def clear_redis_cache():
    """Redis 캐시 제거 (사용 중인 경우)"""
    try:
        import redis
        # Redis 연결 정보는 환경 변수나 config에서 가져오기
        # 현재는 사용하지 않으므로 스킵
        logger.info("ℹ️  Redis cache clearing skipped (not configured)")
    except ImportError:
        logger.info("ℹ️  Redis not installed (file cache only)")


def main():
    """메인 마이그레이션 실행"""
    logger.info("=" * 60)
    logger.info("🔄 Precision System Cache Migration - Revision 4")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📋 작업 내용:")
    logger.info("  - 기존 MarketInfo 캐시 완전 제거")
    logger.info("  - 서비스 재시작 시 새 구조로 자동 재생성")
    logger.info("  - precision_provider 필드 포함된 새 객체 생성 보장")
    logger.info("")

    # 캐시 제거
    clear_file_cache()
    clear_redis_cache()

    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ Migration Complete!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("다음 단계:")
    logger.info("  1. python run.py restart  # 서비스 재시작")
    logger.info("  2. 로그 확인: tail -f web_server/logs/app.log")
    logger.info("  3. 모든 MarketInfo 객체에 precision_provider 필드 생성 확인")
    logger.info("")


if __name__ == '__main__':
    main()
