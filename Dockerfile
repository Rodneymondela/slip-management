FROM python:3.12-slim

# System dependencies: Tesseract OCR, Poppler (PDF), OpenCV libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn psycopg2-binary

COPY . .

# Flask needs this to locate the app factory
ENV FLASK_APP=sliptrack.app:create_app

# Run DB migrations then start Gunicorn (web service)
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120 --log-level debug --access-logfile - --error-logfile -"]
