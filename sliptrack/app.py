from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from .extensions import db, migrate, login_manager, csrf, limiter
from .config import get_config

def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(get_config(config_name))

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

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

# For flask run: FLASK_APP=sliptrack.app:create_app
