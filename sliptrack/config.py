import os
import shutil


def find_tesseract_cmd():
    """Attempt to find the Tesseract executable in common paths or PATH."""
    # 1. From environment variable
    if os.getenv("TESSERACT_CMD"):
        return os.getenv("TESSERACT_CMD")
    # 2. From shutil.which (checks PATH)
    if shutil.which("tesseract"):
        return "tesseract"
    # 3. Common Windows paths (for convenience)
    if os.name == "nt":
        for path in [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]:
            if os.path.exists(path):
                return path
    # 4. Common Linux paths
    for path in ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]:
        if os.path.exists(path):
            return path
    return None


class BaseConfig:
    TESSERACT_CMD = find_tesseract_cmd()
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///sliptrack.db")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
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
