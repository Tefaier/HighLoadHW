FROM docker.io/library/python:3.11-slim

WORKDIR /app


COPY common/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# RUN pip install --no-cache-dir \
#     sqlalchemy>=2.0.0 \
#     psycopg2-binary>=2.9.0 \
#     sqlalchemy-utils>=0.41.0

COPY common/ ./common/
# COPY services/db_init/entrypoint.sh /entrypoint.sh
# RUN chmod +x /entrypoint.sh

COPY services/db_init/ ./

# ENV PYTHONPATH=/app

CMD ["python","main.py"]