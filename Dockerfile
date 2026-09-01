FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts ./scripts
COPY src ./src
COPY db ./db

ENV PYTHONPATH=/app/src
ENV APP_HOST=0.0.0.0
ENV APP_PORT=5057
ENV PYTHONUNBUFFERED=1

EXPOSE 5057

CMD ["python", "scripts/serve.py", "--host", "0.0.0.0", "--port", "5057"]
