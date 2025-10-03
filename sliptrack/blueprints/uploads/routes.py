import os
from datetime import date, timedelta
import uuid
from typing import Any, Optional
from dateutil import parser as date_parser
from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
from sqlalchemy import func

from ...extensions import db, limiter
from ...models.document import Document
from ...models.journal import JournalEntry
from . import uploads_bp
from ...celery_worker import process_ocr
from .helpers import user_owns_document, serve_secure_file
from .ocr_adapter import OcrAdapter

ALLOWED = {".png", ".jpg", ".jpeg", ".pdf"}


def _unique_name(filename: str) -> str:
    """Generate a filesystem-safe, unique name using a UUID."""
    ext = os.path.splitext(secure_filename(filename))[1].lower()
    return f"{uuid.uuid4()}{ext}"


@uploads_bp.route("", methods=["GET", "POST"])
@limiter.limit("20/minute")
@login_required
def upload():
    if request.method == "GET":
        return render_template("uploads/upload.html")

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

    fname = _unique_name(f.filename)
    relative_path = os.path.join("uploads", fname)
    full_path = os.path.join(current_app.instance_path, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    f.save(full_path)

    relative_thumb_path = None
    if ext != ".pdf":
        try:
            im = Image.open(full_path)
            im.thumbnail((480, 480))
            thumb_fname = os.path.splitext(fname)[0] + ".jpg"
            relative_thumb_path = os.path.join("thumbs", thumb_fname)
            full_thumb_path = os.path.join(
                current_app.instance_path, relative_thumb_path
            )
            os.makedirs(os.path.dirname(full_thumb_path), exist_ok=True)
            im.convert("RGB").save(full_thumb_path, "JPEG", quality=85)
        except Exception as e:
            current_app.logger.warning(
                f"Thumbnail generation failed for {full_path}: {e}"
            )

    doc = Document(
        user_id=current_user.id,
        type="receipt",
        file_path=relative_path,
        thumbnail_path=relative_thumb_path,
        status="pending",
    )
    db.session.add(doc)
    db.session.commit()

    task = process_ocr.delay(doc.id)
    doc.task_id = task.id
    doc.status = "processing"
    db.session.commit()

    flash("Upload successful! Processing your document now...", "success")
    return redirect(url_for("uploads.processing_status", doc_id=doc.id))


@uploads_bp.route("/data/<path:file_path>")
@login_required
def serve_data(file_path):
    """Securely serves a user's uploaded file or thumbnail."""
    return serve_secure_file(file_path, current_user.id)


@uploads_bp.route("/processing/<int:doc_id>", methods=["GET"])
@login_required
@user_owns_document
def processing_status(doc_id: int, doc: Document):
    """Shows the status of a processing document."""
    return render_template("uploads/processing.html", doc=doc)


@uploads_bp.route("/doc_status/<int:doc_id>", methods=["GET"])
@login_required
@user_owns_document
def doc_status(doc_id: int, doc: Document):
    """
    API-like endpoint for fetching a document's processing status.
    This is polled by the frontend to provide user feedback.
    """
    if doc.status in ["parsed", "needs_review"]:
        return {
            "doc_status": doc.status,
            "redirect_url": url_for("uploads.confirm_get", doc_id=doc.id),
        }
    elif doc.status == "ocr_failed":
        return {"doc_status": doc.status, "error": "OCR processing failed."}
    else:
        # Status is 'pending' or 'processing'
        return {"doc_status": doc.status}


@uploads_bp.route("/confirm/<int:doc_id>", methods=["GET"])
@login_required
@user_owns_document
def confirm_get(doc_id: int, doc: Document):
    """Show the editable confirmation form for a previously uploaded Document."""
    if doc.status not in ["parsed", "needs_review"]:
        flash(f"Document is currently '{doc.status}' and cannot be confirmed.", "info")
        return redirect(url_for("uploads.processing_status", doc_id=doc.id))

    defaults = {
        "supplier_name": "",
        "supplier_vat_number": "",
        "entry_date": date.today().isoformat(),
        "reference_no": "",
        "subtotal": "",
        "vat_rate": current_app.config.get("VAT_RATE", 0.15),
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
            # If there's no OCR text, start with a blank slate
            parsed = defaults
    except Exception as e:
        current_app.logger.warning(f"Parse failed for Document {doc.id}: {e}")
        flash("Could not parse details - please fill in manually.", "error")
        parsed = defaults

    # Ensure parsed data is merged with defaults for any missing keys
    parsed = {**defaults, **{k: v for k, v in parsed.items() if v is not None}}

    return render_template("uploads/confirm.html", parsed=parsed, doc=doc)


def _parse_number(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    s = str(v).strip().replace(" ", "")
    last_dot = s.rfind(".")
    last_comma = s.rfind(",")
    if last_comma > last_dot:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _find_duplicates(user_id, supplier, total_amount, entry_date):
    if not supplier or total_amount is None or entry_date is None:
        return []
    start = entry_date - timedelta(days=3)
    end = entry_date + timedelta(days=3)
    return (
        JournalEntry.query.filter(JournalEntry.user_id == user_id)
        .filter(JournalEntry.entry_date.between(start, end))
        .filter(func.lower(JournalEntry.supplier_name) == func.lower(supplier.strip()))
        .filter(func.abs(JournalEntry.total_amount - total_amount) <= 0.02)
        .order_by(JournalEntry.entry_date.desc())
        .all()
    )


@uploads_bp.route("/confirm", methods=["POST"])
@login_required
def confirm():
    data = request.form
    try:
        total = _parse_number(data.get("total_amount"))
        subtotal = _parse_number(data.get("subtotal"))
        vat_rate = _parse_number(data.get("vat_rate", "0.15"))
        vat_amount = _parse_number(data.get("vat_amount"))

        vat_included = data.get("vat_included") in ("on", "true", "1", "yes")
        if vat_included and total is not None and (subtotal is None or vat_amount is None):
            base = total / (1 + float(vat_rate))
            subtotal = round(base, 2)
            vat_amount = round(total - base, 2)

        entry_date_str = data.get("entry_date") or ""
        if not entry_date_str:
            raise ValueError("Date is required")
        entry_date = date_parser.parse(entry_date_str, dayfirst=True).date()

        if total is not None and subtotal is not None and vat_amount is not None:
            if abs((subtotal + vat_amount) - total) > 0.02:
                raise ValueError("Subtotal + VAT must match Total (within 2c)")
        if entry_date > (date.today() + timedelta(days=3)):
            raise ValueError("Date cannot be in the future")

        if not data.get("override_duplicate"):
            dups = _find_duplicates(
                user_id=current_user.id,
                supplier=(data.get("supplier_name") or "").strip(),
                total_amount=total,
                entry_date=entry_date,
            )
            if dups:
                return render_template(
                    "uploads/duplicate_warning.html",
                    duplicates=dups,
                    post_fields=data,
                )

        entry = JournalEntry(
            user_id=current_user.id,
            document_id=int(data["document_id"]) if data.get("document_id") else None,
            entry_date=entry_date,
            supplier_name=data.get("supplier_name"),
            supplier_vat_number=data.get("supplier_vat_number"),
            reference_no=data.get("reference_no"),
            subtotal=subtotal,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            total_amount=total,
            currency=data.get("currency", "ZAR"),
            payment_method=data.get("payment_method", "unknown"),
            category=data.get("category"),
            notes=data.get("notes"),
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