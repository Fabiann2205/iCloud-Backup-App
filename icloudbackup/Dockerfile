ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:latest
FROM $BUILD_FROM

# Metadata
LABEL \
    io.hass.name="iCloud Backup App" \
    io.hass.description="Upload your backups to iCloud" \
    io.hass.type="addon" \
    io.hass.version="2026.02.0" \
    maintainer="Fabiann2205 <fabiann2205@icloud.com>" \
    org.opencontainers.image.source="https://github.com/Fabiann2205/iCloud-Backup-App"

# Python environment
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY run.sh uploader.py ./
COPY frontend/ ./frontend/

# Setup
RUN chmod +x run.sh

# Health check
HEALTHCHECK --interval=10s --timeout=3s --start-period=1s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:5000/health || exit 1

CMD ["./run.sh"]
