from flask import Flask, render_template
from flask_wtf.csrf import generate_csrf
from .extensions import db, migrate, login_manager, csrf, limiter, celery_app
from .config import get_config
import os
import pytesseract
from datetime import datetime


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    # Set pytesseract command from config
    if app.config.get("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = app.config["TESSERACT_CMD"]
    else:
        app.logger.warning(
            "Tesseract command not found. OCR will fail. "
            "Please install Tesseract and set TESSERACT_CMD in your environment."
        )

    # Configure Celery
    celery_app.conf.update(
        broker_url=app.config["REDIS_URL"],
        result_backend=app.config["REDIS_URL"],
    )
    # Add Flask app context to Celery tasks
    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery_app.Task = ContextTask


    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"            # redirect unauth users to login
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "error"

    @login_manager.user_loader
    def load_user(user_id):
        # Since the user_id is just the primary key, we can use the query function
        from .models.user import User
        return User.query.get(int(user_id))

    csrf.init_app(app)
    limiter.init_app(app)

    # Expose csrf_token() helper in all Jinja templates
    app.jinja_env.globals["csrf_token"] = generate_csrf

    # Make 'now' available in all templates for the footer year
    @app.context_processor
    def inject_now():
        return dict(now=datetime.utcnow)

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
