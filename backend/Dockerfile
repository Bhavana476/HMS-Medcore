FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home medcore && chown -R medcore /app
USER medcore
EXPOSE 10000
# Migrations run on start so a fresh database is usable immediately.
CMD ["sh","-c","python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn medcore.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 3"]