from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, and_
from ...extensions import db
from ...models.journal import JournalEntry
from ...models.document import Document
from . import journal_bp

@journal_bp.route('', methods=['GET'])
@login_required
def list_journal():
    q = JournalEntry.query.filter_by(user_id=current_user.id)
    supplier = request.args.get('supplier')
    if supplier:
        q = q.filter(func.lower(JournalEntry.supplier_name).contains(supplier.lower()))
    # TODO: more filters (date range, category, payment, amount range, VAT claimed)
    q = q.order_by(JournalEntry.entry_date.desc())
    entries = q.limit(100).all()
    return render_template('journal/list.html', entries=entries)

@journal_bp.route('/<int:entry_id>', methods=['GET','POST'])
@login_required
def detail(entry_id):
    entry = JournalEntry.query.filter_by(user_id=current_user.id, id=entry_id).first_or_404()
    if request.method == 'POST':
        entry.supplier_name = request.form.get('supplier_name') or entry.supplier_name
        db.session.commit()
        flash('Updated', 'success')
        return redirect(url_for('journal.detail', entry_id=entry.id))
    doc = Document.query.get(entry.document_id) if entry.document_id else None
    return render_template('journal/detail.html', entry=entry, doc=doc)
