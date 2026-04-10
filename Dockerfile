FROM python:3.9-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.9-slim

LABEL org.opencontainers.image.title="ping-luma"
LABEL org.opencontainers.image.description="Bale Messenger connectivity bot"

RUN useradd -m -u 1000 bale
WORKDIR /app

COPY --from=builder /install /usr/local

COPY ping_luma/ ./ping_luma/

USER bale

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "from ping_luma.checker import run_quick_ping; print('ok')"

CMD ["python", "-m", "ping_luma.bot"]