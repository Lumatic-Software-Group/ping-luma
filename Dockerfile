FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
LABEL org.opencontainers.image.title="pingluma"
LABEL org.opencontainers.image.description="Iranian messenger global connectivity bot — @ping_luma_bot"

RUN useradd -m -u 1000 pingluma
WORKDIR /app

COPY --from=builder /install /usr/local
COPY ping_luma/ ./ping_luma/
COPY web/       ./web/

USER pingluma

# Many PaaS hosts require EXPOSE + a listening port (Back4app, etc.). The bot
# starts a tiny HTTP server on PORT (default 8080) for / and /health — see paas_health.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; p=os.getenv('PORT','8080'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=5)"

CMD ["python", "-m", "ping_luma.bot"]
