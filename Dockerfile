FROM python:3.8-slim

ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=Bingo.settings

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Default: run gunicorn (add gunicorn to requirements if you use it) or Django runserver.
# Override in compose/CI to run migrate, test, etc.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
