#!/usr/bin/env python3
"""
데이터베이스 초기화 및 기본 관리자 계정 생성 스크립트
"""

import sys
import os

# 경로 설정을 더 안정적으로 처리
def setup_python_path():
    """Python 경로 설정"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    web_server_path = os.path.join(script_dir, '..', 'web_server')
    config_path = os.path.join(script_dir, '..', 'config')
    
    if os.path.exists(web_server_path):
        sys.path.insert(0, os.path.abspath(web_server_path))
    else:
        print(f"Error: web_server path not found at {web_server_path}")
        sys.exit(1)
    
    if os.path.exists(config_path):
        sys.path.insert(0, os.path.abspath(config_path))

# 경로 설정 실행
setup_python_path()

try:
    from app import create_app, db
    from app.models import User
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Current Python path:")
    for path in sys.path:
        print(f"  - {path}")
    sys.exit(1)
from werkzeug.security import generate_password_hash

def init_database():
    """데이터베이스 초기화 및 기본 데이터 생성"""
    app = create_app()
    
    with app.app_context():
        # 데이터베이스 테이블 생성
        print("데이터베이스 테이블 생성 중...")
        db.create_all()
        print("✅ 데이터베이스 테이블 생성 완료")
        
        # 기본 관리자 계정 생성 (이미 존재하면 스킵)
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                password_hash=generate_password_hash('admin123'),
                is_approved=True,
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ 관리자 계정 생성 완료")
            print("   - 사용자명: admin")
            print("   - 비밀번호: admin123")
            print("   - 이메일: admin@example.com")
        else:
            print("ℹ️  관리자 계정이 이미 존재합니다.")
        
        print("\n🎉 데이터베이스 초기화 완료!")
        print("서버를 실행하고 http://localhost:5001 에서 로그인하세요.")

if __name__ == "__main__":
    init_database() 