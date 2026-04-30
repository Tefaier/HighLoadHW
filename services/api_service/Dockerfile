FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/api_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy common code
COPY common/ ./common/

# Copy service code
COPY services/api_service/ ./

EXPOSE 8001

CMD ["python", "main.py"]
