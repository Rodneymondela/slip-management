import pytest
from flask import flash
from flask_login import login_user
from sliptrack.app import create_app
from sliptrack.extensions import db
from sliptrack.models.user import User
from sliptrack.models.journal import JournalEntry
from datetime import date

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app, client):
    return app.test_cli_runner()

def test_duplicate_journal_entry(client, app):
    with app.app_context():
        user = User(email='test@test.com', password_hash='test')
        db.session.add(user)
        db.session.commit()

        entry_data = {
            'user_id': user.id,
            'entry_date': date(2025, 9, 22),
            'supplier_name': 'Test Supplier',
            'total_amount': 100.00,
        }
        entry = JournalEntry(**entry_data)
        db.session.add(entry)
        db.session.commit()

        with client.session_transaction() as session:
            session['_user_id'] = user.id

        # Try to add the same entry again
        response = client.post('/upload/confirm', data={
            'document_id': '',
            'entry_date': '2025-09-22',
            'supplier_name': 'Test Supplier',
            'total_amount': '100.00',
            'subtotal': '85.00',
            'vat_amount': '15.00',
            'vat_rate': '0.15',
            'currency': 'ZAR',
            'payment_method': 'card',
            'category': 'test',
            'notes': 'test notes'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'This looks like a duplicate entry.' in response.data
