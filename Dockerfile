FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files (bust cache on every deploy)
ARG CACHEBUST=1
COPY backend/ ./backend/
COPY bot/ ./bot/
COPY start.py .

# Start via Python launcher (replaces bash script for reliability)
CMD ["python", "start.py"]
