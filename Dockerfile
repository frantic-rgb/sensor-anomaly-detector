FROM python:3.11-slim

# Create non-root user
RUN useradd --create-home appuser

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY static/ ./static/

# Hand off to non-root user
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/status')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
