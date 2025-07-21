#!/usr/bin/env python3
"""
데이터베이스 초기화 및 기본 관리자 계정 생성 스크립트
"""

from app import create_app, db
from app.models import User
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