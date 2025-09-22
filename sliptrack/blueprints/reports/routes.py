from datetime import date
from flask import render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func, extract
from ...extensions import db
from ...models.journal import JournalEntry
from . import reports_bp

@reports_bp.route('/monthly', methods=['GET'])
@login_required
def monthly():
    month = request.args.get('month')
    if not month:
        month = date.today().strftime('%Y-%m')
    y, m = map(int, month.split('-'))
    q = JournalEntry.query.filter(JournalEntry.user_id==current_user.id,
                                  extract('year', JournalEntry.entry_date)==y,
                                  extract('month', JournalEntry.entry_date)==m)
    total = sum((e.total_amount or 0) for e in q)
    vat_total = sum((e.vat_amount or 0) for e in q)
    # per-category
    cat_totals = {}
    for e in q:
        cat = e.category or 'Uncategorized'
        cat_totals[cat] = cat_totals.get(cat, 0) + float(e.total_amount or 0)
    return render_template('reports/monthly.html', month=month, total=total, vat_total=vat_total, cat_totals=cat_totals)
