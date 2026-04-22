FROM python:3.9-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.9-slim
LABEL org.opencontainers.image.title="pingluma"
LABEL org.opencontainers.image.description="Iranian messenger global connectivity bot — @ping_luma_bot"

RUN useradd -m -u 1000 pingluma
WORKDIR /app

COPY --from=builder /install /usr/local
COPY ping_luma/ ./ping_luma/
COPY web/       ./web/

USER pingluma

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "from ping_luma.messengers import MESSENGERS; assert len(MESSENGERS)==6; print('ok')"

CMD ["python", "-m", "ping_luma.bot"]