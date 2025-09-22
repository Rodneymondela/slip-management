from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ...extensions import db
from ...models.rule import Rule
from . import rules_bp

@rules_bp.route('', methods=['GET','POST'])
@login_required
def list_rules():
    if request.method == 'POST':
        r = Rule(user_id=current_user.id,
                 supplier_match=request.form.get('supplier_match') or None,
                 text_contains=request.form.get('text_contains') or None,
                 set_category=request.form.get('set_category') or None,
                 set_vat_included=True if request.form.get('set_vat_included')=='on' else None,
                 priority=int(request.form.get('priority') or 100))
        db.session.add(r); db.session.commit()
        flash('Rule added', 'success')
    rules = Rule.query.filter_by(user_id=current_user.id).order_by(Rule.priority.asc()).all()
    return render_template('rules/list.html', rules=rules)
