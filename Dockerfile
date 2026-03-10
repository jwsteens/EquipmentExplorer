FROM python:3.12-slim

# Install system dependencies (needed for PyMuPDF/OCR)
RUN apt-get update && apt-get install -y \
    libmupdf-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN touch /app/.env

# Copy application code
COPY . .

WORKDIR /app/src


# Create directories for persistent data
RUN mkdir -p /data /documents

# Expose port
EXPOSE 5000

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
