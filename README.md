# SlipTrack — MVP

A neutral, clean web app to upload receipts/invoices, OCR parse them, and keep a searchable expense journal with VAT (South Africa, 15%).

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Install Tesseract:
# Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
# Add the install directory (e.g., C:\Program Files\Tesseract-OCR) to PATH.
# Verify:
tesseract --version

# Initialize DB
export FLASK_APP=sliptrack.app:create_app
flask db init
flask db migrate -m "init"
flask db upgrade

# Run
flask run
```

## Notes
- Uploads saved to `sliptrack/static/uploads`. Thumbnails in `sliptrack/static/thumbs`.
- OCR adapter is swappable; see `sliptrack/blueprints/uploads/ocr_adapter.py`.
- Tailwind via CDN.
- Basic auth, CSRF, and upload rate limiting included.
