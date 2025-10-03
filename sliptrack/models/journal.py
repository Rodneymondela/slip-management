from datetime import datetime
from ..extensions import db

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    entry_date = db.Column(db.Date, nullable=False, index=True)
    supplier_name = db.Column(db.String(128))
    supplier_vat_number = db.Column(db.String(32))
    reference_no = db.Column(db.String(64))
    subtotal = db.Column(db.Numeric(12,2))
    vat_rate = db.Column(db.Numeric(4,4), default=0.15)
    vat_amount = db.Column(db.Numeric(12,2))
    total_amount = db.Column(db.Numeric(12,2))
    currency = db.Column(db.String(3), default='ZAR')
    payment_method = db.Column(db.Enum('cash','card','eft','unknown', name='payment_method'), default='unknown')
    category = db.Column(db.String(64))
    notes = db.Column(db.Text)
    reconciled = db.Column(db.Boolean, default=False)
    reconciliation_ref = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
