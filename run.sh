#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# .env را اگر نبود از نمونه بساز
[ -f .env ] || cp .env.example .env

# بک‌اند
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACK_PID=$!

# با Ctrl+C هر دو بسته شوند
trap "kill $BACK_PID 2>/dev/null" EXIT

# صبر تا بک‌اند بالا بیاید
for i in {1..20}; do
  curl -s http://localhost:8000/health >/dev/null && break
  sleep 0.5
done

# فرانت
streamlit run frontend/app.py --server.port 8501 --server.headless true