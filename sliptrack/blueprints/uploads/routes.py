import os
from datetime import date, timedelta, datetime
from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
from sqlalchemy import func

from ...extensions import db, limiter
from ...models.document import Document
from ...models.journal import JournalEntry
from . import uploads_bp
from .ocr_adapter import OcrAdapter

# Allowed upload extensions
ALLOWED = {".png", ".jpg", ".jpeg", ".pdf"}


def _unique_name(filename: str) -> str:
    """Generate a filesystem-safe, unique name for the uploaded file."""
    name, ext = os.path.splitext(secure_filename(filename))
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    return f"{name}_{ts}{ext.lower()}"


@uploads_bp.route("", methods=["GET", "POST"])
@limiter.limit("20/minute")
@login_required
def upload():
    # GET -> render upload form
    if request.method == "GET":
        return render_template("uploads/upload.html")

    # POST -> handle file
    if "file" not in request.files:
        flash("No file part in request", "error")
        return redirect(url_for("uploads.upload"))

    f = request.files["file"]
    if not f or f.filename == "":
        flash("No file selected", "error")
        return redirect(url_for("uploads.upload"))

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        flash("Unsupported file type (use PNG/JPG/PDF)", "error")
        return redirect(url_for("uploads.upload"))

    # Save original
    fname = _unique_name(f.filename)
    save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], fname)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    f.save(save_path)

    # Thumbnail (skip for PDFs)
    thumb_path = None
    if ext != ".pdf":
        try:
            im = Image.open(save_path)
            im.thumbnail((480, 480))
            thumb_path = os.path.join(current_app.config["THUMB_FOLDER"], fname + ".jpg")
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            im.convert("RGB").save(thumb_path, "JPEG", quality=85)
        except Exception as e:
            current_app.logger.warning(f"Thumbnail generation failed for {save_path}: {e}")

    # OCR best-effort; store raw text on Document, parse on GET confirm
    raw_text = ""
    if ext != ".pdf":  # skip OCR for PDFs for now
        try:
            adapter = OcrAdapter()
            preprocessed = adapter.preprocess(save_path)
            raw_text = adapter.extract_text(preprocessed)
        except Exception as e:
            current_app.logger.exception(f"OCR failed for {save_path}: {e}")
            flash("OCR failed - please fill in details manually.", "error")
    else:
        current_app.logger.info(f"Skipping OCR for PDF: {save_path}")

    # Create Document and commit so we can redirect to a stable GET URL
    doc = Document(
        user_id=current_user.id,
        type="receipt",
        file_path=save_path,
        thumbnail_path=thumb_path,
        ocr_text=raw_text,
        status="parsed" if raw_text else "needs_review",
    )
    db.session.add(doc)
    db.session.commit()

    return redirect(url_for("uploads.confirm_get", doc_id=doc.id))


@uploads_bp.route("/confirm/<int:doc_id>", methods=["GET"])
@login_required
def confirm_get(doc_id: int):
    """Show the editable confirmation form for a previously uploaded Document."""
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()

    defaults = {
        "supplier_name": "",
        "supplier_vat_number": "",
        "entry_date": date.today().isoformat(),
        "reference_no": "",
        "subtotal": "",
        "vat_rate": 0.15,
        "vat_amount": "",
        "total_amount": "",
        "payment_method": "unknown",
        "category": "",
        "notes": "Manual entry",
    }

    parsed = {}
    try:
        if doc.ocr_text:
            parsed = OcrAdapter().parse_fields(doc.ocr_text)
        else:
            parsed = dict(defaults)
    except Exception as e:
        current_app.logger.warning(f"Parse failed for Document {doc.id}: {e}")
        flash("Could not parse details - please fill in manually.", "error")
        parsed = dict(defaults)

    if not isinstance(parsed, dict):
        parsed = dict(defaults)

    return render_template("uploads/confirm.html", parsed=parsed, doc=doc)


def _parse_number(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _find_duplicates(user_id, supplier, total_amount, entry_date):
    """Return possible duplicates: same supplier, total within 2c, and date within +/- 3 days."""
    if not supplier or total_amount is None or entry_date is None:
        return []

    start = entry_date - timedelta(days=3)
    end = entry_date + timedelta(days=3)

    q = (
        JournalEntry.query
        .filter(JournalEntry.user_id == user_id)
        .filter(JournalEntry.entry_date >= start, JournalEntry.entry_date <= end)
        .filter(func.lower(JournalEntry.supplier_name) == func.lower(supplier.strip()))
        .filter(func.abs((JournalEntry.total_amount or 0) - total_amount) <= 0.02)
        .order_by(JournalEntry.entry_date.desc())
    )
    return q.all()


@uploads_bp.route("/confirm", methods=["POST"])
@login_required
def confirm():
    """
    Persist the confirmed/edited fields to a JournalEntry.
    - Accept comma or dot decimals
    - If VAT included is checked and Total is provided, derive Subtotal & VAT (15% default)
    - Validate math within 2c tolerance and disallow future dates (> +3 days)
    - Duplicate warning: supplier + total + date +/- 3 days, with Save anyway option
    """
    data = request.form

    try:
        # Numbers (comma-safe)
        total = _parse_number(data.get("total_amount"))
        subtotal = _parse_number(data.get("subtotal"))
        vat_rate = _parse_number(data.get("vat_rate")) if data.get("vat_rate") else 0.15
        if vat_rate is None:
            vat_rate = 0.15
        vat_amount = _parse_number(data.get("vat_amount"))

        # If VAT included and only total provided, derive values
        vat_included = data.get("vat_included") in ("on", "true", "1", "yes")
        if vat_included and total is not None and (subtotal is None or vat_amount is None):
            base = total / (1 + float(vat_rate))
            subtotal = round(base, 2)
            vat_amount = round(total - base, 2)

        # Date normalization
        entry_date_str = data.get("entry_date") or ""
        entry_date = None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"):
            try:
                entry_date = datetime.strptime(entry_date_str, fmt).date()
                break
            except Exception:
                continue
        if entry_date is None:
            entry_date = datetime.fromisoformat(entry_date_str).date()

        # Validations
        if total is not None and total < 0:
            raise ValueError("Total amount cannot be negative")
        if subtotal is not None and subtotal < 0:
            raise ValueError("Subtotal cannot be negative")
        if vat_amount is not None and vat_amount < 0:
            raise ValueError("VAT amount cannot be negative")
        if subtotal is not None and vat_amount is not None and total is not None:
            if abs((subtotal + vat_amount) - total) > 0.02:
                raise ValueError("Subtotal + VAT must match Total (within 2c)")
        if entry_date > (date.today() + timedelta(days=3)):
            raise ValueError("Date cannot be in the future")

        # Duplicate detection (unless user confirmed override)
        if not data.get("override_duplicate"):
            dups = _find_duplicates(
                user_id=current_user.id,
                supplier=(data.get("supplier_name") or "").strip(),
                total_amount=total,
                entry_date=entry_date,
            )
            if dups:
                carry = {
                    "document_id": data.get("document_id") or "",
                    "entry_date": entry_date.isoformat(),
                    "supplier_name": data.get("supplier_name") or "",
                    "supplier_vat_number": data.get("supplier_vat_number") or "",
                    "reference_no": data.get("reference_no") or "",
                    "subtotal": "" if subtotal is None else f"{subtotal}",
                    "vat_rate": "" if vat_rate is None else f"{vat_rate}",
                    "vat_amount": "" if vat_amount is None else f"{vat_amount}",
                    "total_amount": "" if total is None else f"{total}",
                    "currency": data.get("currency") or "ZAR",
                    "payment_method": data.get("payment_method") or "unknown",
                    "category": data.get("category") or "",
                    "notes": data.get("notes") or "",
                    "vat_included": "on" if vat_included else "",
                }
                return render_template(
                    "uploads/duplicate_warning.html",
                    duplicates=dups,
                    post_fields=carry,
                )

        # No duplicates or user chose to override -> save
        entry = JournalEntry(
            user_id=current_user.id,
            document_id=int(data.get("document_id")) if data.get("document_id") else None,
            entry_date=entry_date,
            supplier_name=data.get("supplier_name"),
            supplier_vat_number=data.get("supplier_vat_number") or None,
            reference_no=data.get("reference_no") or None,
            subtotal=subtotal,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            total_amount=total,
            currency=data.get("currency") or "ZAR",
            payment_method=data.get("payment_method") or "unknown",
            category=data.get("category") or None,
            notes=data.get("notes") or None,
        )

        db.session.add(entry)
        db.session.commit()
        flash("Saved to journal", "success")
        return redirect(url_for("journal.list_journal"))

    except Exception as e:
        current_app.logger.exception(f"Confirm/save failed: {e}")
        flash(f"Error saving: {e}", "error")
        doc_id = request.form.get("document_id")
        if doc_id:
            return redirect(url_for("uploads.confirm_get", doc_id=doc_id))
        return redirect(url_for("uploads.upload"))
