"""
ChartSession: یک چارت زنده = سهم + تایم‌فریم + اندیکاتورهای فعال + مشترکین WebSocket

- refresh():        دیتا می‌گیرد → کندل امروز را merge می‌کند → اندیکاتورها را حساب می‌کند → سیگنال‌های جدید
- payload_init():   کل چارت (کندل، حجم، پنل‌ها، خطوط، باکس‌ها، مارکرها)   → وقتی ساختار عوض شده
- payload_update(): فقط کندل آخر + آخرین نقطه‌ی هر خط + مارکرها            → هر تیک
- summaries():      خلاصه‌ی ساختاریافته‌ی هر اندیکاتور برای LLM
"""
import json
import math
import time
import hashlib
import logging
from datetime import datetime
from backend.data import candle_store
from backend.data.tsetmc import build_intraday_candles  # اگر اینجاست؛ وگرنه همان build_intraday خودت
import numpy as np
import pandas as pd

from config import CANDLE_CLOSE, PRICE_ADJUST, INCLUDE_HALTED
from backend.indicators.registry import get_indicator

log = logging.getLogger("session")

TZ_OFFSET = 12600  # +03:30 → نمایش ساعت تهران در Lightweight Charts
PALETTE = ["#26a69a", "#ef5350", "#42a5f5", "#ffa726", "#ab47bc", "#26c6da", "#8d6e63", "#78909c"]
CANDLE_COLS = ["open", "high", "low", "close", "last", "final", "volume", "value"]


# ───────────────────────── helpers ─────────────────────────
def ts(idx) -> int:
    return int(pd.Timestamp(idx).timestamp()) + TZ_OFFSET


def _num(x, default=0.0) -> float:
    try:
        v = float(x)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default


def _pos(x) -> bool:
    return _num(x) > 0


def clean(o, time_as="ts"):
    """NaN / numpy / Timestamp را JSON-safe می‌کند"""
    if isinstance(o, dict):
        return {str(k): clean(v, time_as) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(x, time_as) for x in o]
    if isinstance(o, (pd.Timestamp, datetime)):
        return ts(o) if time_as == "ts" else str(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else float(o)
    return o


def style_for(sig: str, styles: dict, base: str) -> dict:
    """استایل مارکر: اول signal_styles اندیکاتور، وگرنه حدس از روی نام سیگنال"""
    if sig in styles:
        return styles[sig]
    bull = any(k in sig for k in ("buy", "bull", "up", "demand", "long"))
    return {"position": "belowBar" if bull else "aboveBar",
            "color": "#26a69a" if bull else "#ef5350",
            "shape": ("arrowUp" if bull else "arrowDown") if sig in ("buy", "sell") else "circle",
            "text": base if sig in ("buy", "sell") else sig}


def build_intraday(trades: pd.DataFrame, tf: str) -> pd.DataFrame:
    """کندل درون‌روزی از ریز معاملات امروز"""
    if trades is None or trades.empty:
        return pd.DataFrame()
    t = trades.set_index("time")
    o = t["price"].resample(tf).ohlc()
    o["volume"] = t["qty"].resample(tf).sum()
    o = o.dropna(subset=["close"])
    o["last"] = o["close"]
    o["final"] = o["close"]
    o["value"] = o["volume"] * o["close"]
    return o


# ───────────────────────── session ─────────────────────────
class ChartSession:
    def __init__(self, sid: str, src, ins_code: str, symbol: str, timeframe: str = "D"):
        self.sid, self.src = sid, src
        self.ins, self.symbol, self.timeframe = ins_code, symbol, timeframe

        self.indicators: dict[str, dict] = {}   # iid -> {"name", "params", "obj"}
        self._n = 0

        self.df: pd.DataFrame | None = None
        self.results: dict[str, dict] = {}
        self.meta: dict = {}
        self.info: dict = {}
        self.live: dict = {}

        self.markers: list[dict] = []
        self._marker_keys: set = set()
        self._shape_hash: str | None = None

        self._hist: pd.DataFrame | None = None
        self._hist_at = 0.0
        self._saved_at: dict[str, float] = {}     # آخرین ذخیره‌ی آرشیو، برای هر تایم‌فریم جدا

        self.dirty = True                        # True → payload_init باید فرستاده شود
        self.subscribers: set = set()

    # ── پیکربندی ──────────────────────────────────────────
    def add_indicator(self, name: str, params: dict | None = None) -> str:
        cls = get_indicator(name)
        self._n += 1
        iid = f"{name}#{self._n}"
        self.indicators[iid] = {"name": name, "params": {**cls.inputs, **(params or {})}, "obj": cls()}
        self.dirty = True
        return iid

    def remove_indicator(self, iid: str) -> bool:
        ok = self.indicators.pop(iid, None) is not None
        self.results.pop(iid, None)
        self._marker_keys = {k for k in self._marker_keys if k[0] != iid}
        self.dirty = True
        return ok

    def refresh_classes(self):
        """بعد از hot-reload پلاگین‌ها: نمونه‌ها را با کلاس جدید بازسازی می‌کند"""
        for ind in self.indicators.values():
            try:
                cls = get_indicator(ind["name"])
            except KeyError:
                continue
            if type(ind["obj"]) is not cls:
                ind["obj"] = cls()
                ind["params"] = {**cls.inputs, **ind["params"]}
                self.dirty = True

    def set_symbol(self, ins_code: str, symbol: str):
        self.ins, self.symbol = ins_code, symbol
        self._reset()

    def set_timeframe(self, tf: str):
        self.timeframe = tf
        self._reset()

    def _reset(self):
        self._hist, self._hist_at = None, 0.0
        self.df, self.results, self.info, self.live = None, {}, {}, {}
        self.markers, self._marker_keys, self._shape_hash = [], set(), None
        for ind in self.indicators.values():          # کش داخلی اندیکاتورهای heavy پاک شود
            ind["obj"] = type(ind["obj"])()
        self.dirty = True

    def config(self) -> dict:
        return {"session_id": self.sid, "ins_code": self.ins, "symbol": self.symbol, "timeframe": self.timeframe,
                "indicators": [{"id": k, "name": v["name"], "params": v["params"],
                                "premium": bool(getattr(type(v["obj"]), "premium", False))}
                               for k, v in self.indicators.items()]}

    # ── داده ──────────────────────────────────────────────
    async def refresh(self, confirmed: bool = False) -> list[dict]:
        """دیتا → کندل‌ها → اندیکاتورها → سیگنال‌های جدید روی کندل آخر"""
        if not self.info:
            try:
                self.info = await self.src.info(self.ins)
            except Exception:
                self.info = {}
        self.live = await self.src.price(self.ins) or {}

        if self.timeframe == "D":
            if self._hist is None or time.time() - self._hist_at > 300:
                self._hist = await self.src.daily_history(
                    self.ins, adjust=PRICE_ADJUST, include_halted=INCLUDE_HALTED, close_source=CANDLE_CLOSE)
                self._hist_at = time.time()
            df = self._merge_live(self._hist, self.live)
        else:
                    
            # 1) آرشیو روزهای قبل
            hist = candle_store.load(self.ins, self.timeframe, limit=3000)
            # 2) ریز معاملات امروز → کندل
            try:
                trades = await self.src.trades(self.ins)
            except Exception:
                trades = pd.DataFrame()
            today = build_intraday(trades, self.timeframe) if not trades.empty else pd.DataFrame()
            # 3) ادغام
            df = candle_store.merge_history_with_today(hist, today)
            # 4) در حین/بعد بازار، امروز را روی دیسک هم بنویس (برای هر تایم‌فریم، هر ~۵ دقیقه)
            if not today.empty and time.time() - self._saved_at.get(self.timeframe, 0.0) > 300:
                candle_store.save(self.ins, self.timeframe, today)
                self._saved_at[self.timeframe] = time.time()
            # 5) خطای موقت TSETMC (نه آرشیو، نه ریزمعامله) نباید چارت را خالی کند
            if today.empty and hist.empty and self.df is not None and not self.df.empty:
                log.warning("no intraday data for %s %s — keeping previous chart", self.symbol, self.timeframe)
                return []

        # 6) نتیجه را روی سشن بگذار (کندل‌ها + هدر + اندیکاتورها)
        self.df = df
        if df is None or df.empty:
            self.results, self.meta = {}, {}
            self.dirty = True
            return []

        for iid, ind in self.indicators.items():      # اندیکاتورها روی کندل‌های تازه
            try:
                self.results[iid] = ind["obj"].calc(self.df, ind["params"], confirmed=confirmed)
            except Exception as e:
                log.warning("indicator %s failed on %s: %s", iid, self.symbol, e)
                self.results[iid] = {"plots": {}, "signals": {},
                                     "summary": {"error": f"{type(e).__name__}: {e}"}}
        for iid in [k for k in self.results if k not in self.indicators]:
            self.results.pop(iid, None)

        self._update_meta()                          # هدر: آخرین / پایانی / دیروز + درصدها
        return self._rebuild_markers()               # مارکرها + سیگنال‌های تازه‌ی کندل آخر

    def _merge_live(self, hist: pd.DataFrame, live: dict) -> pd.DataFrame:
        """کندل امروز را از قیمت زنده می‌سازد/آپدیت می‌کند (فقط اگر معامله شده باشد)"""
        df = hist.copy() if hist is not None else pd.DataFrame(columns=CANDLE_COLS)
        if not live or not _pos(live.get("last")) or not _pos(live.get("volume")):
            return df

        last = _num(live["last"])
        final = _num(live.get("final")) or last
        close_today = final if CANDLE_CLOSE == "final" else last
        opn = _num(live.get("open")) or last
        hi = max(_num(live.get("high")) or last, opn, close_today)
        lo = min(_num(live.get("low")) or last, opn, close_today)
        row = {"open": opn, "high": hi, "low": lo, "close": close_today, "last": last, "final": final,
               "volume": _num(live.get("volume")), "value": _num(live.get("value"))}
        for c in df.columns:
            row.setdefault(c, np.nan)
        row = {c: row[c] for c in df.columns} if len(df.columns) else row

        today = pd.Timestamp(datetime.now().date())
        srv_date = str(live.get("date") or "")
        if len(df) and pd.Timestamp(df.index[-1]).normalize() == today:
            df.iloc[-1] = pd.Series(row)[df.columns]
        elif srv_date == today.strftime("%Y%m%d"):
            df.loc[today] = pd.Series(row)
        return df

    def _update_meta(self):
        c = self.df.close
        last = _num(self.live.get("last")) or float(c.iloc[-1])
        final = _num(self.live.get("final")) or last
        y = _num(self.live.get("yesterday"))
        if not y:                                        # قبل از معامله/روز تعطیل: کندل آخر همان دیروز است
            has_today = pd.Timestamp(self.df.index[-1]).date() == datetime.now().date()
            y = float(c.iloc[-2]) if (has_today and len(c) > 1) else float(c.iloc[-1])
        p = lambda v: (v / y - 1) * 100 if y else 0.0
        self.meta = {"symbol": self.symbol, "timeframe": self.timeframe,
                     "last": last, "final": final, "yesterday": y,
                     "last_pct": p(last), "final_pct": p(final),
                     "change_pct": p(final if CANDLE_CLOSE == "final" else last),
                     "volume": _num(self.live.get("volume")), "value": _num(self.live.get("value")),
                     "count": self.live.get("count"), "queue": None,
                     "updated": datetime.now().strftime("%H:%M:%S")}
        up, dn = _num(self.info.get("limit_up")), _num(self.info.get("limit_down"))
        if up and abs(last - up) < 1:
            self.meta["queue"] = "buy"
        elif dn and abs(last - dn) < 1:
            self.meta["queue"] = "sell"

    def _rebuild_markers(self) -> list[dict]:
        """همه‌ی مارکرها را از نو می‌سازد؛ سیگنال‌های جدیدِ کندل آخر را برمی‌گرداند"""
        markers, new = [], []
        last_idx = self.df.index[-1]
        for iid, r in self.results.items():
            cls = type(self.indicators[iid]["obj"])
            styles = getattr(cls, "signal_styles", {}) or {}
            base = iid.split("#")[0]
            for sig, series in (r.get("signals") or {}).items():
                if series is None:
                    continue
                st = style_for(sig, styles, base)
                fired = series[series.fillna(False).astype(bool)].index
                for idx in fired:
                    t = ts(idx)
                    markers.append({"time": t, "position": st["position"], "color": st["color"],
                                    "shape": st["shape"], "text": st.get("text", sig)})
                    key = (iid, sig, t)
                    if key not in self._marker_keys:
                        self._marker_keys.add(key)
                        if idx == last_idx:
                            new.append({"indicator": iid, "signal": sig,
                                        "price": float(self.df.close.iloc[-1]), "time": str(idx)})
        self.markers = sorted(markers, key=lambda m: m["time"])
        return new

    # ── payload ───────────────────────────────────────────
    @staticmethod
    def _series(s: pd.Series) -> list[dict]:
        return [{"time": ts(i), "value": float(v)} for i, v in s.items() if pd.notna(v)]

    def _candles(self, tail: int | None = None):
        d = self.df if tail is None else self.df.tail(tail)
        c = [{"time": ts(i), "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close)}
             for i, r in d.iterrows()]
        v = [{"time": ts(i), "value": float(_num(r.volume)),
              "color": "rgba(38,166,154,.5)" if r.close >= r.open else "rgba(239,83,80,.5)"}
             for i, r in d.iterrows()]
        return c, v

    def payload_init(self) -> dict:
        if self.df is None:
            return {"type": "init", "meta": self.meta, "config": self.config(),
                    "candles": [], "volume": [], "panes": [], "markers": []}
        candles, volume = self._candles()
        panes = []
        for iid, ind in self.indicators.items():
            r = self.results.get(iid, {})
            cls = type(ind["obj"])
            colors = getattr(cls, "colors", {}) or {}
            panes.append({
                "id": iid, "overlay": bool(getattr(cls, "overlay", False)),
                "levels": clean(r.get("levels") or []),
                "series": [{"name": n, "color": colors.get(n, PALETTE[k % len(PALETTE)]), "data": self._series(s)}
                           for k, (n, s) in enumerate((r.get("plots") or {}).items()) if s is not None],
                "zones": clean(r.get("zones") or []),
                "lines": clean(r.get("lines") or []),
            })
        return {"type": "init", "meta": self.meta, "config": self.config(),
                "candles": candles, "volume": volume, "panes": panes, "markers": self.markers}

    def payload_update(self, new_signals: list[dict]) -> dict:
        if self.df is None:
            return {"type": "update", "meta": self.meta}
        c, v = self._candles(tail=1)
        points = {}
        for iid, r in self.results.items():
            pts = {}
            for n, s in (r.get("plots") or {}).items():
                if s is None or not len(s) or pd.isna(s.iloc[-1]):
                    pts[n] = None
                else:
                    pts[n] = {"time": ts(s.index[-1]), "value": float(s.iloc[-1])}
            points[iid] = pts
        return {"type": "update", "meta": self.meta, "candle": c[0], "volume": v[0],
                "points": points, "markers": self.markers, "signals": new_signals}

    def summaries(self) -> dict:
        return {iid: clean(r.get("summary") or {}, time_as="str") for iid, r in self.results.items()}

    async def broadcast(self, msg: dict):
        data = json.dumps(clean(msg), ensure_ascii=False)
        dead = set()
        for ws in list(self.subscribers):
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self.subscribers -= dead