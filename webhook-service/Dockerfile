FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    flask==3.0.3 \
    gunicorn==22.0.0 \
    kubernetes==29.0.0

COPY app.py .

ENV PORT=8001
EXPOSE 8001

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8001", "--timeout", "60", "app:app"]
