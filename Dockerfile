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

# Copy project files
# The .dockerignore ensures no __pycache__, .db, .env files sneak in
COPY backend/ ./backend/
COPY bot/ ./bot/
COPY start.py .

# Force Railway to never use stale image — version tag changes on every meaningful deploy
LABEL app.version="2.5.0-2026-02-23" \
      app.description="ADM Platform - no demo data"

# Delete any stale .db files that might have leaked into the image
RUN find /app -name "*.db" -delete 2>/dev/null; \
    find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; \
    echo "Clean build verified at $(date -u)"

# Start via Python launcher (replaces bash script for reliability)
CMD ["python", "start.py"]
