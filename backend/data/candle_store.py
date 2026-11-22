"""ذخیره/بارگذاری کندل‌های درون‌روزی. هر روز بعد از بازار، trades همان روز آرشیو می‌شود."""
from pathlib import Path
import pandas as pd

STORE = Path(__file__).resolve().parents[2] / "data" / "intraday"
STORE.mkdir(parents=True, exist_ok=True)


def _path(ins: str, tf: str) -> Path:
    safe = "".join(c if c.isalnum() else "_" for c in str(ins))
    return STORE / f"{safe}_{tf}.parquet"


def load(ins: str, tf: str, limit: int = 2000) -> pd.DataFrame:
    p = _path(ins, tf)
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(p)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        return df.sort_index().tail(limit)
    except Exception:
        return pd.DataFrame()


def save(ins: str, tf: str, df: pd.DataFrame):
    if df is None or df.empty:
        return
    p = _path(ins, tf)
    old = load(ins, tf, limit=50_000)
    cols = ["open", "high", "low", "close", "volume"]
    chunk = df[cols].copy()
    if old.empty:
        merged = chunk
    else:
        merged = pd.concat([old[cols], chunk]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
    merged.to_parquet(p)


def merge_history_with_today(hist: pd.DataFrame, today: pd.DataFrame) -> pd.DataFrame:
    if hist is None or hist.empty:
        return today if today is not None else pd.DataFrame()
    if today is None or today.empty:
        return hist
    cols = [c for c in ["open", "high", "low", "close", "volume", "final", "last", "value"] if c in hist.columns or c in today.columns]
    h, t = hist.copy(), today.copy()
    for c in cols:
        if c not in h: h[c] = 0.0
        if c not in t: t[c] = 0.0
    # اگر کندل امروز در آرشیو هم هست، نسخهٔ زنده‌تر (today) اولویت دارد
    out = pd.concat([h[cols], t[cols]]).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    if "final" not in out: out["final"] = out["close"]
    if "last" not in out: out["last"] = out["close"]
    if "value" not in out: out["value"] = out["volume"] * out["close"]
    return out