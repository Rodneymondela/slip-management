from datetime import datetime
from ..extensions import db


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    type = db.Column(
        db.Enum("receipt", "invoice", name="doc_type"),
        nullable=False,
        default="receipt",
    )
    file_path = db.Column(db.String(512), nullable=False)
    thumbnail_path = db.Column(db.String(512))
    ocr_text = db.Column(db.Text)
    status = db.Column(
        db.Enum(
            "pending",
            "processing",
            "parsed",
            "needs_review",
            "ocr_failed",
            name="doc_status",
        ),
        default="pending",
        nullable=False,
        index=True,
    )
    task_id = db.Column(db.String(36), nullable=True)  # To store Celery task ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
