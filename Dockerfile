FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE=/data/tracker.sqlite3

WORKDIR /app

RUN addgroup --system tracker && adduser --system --ingroup tracker tracker

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY whatsapp_tracker ./whatsapp_tracker
RUN mkdir -p /data && chown -R tracker:tracker /data /app

USER tracker
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-", "whatsapp_tracker:create_app()"]

