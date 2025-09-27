from flask import Flask, render_template
from flask_wtf.csrf import generate_csrf
from .extensions import db, migrate, login_manager, csrf, limiter
from .config import get_config
import os
import pytesseract


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(get_config(config_name))

    # Ensure pytesseract points to the Windows exe from .env (or common default)
    try:
        cmd = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if cmd and os.path.exists(cmd):
            pytesseract.pytesseract.tesseract_cmd = cmd
    except Exception:
        # Don't crash the app if not set; OCR will just fall back to PATH
        app.logger.warning("Could not set pytesseract.tesseract_cmd", exc_info=True)

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"            # redirect unauth users to login
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "error"
    csrf.init_app(app)
    limiter.init_app(app)

    # Expose csrf_token() helper in all Jinja templates
    app.jinja_env.globals["csrf_token"] = generate_csrf

    # Ensure models are imported so Alembic sees them during 'flask db migrate'
    with app.app_context():
        from . import models  # noqa: F401

    # Blueprints
    from .blueprints.auth.routes import auth_bp
    from .blueprints.uploads.routes import uploads_bp
    from .blueprints.journal.routes import journal_bp
    from .blueprints.reports.routes import reports_bp
    from .blueprints.rules.routes import rules_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(journal_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(rules_bp)

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    return app

# For flask run (PowerShell):
# $env:FLASK_APP = "sliptrack.app:create_app"
# flask run --debug
