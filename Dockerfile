FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ── Runtime ──────────────────────────────────────────────
FROM python:3.12-slim

RUN groupadd -r turing && useradd -r -g turing -s /bin/false turing
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8005

USER turing

CMD ["uvicorn", "app.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8005", \
     "--workers", "2", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
