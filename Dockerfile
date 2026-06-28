FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app/ ./app/

# Copy skill scripts (referenced by tools.py via relative paths)
COPY .claude/local-marketplace/plugins/ ./.claude/local-marketplace/plugins/

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Binds 0.0.0.0 so the port is reachable from outside the container. Host
# exposure is controlled by the compose port mapping (127.0.0.1 loopback only).
# SECURITY: `docker run -p 8000:8000` publishes on ALL host interfaces with no
# auth — unsafe. Use `docker compose up` (loopback publish) or set APP_API_KEY.
# The app refuses to start unauthenticated off-loopback unless ALLOW_NO_AUTH=1.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
