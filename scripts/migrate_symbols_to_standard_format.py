#!/usr/bin/env python3
"""
DB 심볼 마이그레이션 스크립트: {coin}{currency} → {coin}/{currency}

레거시 형식(BTCUSDT, KRW-BTC)을 표준 형식(BTC/USDT, BTC/KRW)으로 변환합니다.

사용법:
    python scripts/migrate_symbols_to_standard_format.py [--dry-run]

옵션:
    --dry-run: 실제 변경 없이 변환 결과만 출력 (기본값)
    --execute: 실제 DB 업데이트 수행
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'web_server'))

from app import create_app, db
from app.models import StrategyPosition, Trade, OpenOrder, TradeExecution
from app.utils.symbol_utils import (
    normalize_symbol_from_db,
    is_standard_format,
    SymbolFormatError
)
from sqlalchemy import text
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SymbolMigrator:
    """심볼 마이그레이션 관리 클래스"""

    def __init__(self, app, dry_run=True):
        self.app = app
        self.dry_run = dry_run
        self.stats = {
            'StrategyPosition': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'Trade': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'OpenOrder': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'TradeExecution': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
        }

    def migrate_table(self, model_class, table_name):
        """특정 테이블의 심볼을 마이그레이션"""
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 {table_name} 마이그레이션 시작")
        logger.info(f"{'='*60}")

        with self.app.app_context():
            # 모든 레코드 조회 (레거시 형식 필터링은 Python에서 수행)
            records = model_class.query.all()
            self.stats[table_name]['total'] = len(records)

            logger.info(f"총 {len(records)}개 레코드 발견")

            for record in records:
                original_symbol = record.symbol

                # 이미 표준 형식인 경우 스킵
                if is_standard_format(original_symbol):
                    self.stats[table_name]['skipped'] += 1
                    logger.debug(f"✅ 스킵 (이미 표준 형식): {original_symbol}")
                    continue

                # 표준 형식으로 변환
                try:
                    # 거래소 정보 추출
                    exchange = None
                    if hasattr(record, 'strategy_account') and record.strategy_account:
                        if hasattr(record.strategy_account, 'account') and record.strategy_account.account:
                            exchange = record.strategy_account.account.exchange

                    standard_symbol = normalize_symbol_from_db(original_symbol, exchange)

                    if original_symbol == standard_symbol:
                        self.stats[table_name]['skipped'] += 1
                        logger.debug(f"✅ 스킵 (변환 불필요): {original_symbol}")
                        continue

                    logger.info(f"🔄 변환: {original_symbol} → {standard_symbol} (ID: {record.id})")

                    if not self.dry_run:
                        record.symbol = standard_symbol
                        self.stats[table_name]['migrated'] += 1
                    else:
                        logger.info(f"   [DRY-RUN] 실제 변경 안 함")
                        self.stats[table_name]['migrated'] += 1

                except SymbolFormatError as e:
                    self.stats[table_name]['errors'] += 1
                    logger.error(f"❌ 변환 실패: {original_symbol} - {e}")
                except Exception as e:
                    self.stats[table_name]['errors'] += 1
                    logger.error(f"❌ 예상치 못한 오류: {original_symbol} - {e}")

            # 변경사항 커밋
            if not self.dry_run and self.stats[table_name]['migrated'] > 0:
                try:
                    db.session.commit()
                    logger.info(f"✅ {table_name} 변경사항 커밋 완료")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"❌ 커밋 실패: {e}")
                    raise

    def run(self):
        """모든 테이블 마이그레이션 실행"""
        logger.info("\n" + "="*60)
        logger.info("🚀 DB 심볼 마이그레이션 시작")
        logger.info("="*60)
        logger.info(f"모드: {'DRY-RUN (읽기 전용)' if self.dry_run else 'EXECUTE (실제 변경)'}")
        logger.info("="*60)

        # 각 테이블 마이그레이션
        self.migrate_table(StrategyPosition, 'StrategyPosition')
        self.migrate_table(Trade, 'Trade')
        self.migrate_table(OpenOrder, 'OpenOrder')
        self.migrate_table(TradeExecution, 'TradeExecution')

        # 최종 통계 출력
        self.print_summary()

    def print_summary(self):
        """마이그레이션 결과 요약 출력"""
        logger.info("\n" + "="*60)
        logger.info("📊 마이그레이션 결과 요약")
        logger.info("="*60)

        total_all = 0
        migrated_all = 0
        skipped_all = 0
        errors_all = 0

        for table_name, stats in self.stats.items():
            logger.info(f"\n{table_name}:")
            logger.info(f"  총 레코드: {stats['total']}")
            logger.info(f"  변환됨: {stats['migrated']}")
            logger.info(f"  스킵됨: {stats['skipped']}")
            logger.info(f"  오류: {stats['errors']}")

            total_all += stats['total']
            migrated_all += stats['migrated']
            skipped_all += stats['skipped']
            errors_all += stats['errors']

        logger.info("\n" + "-"*60)
        logger.info("전체 합계:")
        logger.info(f"  총 레코드: {total_all}")
        logger.info(f"  변환됨: {migrated_all}")
        logger.info(f"  스킵됨: {skipped_all}")
        logger.info(f"  오류: {errors_all}")

        if self.dry_run:
            logger.info("\n" + "="*60)
            logger.info("⚠️  DRY-RUN 모드: 실제 변경사항이 저장되지 않았습니다")
            logger.info("실제 마이그레이션을 수행하려면 --execute 옵션을 사용하세요:")
            logger.info("  python scripts/migrate_symbols_to_standard_format.py --execute")
            logger.info("="*60)
        else:
            logger.info("\n" + "="*60)
            logger.info("✅ 마이그레이션 완료! DB에 변경사항이 저장되었습니다")
            logger.info("="*60)


def main():
    """메인 함수"""
    # 커맨드 라인 인자 파싱
    dry_run = True
    if len(sys.argv) > 1:
        if sys.argv[1] == '--execute':
            dry_run = False
        elif sys.argv[1] != '--dry-run':
            print("사용법: python scripts/migrate_symbols_to_standard_format.py [--dry-run|--execute]")
            sys.exit(1)

    # Flask 앱 생성
    app = create_app()

    # 마이그레이터 실행
    migrator = SymbolMigrator(app, dry_run=dry_run)

    try:
        migrator.run()
    except KeyboardInterrupt:
        logger.warning("\n⚠️  사용자가 마이그레이션을 중단했습니다")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 마이그레이션 실패: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
