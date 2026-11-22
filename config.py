import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# ── بک‌اند / فرانت ──
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_WS = os.getenv("BACKEND_WS", "ws://localhost:8000")

# ── داده ──
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "3"))
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "فزر")

# ── پلاگین / چارت ──
USER_PLAN = os.getenv("USER_PLAN", "premium")
PLUGIN_SCAN_SEC = float(os.getenv("PLUGIN_SCAN_SEC", "5"))
CANDLE_CLOSE = os.getenv("CANDLE_CLOSE", "final")
PRICE_ADJUST = os.getenv("PRICE_ADJUST", "1") == "1"
INCLUDE_HALTED = os.getenv("INCLUDE_HALTED", "0") == "1"

# ── 9Router ──
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:20128/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_PROXY = os.getenv("LLM_PROXY", "")  # برای 9Router لوکال لازم نیست