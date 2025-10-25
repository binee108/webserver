#!/bin/bash

echo "🚀 트레이딩 시스템 시작 중..."

# Docker Compose가 설치되어 있는지 확인
if ! command -v docker-compose &> /dev/null
then
    echo "❌ Docker Compose가 설치되어 있지 않습니다."
    echo "Docker Desktop을 설치하거나 docker-compose를 설치해주세요."
    exit 1
fi

# Docker가 실행 중인지 확인
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker가 실행되고 있지 않습니다."
    echo "Docker Desktop을 시작해주세요."
    exit 1
fi

# 기존 컨테이너 정리 (선택사항)
echo "🧹 기존 컨테이너 정리 중..."
docker-compose down

# PostgreSQL 먼저 시작
echo "🐘 PostgreSQL 데이터베이스 시작 중..."
docker-compose up -d postgres

# PostgreSQL이 준비될 때까지 대기
echo "⏳ PostgreSQL 준비 대기 중..."
for i in {1..30}; do
    if docker-compose exec -T postgres pg_isready -U trader -d trading_system > /dev/null 2>&1; then
        echo "✅ PostgreSQL 준비 완료!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ PostgreSQL 시작 시간 초과"
        exit 1
    fi
    sleep 2
    echo "  대기 중... ($i/30)"
done

# 데이터베이스 마이그레이션 실행
echo "🔧 데이터베이스 마이그레이션 실행 중..."
if docker-compose run --rm app flask db upgrade; then
    echo "✅ 데이터베이스 마이그레이션 완료"
else
    echo "⚠️  마이그레이션 실패 - 새로운 데이터베이스로 초기화 시도 중..."
    docker-compose run --rm app python init_db.py
fi

# 전체 시스템 시작
echo "🏃 Flask 애플리케이션 시작 중..."
docker-compose up -d

# 시작 완료 메시지
echo ""
echo "✅ 트레이딩 시스템이 성공적으로 시작되었습니다!"
echo ""
echo "🌐 웹 인터페이스 (HTTPS): https://localhost"
echo "🔓 웹 인터페이스 (HTTP): http://localhost:5001"
echo "🐘 PostgreSQL: localhost:5432"
echo ""
echo "⚠️  브라우저에서 보안 경고가 나타나면:"
echo "   Chrome: '고급' → '안전하지 않음(권장하지 않음)' → '계속 진행'"
echo "   Safari: '고급' → '계속 진행'"
echo ""
echo "👤 기본 로그인 정보:"
echo "   사용자명: admin"
echo "   비밀번호: admin_test_0623"
echo ""
echo "🛑 시스템 중지: './stop.sh' 또는 'docker-compose down'"
echo "📋 로그 확인: 'docker-compose logs -f'"