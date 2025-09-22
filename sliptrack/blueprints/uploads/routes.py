import os
from datetime import date, timedelta, datetime
from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from ...extensions import db, limiter
from ...models.document import Document
from ...models.journal import JournalEntry
from . import uploads_bp
from .ocr_adapter import OcrAdapter
from PIL import Image

ALLOWED = {'.png','.jpg','.jpeg','.pdf'}

def _unique_name(filename):
    name, ext = os.path.splitext(secure_filename(filename))
    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    return f"{name}_{ts}{ext.lower()}"

@uploads_bp.route('', methods=['GET','POST'])
@limiter.limit("20/minute")
@login_required
def upload():
    if request.method == 'POST' and 'file' in request.files:
        f = request.files['file']
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED:
            flash('Unsupported file type', 'error')
            return redirect(url_for('uploads.upload'))
        fname = _unique_name(f.filename)
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        f.save(save_path)

        # Thumbnail
        try:
            im = Image.open(save_path)
            im.thumbnail((480,480))
            thumb_path = os.path.join(current_app.config['THUMB_FOLDER'], fname + '.jpg')
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            im.convert('RGB').save(thumb_path, 'JPEG', quality=85)
        except Exception:
            thumb_path = None

        adapter = OcrAdapter()
        pre = adapter.preprocess(save_path)
        raw = adapter.extract_text(pre)
        parsed = adapter.parse_fields(raw)

        doc = Document(user_id=current_user.id, type='receipt', file_path=save_path, thumbnail_path=thumb_path, ocr_text=raw, status='parsed')
        db.session.add(doc); db.session.flush()

        return render_template('uploads/confirm.html', parsed=parsed, doc=doc)

    return render_template('uploads/upload.html')

@uploads_bp.route('/confirm', methods=['POST'])
@login_required
def confirm():
    data = request.form
    try:
        entry = JournalEntry(
            user_id=current_user.id,
            document_id=int(data.get('document_id')) if data.get('document_id') else None,
            entry_date=datetime.fromisoformat(data.get('entry_date')).date(),
            supplier_name=data.get('supplier_name'),
            supplier_vat_number=data.get('supplier_vat_number') or None,
            reference_no=data.get('reference_no') or None,
            subtotal=float(data.get('subtotal')) if data.get('subtotal') else None,
            vat_rate=float(data.get('vat_rate')) if data.get('vat_rate') else 0.15,
            vat_amount=float(data.get('vat_amount')) if data.get('vat_amount') else None,
            total_amount=float(data.get('total_amount')) if data.get('total_amount') else None,
            currency=data.get('currency') or 'ZAR',
            payment_method=data.get('payment_method') or 'unknown',
            category=data.get('category') or None,
            notes=data.get('notes') or None,
        )
        # Basic validations
        if entry.total_amount is not None and entry.total_amount < 0:
            raise ValueError("Total amount cannot be negative")
        # TODO: duplicate detection & rules application
        db.session.add(entry); db.session.commit()
        flash('Saved to journal', 'success')
        return redirect(url_for('journal.list_journal'))
    except Exception as e:
        flash(f'Error saving: {e}', 'error')
        return redirect(url_for('uploads.upload'))
