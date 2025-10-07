"""
Make TradeExecution.strategy_account_id nullable

목적:
- 계좌 연결 해제 시 과거 거래 기록 보존
- StrategyAccount 삭제 후에도 TradeExecution 레코드 유지

변경사항:
- trade_executions.strategy_account_id: NOT NULL → NULL

작성일: 2025-10-07
"""

from sqlalchemy import text


def upgrade(engine):
    """
    TradeExecution.strategy_account_id를 nullable로 변경

    주의사항:
    - 이 변경은 기존 데이터에 영향을 주지 않습니다
    - 계좌 연결 해제 시 strategy_account_id가 NULL로 설정됩니다
    """
    with engine.connect() as conn:
        # PostgreSQL: ALTER COLUMN DROP NOT NULL
        conn.execute(text(
            'ALTER TABLE trade_executions ALTER COLUMN strategy_account_id DROP NOT NULL;'
        ))
        conn.commit()
        print('✅ trade_executions.strategy_account_id를 nullable로 변경했습니다.')


def downgrade(engine):
    """
    TradeExecution.strategy_account_id를 다시 NOT NULL로 변경

    주의사항:
    - NULL 값이 있는 경우 실패합니다
    - 롤백 전 NULL 값을 먼저 처리해야 합니다
    """
    with engine.connect() as conn:
        # NULL 값 체크
        result = conn.execute(text(
            "SELECT COUNT(*) FROM trade_executions WHERE strategy_account_id IS NULL"
        ))
        null_count = result.scalar()

        if null_count > 0:
            raise Exception(
                f"❌ NOT NULL 제약을 설정할 수 없습니다: "
                f"{null_count}개의 레코드가 NULL strategy_account_id를 가지고 있습니다.\n"
                f"롤백하려면 먼저 이 레코드들을 삭제하거나 strategy_account_id를 설정해야 합니다."
            )

        # PostgreSQL: ALTER COLUMN SET NOT NULL
        conn.execute(text(
            'ALTER TABLE trade_executions ALTER COLUMN strategy_account_id SET NOT NULL;'
        ))
        conn.commit()
        print('✅ trade_executions.strategy_account_id를 NOT NULL로 복원했습니다.')


if __name__ == '__main__':
    """
    독립 실행 예시:

    from app import create_app, db
    app = create_app()
    with app.app_context():
        upgrade(db.engine)
    """
    print("이 스크립트는 Flask 애플리케이션 컨텍스트에서 실행되어야 합니다.")
    print("사용 예시:")
    print("  from app import create_app, db")
    print("  app = create_app()")
    print("  with app.app_context():")
    print("      from migrations.20251007_153047_make_trade_execution_strategy_account_nullable import upgrade")
    print("      upgrade(db.engine)")
