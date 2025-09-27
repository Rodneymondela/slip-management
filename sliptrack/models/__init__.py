"""
This file ensures that all models are imported and registered with SQLAlchemy
when the application context is created. This is crucial for tools like
Flask-Migrate to detect all tables correctly.
"""
from .user import User
from .document import Document
from .journal import JournalEntry
from .rule import Rule
from .editlog import EditLog

# You can define a __all__ to control what `from .models import *` imports,
# though it's not strictly necessary for the migration tool to work.
__all__ = ["User", "Document", "JournalEntry", "Rule", "EditLog"]