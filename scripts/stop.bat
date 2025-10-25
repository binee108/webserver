@echo off
chcp 65001 > nul

echo 🛑 트레이딩 시스템 중지 중...

REM Docker Compose로 모든 컨테이너 중지
docker-compose down

echo ✅ 시스템이 중지되었습니다.
echo.
echo 💡 데이터는 보존되었습니다. 다시 시작하려면 'start.bat'를 실행하세요.
echo 🗑️  모든 데이터를 삭제하려면 'docker-compose down -v'를 실행하세요.
echo.
pause