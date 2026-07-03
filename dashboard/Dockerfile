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
COPY requirements.txt ./requirements.txt
COPY dashboard/requirements.txt ./dashboard_requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r dashboard_requirements.txt

# Install Chromium browser for Playwright
RUN python -m playwright install chromium

# Copy all files from root context
COPY . .

# Create output and logs directories
RUN mkdir -p /app/output /app/logs

EXPOSE 8000

# Run from root so sys.path resolves correctly
CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
