FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for compiling packages and PostgreSQL connectivity
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Create directories for persistent files and models
RUN mkdir -p /app/uploads /app/faiss_index

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
