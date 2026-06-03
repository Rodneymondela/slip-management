from datetime import date
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from ...extensions import db
from ...models.journal import JournalEntry
from ...models.document import Document
from ...models.editlog import EditLog
from . import journal_bp


@journal_bp.route('', methods=['GET'])
@login_required
def list_journal():
    q = JournalEntry.query.filter_by(user_id=current_user.id)
    supplier = request.args.get('supplier')
    if supplier:
        q = q.filter(func.lower(JournalEntry.supplier_name).contains(supplier.lower()))
    q = q.order_by(JournalEntry.entry_date.desc())
    entries = q.limit(100).all()
    return render_template('journal/list.html', entries=entries)


@journal_bp.route('/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def detail(entry_id):
    entry = JournalEntry.query.filter_by(user_id=current_user.id, id=entry_id).first_or_404()

    if request.method == 'POST':
        editable = {
            'supplier_name': (request.form.get('supplier_name') or '').strip() or None,
            'reference_no': request.form.get('reference_no') or None,
            'supplier_vat_number': request.form.get('supplier_vat_number') or None,
            'category': request.form.get('category') or None,
            'payment_method': request.form.get('payment_method') or 'unknown',
            'notes': request.form.get('notes') or None,
        }

        try:
            date_str = request.form.get('entry_date', '')
            editable['entry_date'] = date.fromisoformat(date_str) if date_str else entry.entry_date

            for field in ('subtotal', 'vat_amount', 'total_amount'):
                raw = request.form.get(field, '').strip()
                editable[field] = float(raw) if raw else None
        except (ValueError, TypeError) as exc:
            flash(f'Invalid value: {exc}', 'error')
            return redirect(url_for('journal.detail', entry_id=entry.id))

        for field, new_val in editable.items():
            old_val = getattr(entry, field)
            if str(old_val) != str(new_val):
                db.session.add(EditLog(
                    user_id=current_user.id,
                    journal_entry_id=entry.id,
                    field=field,
                    old_value=str(old_val),
                    new_value=str(new_val),
                ))
                setattr(entry, field, new_val)

        db.session.commit()
        flash('Entry updated', 'success')
        return redirect(url_for('journal.detail', entry_id=entry.id))

    doc = db.session.get(Document, entry.document_id) if entry.document_id else None
    return render_template('journal/detail.html', entry=entry, doc=doc)
