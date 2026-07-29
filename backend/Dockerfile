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
COPY models/best/ ./models/best/
COPY models/bid_policy.json ./models/bid_policy.json
COPY static/ ./static/
COPY alembic/ ./alembic/
COPY alembic.ini .

# 런타임 data 파일 — 작은 것만 (ev2gym/kpx_processed 등 수십 MB 재생 데이터는 제외).
# appuser 소유로 복사해야 smp-api inject 캐시(kpx_smp_api_cache.json)를 쓸 수 있다.
COPY --chown=appuser:appuser data/kpx_smp.csv data/kpx_calibration.json \
     data/jeju_facts.json data/jeju_curtailment.csv data/jeju_plusdr.csv ./data/
COPY --chown=appuser:appuser data/models/ ./data/models/

USER appuser

EXPOSE 8000

# 헬스체크 — Kubernetes / Docker Compose에서 사용
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
