import os
from sliptrack.app import create_app
from sliptrack.extensions import db

# Create a Flask app instance
app = create_app()

# Ensure the instance folder exists
if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)
    print(f"Instance folder created at: {app.instance_path}")

# Push an application context to make the db object available
with app.app_context():
    print("Creating database tables...")
    # This will create all tables based on the models registered with SQLAlchemy
    db.create_all()
    print("Database tables created successfully.")