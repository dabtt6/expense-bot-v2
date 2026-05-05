FROM python:3.12-slim

LABEL description="Telegram Expense Bot v2.0"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /app/data

RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

ENV DB_PATH=/app/data/expenses.db \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('/app/data/expenses.db')"

CMD ["python", "src/bot.py"]
