from flask_login import login_user
from sliptrack.models.user import User
from sliptrack.models.journal import JournalEntry
from datetime import date

def test_duplicate_journal_entry(client, db_session):
    """
    Test that the duplicate detection logic correctly flags a new entry
    that matches an existing one.
    """
    # 1. Create a user and an initial journal entry
    user = User(email="test@example.com", password_hash="supersecret")
    db_session.add(user)
    db_session.commit()

    entry_data = {
        "user_id": user.id,
        "entry_date": date(2025, 9, 22),
        "supplier_name": "Test Supplier",
        "total_amount": 100.00,
        "subtotal": 85.00,
        "vat_amount": 15.00,
    }
    existing_entry = JournalEntry(**entry_data)
    db_session.add(existing_entry)
    db_session.commit()

    # 2. Log the user in to establish a session
    # We need to be in a request context to use login_user
    with client.application.test_request_context():
        login_user(user)

    # 3. Post a new entry with the same key details
    form_data = {
        "document_id": "",
        "entry_date": "22-09-2025",  # Use a different but valid date format
        "supplier_name": " Test Supplier ",  # Add whitespace to test stripping
        "total_amount": "100.00",
        "subtotal": "85.00",
        "vat_amount": "15.00",
        "vat_rate": "0.15",
    }

    response = client.post("/upload/confirm", data=form_data, follow_redirects=True)

    # 4. Assert that the duplicate warning page is shown
    assert response.status_code == 200
    # Check for a unique string from the duplicate warning template
    assert b"Duplicate Warning" in response.data
    assert b"Test Supplier" in response.data
    assert b"100.00" in response.data