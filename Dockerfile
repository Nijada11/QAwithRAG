FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    INDEX_DIR=/app/index USAGE_LOG=/app/logs/usage.jsonl

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY data ./data

RUN useradd --system --no-create-home appuser \
    && mkdir -p /app/index /app/logs /app/.cache \
    && chown -R appuser /app
USER appuser

# Download the embedding model and build the index at build time, so a container starts
# ready to answer and needs no network access to Hugging Face at runtime.
RUN python -m src.cli build

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "src.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
