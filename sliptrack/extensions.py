import os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from celery import Celery

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery(
    __name__,
    include=["sliptrack.celery_worker"],
    broker=_redis_url,
    backend=_redis_url,
)