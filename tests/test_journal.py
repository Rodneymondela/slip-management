from werkzeug.security import generate_password_hash
from sliptrack.models.user import User
from sliptrack.models.journal import JournalEntry
from datetime import date


def _login(client, email, password):
    return client.post('/auth/login', data={'email': email, 'password': password}, follow_redirects=True)


def test_duplicate_journal_entry(client, db_session):
    """
    Duplicate detection should render the warning page when a new entry
    matches an existing one (same supplier, total within 2c, date within 3 days).
    """
    user = User(email="test@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    existing_entry = JournalEntry(
        user_id=user.id,
        entry_date=date(2025, 9, 22),
        supplier_name="Test Supplier",
        total_amount=100.00,
        subtotal=85.00,
        vat_amount=15.00,
    )
    db_session.add(existing_entry)
    db_session.commit()

    _login(client, "test@example.com", "password123")

    form_data = {
        "document_id": "",
        "entry_date": "22-09-2025",
        "supplier_name": " Test Supplier ",
        "total_amount": "100.00",
        "subtotal": "85.00",
        "vat_amount": "15.00",
        "vat_rate": "0.15",
    }

    response = client.post("/upload/confirm", data=form_data, follow_redirects=True)

    assert response.status_code == 200
    assert b"Duplicate Warning" in response.data
    assert b"Test Supplier" in response.data
    assert b"100.00" in response.data
