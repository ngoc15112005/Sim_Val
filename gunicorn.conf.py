import os

# Gunicorn configuration for Render deployment
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 2
timeout = 120
graceful_timeout = 30
keepalive = 5
