#!/bin/sh
set -e

echo "⏳ Waiting for database..."
sleep 3

echo "🔄 Applying migrations..."
python manage.py migrate --noinput

echo "📦 Collecting static files..."
python manage.py collectstatic --noinput

echo "🚀 Starting server..."
exec "$@"