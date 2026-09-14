FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    mlflow==2.11.0 \
    scikit-learn \
    boto3 \
    psycopg2-binary

COPY train.py .

CMD ["python", "train.py"]
