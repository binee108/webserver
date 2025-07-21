#!/usr/bin/env python3
"""
트레이딩 자동화 시스템 메인 실행 파일
"""
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # 개발 환경에서만 debug=True
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5001)),
        debug=debug_mode
    ) 