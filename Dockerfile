# wonderful/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Create app directory inside the container
WORKDIR /app

# Copy dependency file first for layer caching
COPY requirements.txt /app/backend/requirements.txt

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -r /app/backend/requirements.txt

# Copy backend source
COPY backend /app/backend

# Run from /app/backend so relative paths like ./data work
WORKDIR /app/backend

EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
