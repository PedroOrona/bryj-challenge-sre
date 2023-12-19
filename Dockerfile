FROM python:3.9.6-slim

WORKDIR /src

COPY src/requirements.txt .

RUN pip install -r requirements.txt

COPY src/metrics.py .
COPY src/.env-docker .env
COPY src/app.py .

ENTRYPOINT ["python", "app.py"]
