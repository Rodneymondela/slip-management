# SlipTrack — Enhanced

A neutral, clean web app to upload receipts/invoices, OCR parse them, and keep a searchable expense journal with VAT (South Africa, 15%). This version includes asynchronous processing for scalability and support for PDF documents.

## Quickstart

### 1. System Dependencies

Before installing Python packages, you need to install a few system-level dependencies.

**Tesseract (for OCR):**
- **Windows:** Download from [Tesseract at UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). Add the install directory (e.g., `C:\Program Files\Tesseract-OCR`) to your system's PATH.
- **macOS (Homebrew):** `brew install tesseract`
- **Debian/Ubuntu:** `sudo apt-get install tesseract-ocr`
- **Verify:** `tesseract --version`

**Poppler (for PDF processing):**
- **Windows:** Download the latest binaries from [the Poppler for Windows project](http://blog.alivate.com.au/poppler-windows/). Add the `bin/` directory to your system's PATH.
- **macOS (Homebrew):** `brew install poppler`
- **Debian/Ubuntu:** `sudo apt-get install poppler-utils`
- **Verify:** `pdftotext -v`

**Redis (for background task queue):**
- **macOS (Homebrew):** `brew install redis` and then `brew services start redis`
- **Debian/Ubuntu:** `sudo apt-get install redis-server`
- **Docker (Recommended for ease of use):** `docker run -d -p 6379:6379 redis`
- **Verify:** `redis-cli ping` (should return `PONG`)

### 2. Python Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install Python packages
pip install -r requirements.txt

# Set the Flask app environment variable
export FLASK_APP=sliptrack.app:create_app
# On Windows, use: set FLASK_APP=sliptrack.app:create_app

# Initialize the database
flask db init  # Only if you've never run it before
flask db migrate -m "Initial migration"
flask db upgrade
```

### 3. Running the Application

You need to run two processes in separate terminals: the Flask web server and the Celery background worker.

**Terminal 1: Run the Celery Worker**
```bash
celery -A sliptrack.celery_worker.celery_app worker --loglevel=info
```

**Terminal 2: Run the Flask App**
```bash
flask run
```

The application will be available at `http://127.0.0.1:5000`.

## Notes
- Uploads are saved to `sliptrack/static/uploads`, with thumbnails in `sliptrack/static/thumbs`.
- OCR and PDF processing are handled asynchronously by a Celery worker.
- Tailwind CSS is included via a CDN for simple styling.
- The app includes basic authentication, CSRF protection, and upload rate limiting.