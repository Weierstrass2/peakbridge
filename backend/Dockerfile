# PeakBridge EV 피크쉐이빙 백엔드 — 프로덕션 Docker 이미지
# 멀티스테이지 빌드로 이미지 크기 최소화

FROM python:3.10-slim AS builder

WORKDIR /build

# 빌드 의존성 (bcrypt, cryptography 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.10-slim AS runtime

WORKDIR /app

# PostgreSQL 클라이언트 라이브러리
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 비루트 사용자로 실행 (보안)
RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

USER appuser

EXPOSE 8000

# 헬스체크 — Kubernetes / Docker Compose에서 사용
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
