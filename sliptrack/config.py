import os

class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///sliptrack.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "sliptrack/static/uploads")
    THUMB_FOLDER = os.environ.get("THUMB_FOLDER", "sliptrack/static/thumbs")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_SAMESITE = "Lax"
    VAT_RATE = float(os.environ.get("VAT_RATE", 0.15))

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False

class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

def get_config(name=None):
    if name is None:
        name = os.environ.get("FLASK_ENV", "development").lower()
    if name.startswith("prod"):
        return ProductionConfig
    return DevelopmentConfig
