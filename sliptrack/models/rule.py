from ..extensions import db

class Rule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    supplier_match = db.Column(db.String(128))
    text_contains = db.Column(db.String(128))
    set_category = db.Column(db.String(64))
    set_vat_included = db.Column(db.Boolean)
    priority = db.Column(db.Integer, default=100)
