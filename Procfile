web: flask db upgrade && gunicorn 'sliptrack.app:create_app()' --bind 0.0.0.0:$PORT --workers 2 --timeout 120
worker: celery -A sliptrack.celery_worker.celery_app worker --loglevel=info -P solo
