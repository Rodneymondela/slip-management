import os
from datetime import date, timedelta, datetime
import uuid
from typing import Any, Optional
from dateutil import parser as date_parser
from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
from sqlalchemy import func

from ...extensions import db, limiter
from ...models.document import Document
from ...models.journal import JournalEntry
from . import uploads_bp
from ...celery_worker import process_ocr

# Allowed upload extensions
ALLOWED = {".png", ".jpg", ".jpeg", ".pdf"}


def _unique_name(filename: str) -> str:
    """Generate a filesystem-safe, unique name using a UUID."""
    ext = os.path.splitext(secure_filename(filename))[1].lower()
    return f"{uuid.uuid4()}{ext}"


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
            # Use the same unique name but with a .jpg extension
            thumb_fname = os.path.splitext(fname)[0] + ".jpg"
            thumb_path = os.path.join(current_app.config["THUMB_FOLDER"], thumb_fname)
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            im.convert("RGB").save(thumb_path, "JPEG", quality=85)
        except Exception as e:
            current_app.logger.warning(f"Thumbnail generation failed for {save_path}: {e}")

    # Create Document record before starting the task
    doc = Document(
        user_id=current_user.id,
        type="receipt",
        file_path=save_path,
        thumbnail_path=thumb_path,
        status="pending",  # New initial status
    )
    db.session.add(doc)
    db.session.commit()

    # Launch the background OCR task
    task = process_ocr.delay(doc.id)

    # Save the task ID to the document
    doc.task_id = task.id
    doc.status = "processing"
    db.session.commit()

    flash("Upload successful! Processing your document now...", "success")
    return redirect(url_for("uploads.processing_status", doc_id=doc.id))


@uploads_bp.route("/processing/<int:doc_id>", methods=["GET"])
@login_required
def processing_status(doc_id: int):
    """
    Page that shows the status of a processing document.
    It can poll for updates or simply show the current state.
    """
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()
    return render_template("uploads/processing.html", doc=doc)


@uploads_bp.route("/task_status/<string:task_id>", methods=["GET"])
@login_required
def task_status(task_id: str):
    """API-like endpoint for fetching a Celery task's status."""
    task = process_ocr.AsyncResult(task_id)
    response_data = {"state": task.state}
    if task.state == "FAILURE":
        response_data["error"] = str(task.info)  # Exception info
    elif task.state == "SUCCESS":
        # If the task is done, find the associated document to get the next URL
        doc = Document.query.filter_by(task_id=task_id, user_id=current_user.id).first()
        if doc:
            response_data["redirect_url"] = url_for("uploads.confirm_get", doc_id=doc.id)
    return response_data


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


def _parse_number(v: Any) -> Optional[float]:
    """
    Robustly converts a string or number to a float, handling common
    European and American-style number formats.
    """
    if v is None or v == "":
        return None

    s = str(v).strip()
    last_dot = s.rfind('.')
    last_comma = s.rfind(',')

    if last_comma > last_dot:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '')

    try:
        return float(s)
    except (ValueError, TypeError):
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

        # Date normalization using dateutil
        entry_date_str = data.get("entry_date") or ""
        if not entry_date_str:
            raise ValueError("Date is required")
        try:
            # dayfirst=True helps resolve ambiguity for formats like 01/02/2024
            entry_date = date_parser.parse(entry_date_str, dayfirst=True).date()
        except (date_parser.ParserError, TypeError):
            raise ValueError(f"Could not understand date: {entry_date_str}")

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
