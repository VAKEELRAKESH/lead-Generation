FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip cache purge || true && pip install --no-cache-dir -r requirements.txt

# Install Chromium browser for Playwright
RUN python -m playwright install chromium

# Create output directory so the app can write CSVs
RUN mkdir -p /app/output /app/logs

# Copy project source
COPY . .

# Mount point for retrieving output files from host
VOLUME ["/app/output"]

CMD ["python", "main.py"]