# routes 패키지 

def register_blueprints(app):
    """모든 Blueprint를 애플리케이션에 등록"""
    
    # 기존 Blueprint들
    from .main import bp as main_bp
    from .auth import bp as auth_bp
    from .admin import bp as admin_bp
    
    # 새로 분리된 API Blueprint들
    from .webhook import bp as webhook_bp
    from .accounts import bp as accounts_bp
    from .strategies import bp as strategies_bp
    from .capital import bp as capital_bp
    from .dashboard import bp as dashboard_bp
    from .system import bp as system_bp
    from .positions import bp as positions_bp
    
    # Blueprint 등록
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(strategies_bp)
    app.register_blueprint(capital_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(positions_bp) 