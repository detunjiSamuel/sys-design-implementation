celery -A project worker --loglevel=info &

uv run manage.py runserver
