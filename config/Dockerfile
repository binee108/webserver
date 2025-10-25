FROM python:3.10-slim

WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY web_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 웹서버 애플리케이션 코드 복사
COPY web_server/ ./web_server/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Flask-Migrate 작업 디렉토리를 web_server로 설정
WORKDIR /app/web_server

# 필요한 디렉토리 생성
RUN mkdir -p logs certs

# 환경 변수 설정 (경로 참조를 위해)
ENV PYTHONPATH=/app:/app/web_server

# Flask 앱 실행 (scripts와 config는 볼륨으로 마운트됨)
EXPOSE 443 5001

CMD ["python", "/app/scripts/app.py"]