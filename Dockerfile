FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_DEBUG=0 \
    FLASK_APP=app:create_app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt -c requirements.lock

COPY . .
RUN mkdir -p /app/instance \
    && adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:5000 --workers ${WEB_CONCURRENCY:-2} --threads ${WEB_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-60} app:app"]
