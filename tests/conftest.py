import pytest
from sliptrack.app import create_app
from sliptrack.extensions import db

@pytest.fixture(scope='session')
def app():
    """Session-wide test `Flask` application."""
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "SERVER_NAME": "localhost",
        "BCRYPT_LOG_ROUNDS": 4, # Speed up password hashing in tests
    })

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app, clean_db):
    """Yields a database session for a test, wrapped in an app context."""
    with app.app_context():
        yield db.session


@pytest.fixture(scope='function')
def clean_db(app):
    """Ensures the database is clean before each test runs."""
    with app.app_context():
        # A fast way to clear all data from all tables
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()