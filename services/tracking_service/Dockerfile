FROM python:3.11-slim

WORKDIR /app

COPY services/tracking_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY services/tracking_service/ ./

EXPOSE 8003

CMD ["python", "main.py"]
