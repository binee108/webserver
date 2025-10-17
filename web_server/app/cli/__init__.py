"""
Flask CLI 명령어 모듈

애플리케이션 관리 및 유지보수를 위한 커스텀 CLI 명령어를 제공합니다.
"""

from .securities import securities

def init_app(app):
    """Flask 앱에 CLI 명령어 그룹 등록"""
    app.cli.add_command(securities)

__all__ = ['init_app', 'securities']
