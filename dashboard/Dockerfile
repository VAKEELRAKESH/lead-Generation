FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy dashboard source
COPY . .

# The CSV is provided via a mounted volume at runtime, but make sure the
# output directory exists so the app never crashes on a missing folder.
RUN mkdir -p /app/output

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
