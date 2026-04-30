FROM python:3.11-slim

WORKDIR /app

COPY services/order_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY services/order_service/ ./

EXPOSE 8002

CMD ["python", "main.py"]
