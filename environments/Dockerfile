FROM python:3.11.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QT_QPA_PLATFORM=offscreen MPLCONFIGDIR=/tmp/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libegl1 libopengl0 libxkbcommon0 libdbus-1-3 libgl1 libxcb-cursor0 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
COPY extras.lock /tmp/extras.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/extras.lock
COPY backtest_repair /app/backtest_repair
ENV PYTHONPATH=/app
RUN useradd --uid 10001 --create-home worker
USER worker
WORKDIR /tmp
CMD ["python", "-m", "backtest_repair.stream_worker"]
