"""
증권 관련 CLI 명령어

사용 예시:
    flask securities refresh-tokens
    flask securities check-status
"""

import click
from flask import current_app
from flask.cli import with_appcontext


@click.group()
def securities():
    """증권 관련 명령어 그룹"""
    pass


@securities.command('refresh-tokens')
@with_appcontext
def refresh_tokens():
    """
    증권 OAuth 토큰 수동 갱신

    모든 증권 계좌의 OAuth 토큰을 즉시 갱신합니다.
    Background Job과 동일한 로직을 사용하여 안전하게 처리됩니다.

    사용 예시:
        flask securities refresh-tokens
    """
    from app.jobs.securities_token_refresh import SecuritiesTokenRefreshJob

    click.echo("🔄 증권 토큰 수동 갱신 시작...")

    result = SecuritiesTokenRefreshJob.run(current_app._get_current_object())

    click.echo(f"\n📊 갱신 결과:")
    click.echo(f"  - 성공: {result['success']}")
    click.echo(f"  - 실패: {result['failed']}")
    click.echo(f"  - 전체: {result['total']}")
    click.echo(f"  - 시각: {result['timestamp']}")

    if result['failed_accounts']:
        click.echo(f"\n❌ 실패한 계좌:")
        for acc in result['failed_accounts']:
            click.echo(
                f"  - account_id={acc['account_id']} ({acc['account_name']}): {acc['error']}"
            )

    click.echo("\n✅ 완료")


@securities.command('check-status')
@with_appcontext
def check_status():
    """
    증권 계좌 토큰 상태 확인

    모든 증권 계좌의 토큰 만료 시간과 갱신 필요 여부를 확인합니다.

    사용 예시:
        flask securities check-status
    """
    from app.models import Account, SecuritiesToken
    from app import db
    from datetime import datetime

    click.echo("📋 증권 계좌 토큰 상태 확인...\n")

    # 증권 계좌 조회
    securities_accounts = Account.query.filter(
        Account.account_type.like('SECURITIES_%')
    ).all()

    if not securities_accounts:
        click.echo("⚠️ 증권 계좌가 없습니다.")
        return

    click.echo(f"총 {len(securities_accounts)}개 증권 계좌:\n")

    for account in securities_accounts:
        token_cache = SecuritiesToken.query.filter_by(account_id=account.id).first()

        click.echo(f"📌 계좌 {account.id} ({account.name})")
        click.echo(f"   - 거래소: {account.exchange}")
        click.echo(f"   - 계좌 타입: {account.account_type}")

        if not token_cache:
            click.echo(f"   ⚠️ 토큰 없음 (미발급)")
        else:
            now = datetime.utcnow()
            time_until_expiry = token_cache.expires_at - now
            time_since_refresh = now - token_cache.last_refreshed_at

            click.echo(f"   - 만료 시간: {token_cache.expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            click.echo(f"   - 남은 시간: {time_until_expiry}")
            click.echo(f"   - 마지막 갱신: {token_cache.last_refreshed_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            click.echo(f"   - 갱신 경과: {time_since_refresh}")

            if token_cache.is_expired():
                click.echo(f"   ❌ 상태: 만료됨 (재발급 필요)")
            elif token_cache.needs_refresh():
                click.echo(f"   ⚠️ 상태: 갱신 권장 (6시간 경과)")
            else:
                click.echo(f"   ✅ 상태: 정상")

        click.echo("")

    click.echo("✅ 상태 확인 완료")
