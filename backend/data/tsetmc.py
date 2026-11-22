"""
کلاینت API رایگان TSETMC (cdn.tsetmc.com) — بدون کلید، آپدیت هر ۲–۳ ثانیه.
- از IP ایران اجرا شود
- نام فیلدها در FIELDS متمرکز است؛ اگر TSETMC چیزی را عوض کرد فقط همین‌جا اصلاح کن
"""
import asyncio
import logging
from datetime import datetime

import httpx
import pandas as pd

log = logging.getLogger("tsetmc")
BASE = "https://cdn.tsetmc.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Referer": "https://main.tsetmc.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa-IR,fa;q=0.9",
}

# نگاشت نام فیلدهای TSETMC → نام داخلی
FIELDS = {
    "price": {"last": "pDrCotVal", "final": "pClosing", "open": "priceFirst", "high": "priceMax", "low": "priceMin",
              "yesterday": "priceYesterday", "volume": "qTotTran5J", "value": "qTotCap", "count": "zTotTran",
              "date": "dEven", "time": "hEven"},
    "daily": {"open": "priceFirst", "high": "priceMax", "low": "priceMin", "close": "pDrCotVal", "final": "pClosing",
              "yesterday": "priceYesterday", "volume": "qTotTran5J", "value": "qTotCap", "count": "zTotTran", "date": "dEven"},
    "client": {"buy_real_vol": "buy_I_Volume", "buy_legal_vol": "buy_N_Volume", "sell_real_vol": "sell_I_Volume",
               "sell_legal_vol": "sell_N_Volume", "buy_real_cnt": "buy_CountI", "buy_legal_cnt": "buy_CountN",
               "sell_real_cnt": "sell_CountI", "sell_legal_cnt": "sell_CountN", "date": "recDate"},
    "orderbook": {"row": "number", "bid_count": "zOrdMeDem", "bid_vol": "qTitMeDem", "bid": "pMeDem",
                  "ask": "pMeOf", "ask_vol": "qTitMeOf", "ask_count": "zOrdMeOf"},
    "watch": {"symbol": "lva", "name": "lvc", "last": "pdv", "final": "pcl", "open": "pf", "high": "pmx", "low": "pmn",
              "yesterday": "py", "volume": "qtj", "value": "qtc", "count": "ztt", "time": "hEven",
              "limit_up": "pMax", "limit_down": "pMin", "base_volume": "bv", "eps": "eps"},
}


def fa2ar(s: str) -> str:
    return (s or "").replace("ی", "ي").replace("ک", "ك")


def ar2fa(s: str) -> str:
    return (s or "").replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").strip()


def _map(d: dict, m: dict) -> dict:
    return {k: d.get(v) for k, v in m.items()}


def _num(x, default=0.0):
    try:
        return float(x) if x is not None else default
    except (TypeError, ValueError):
        return default
    
    
import numpy as np

def adjust_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    تعدیل به روش قیمت مرجع: هر جا «قیمت دیروزِ» امروز با «پایانیِ» روز قبل فرق دارد
    (افزایش سرمایه، سود نقدی، ...)، همهٔ قیمت‌های قبل از آن روز در نسبت ضرب می‌شوند.
    همان روشی که چارت مفید/رهاورد/pytse-client استفاده می‌کنند.
    """
    if df.empty or "yesterday" not in df:
        return df
    fin, yest = df["final"].to_numpy(float), df["yesterday"].to_numpy(float)
    n = len(df); ratios = np.ones(n)
    for i in range(1, n):
        if fin[i - 1] > 0 and yest[i] > 0 and abs(yest[i] - fin[i - 1]) / fin[i - 1] > 0.001:
            ratios[i] = yest[i] / fin[i - 1]
    f = np.cumprod(ratios[::-1])[::-1]          # f[j] = prod ratios[j..n-1]
    factor = np.append(f[1:], 1.0)              # عامل هر روز = حاصل‌ضرب رویدادهای بعد از آن
    out = df.copy()
    for col in ("open", "high", "low", "close", "final", "yesterday"):
        out[col] = out[col] * factor
    out["adj_factor"] = factor
    return out    


class TSETMC:
    def __init__(self, timeout: float = 15, retries: int = 2):
        self.c = httpx.AsyncClient(headers=HEADERS, timeout=timeout, http2=False)
        self.retries = retries
        self._cache: dict[str, tuple[float, object]] = {}

    async def close(self):
        await self.c.aclose()

    # ───────────── low-level ─────────────
    async def _get(self, path: str, ttl: float = 0) -> dict:
        """GET با retry؛ ttl>0 یعنی نتیجه کش شود (برای داده‌های کم‌تغییر مثل مشخصات نماد)"""
        now = asyncio.get_event_loop().time()
        if ttl and path in self._cache and now - self._cache[path][0] < ttl:
            return self._cache[path][1]
        last_exc = None
        for attempt in range(self.retries + 1):
            try:
                r = await self.c.get(f"{BASE}/{path}")
                if r.status_code == 403:
                    raise PermissionError("TSETMC 403 — احتمالاً IP خارج از ایران یا هدر ناقص")
                r.raise_for_status()
                data = r.json()
                if ttl:
                    self._cache[path] = (now, data)
                return data
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                last_exc = e
                await asyncio.sleep(0.5 * (attempt + 1))
        raise last_exc

    # ───────────── search / info ─────────────
    async def search(self, q: str, limit: int = 10) -> list[dict]:
        q_fa = ar2fa(q)
        d = await self._get(f"Instrument/GetInstrumentSearch/{fa2ar(q_fa)}", ttl=300)
        rows = []
        for i in d.get("instrumentSearch", []) or []:
            sym, name = ar2fa(i.get("lVal18AFC")), ar2fa(i.get("lVal30"))
            if not sym:
                continue
            rows.append({"ins_code": str(i.get("insCode")), "symbol": sym, "name": name,
                         "active": i.get("lastDate") == 1, "market": i.get("flow")})
        # رتبه‌بندی: تطابق دقیق → شروع با عبارت → فعال → کوتاه‌تر
        rows.sort(key=lambda r: (r["symbol"] != q_fa, not r["symbol"].startswith(q_fa), not r["active"], len(r["symbol"])))
        # حذف نمادهای تکراری (کدهای قدیمی/غیرفعال با همان نام)
        seen, out = set(), []
        for r in rows:
            if r["symbol"] in seen and not r["active"]:
                continue
            seen.add(r["symbol"]); out.append(r)
        return out[:limit]

    async def info(self, ins: str) -> dict:
        d = (await self._get(f"Instrument/GetInstrumentInfo/{ins}", ttl=600)).get("instrumentInfo") or {}
        st, eps, sec = d.get("staticThreshold") or {}, d.get("eps") or {}, d.get("sector") or {}
        return {
            "ins_code": ins,
            "symbol": ar2fa(d.get("lVal18AFC")), "name": ar2fa(d.get("lVal30")),
            "sector": ar2fa(sec.get("lSecVal")), "sector_code": sec.get("cSecVal"),
            "base_volume": d.get("baseVol"),
            "limit_up": st.get("psGelStaMax"), "limit_down": st.get("psGelStaMin"),
            "eps": eps.get("estimatedEPS"), "sector_pe": eps.get("sectorPE"),
            "shares": d.get("zTitad"), "market": ar2fa(d.get("flowTitle")),
        }

    # ───────────── live ─────────────
    async def price(self, ins: str) -> dict:
        d = (await self._get(f"ClosingPrice/GetClosingPriceInfo/{ins}")).get("closingPriceInfo") or {}
        p = _map(d, FIELDS["price"])
        last = _num(p["last"])
        # قبل از اولین معامله‌ی روز open/high/low صفرند → روی آخرین قیمت
        for k in ("open", "high", "low"):
            if not _num(p[k]):
                p[k] = last
        return p

    async def orderbook(self, ins: str) -> list[dict]:
        rows = (await self._get(f"BestLimits/{ins}")).get("bestLimits") or []
        return sorted((_map(r, FIELDS["orderbook"]) for r in rows), key=lambda r: r["row"] or 0)

    async def client_type(self, ins: str) -> dict:
        d = (await self._get(f"ClientType/GetClientType/{ins}")).get("clientType") or {}
        out = _map(d, FIELDS["client"]); out.pop("date", None)
        return {k: _num(v) for k, v in out.items()}

    async def client_type_history(self, ins: str, days: int = 30) -> pd.DataFrame:
        rows = (await self._get(f"ClientType/GetClientTypeHistory/{ins}", ttl=300)).get("clientType") or []
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([_map(r, FIELDS["client"]) for r in rows])
        df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
        df = df.dropna(subset=["date"]).set_index("date").sort_index()
        return df.astype(float).tail(days)

    async def trades(self, ins: str) -> pd.DataFrame:
        rows = (await self._get(f"Trade/GetTrade/{ins}")).get("trade") or []
        if not rows:
            return pd.DataFrame(columns=["time", "price", "qty"])
        df = pd.DataFrame(rows)
        # فید معاملات گاه ردیف تکراری (همان nTran) برمی‌گرداند؛ بدون حذف، حجم کندل‌های
        # درون‌روزی از حجم رسمی TSETMC بیشتر می‌شود.
        if "nTran" in df.columns:
            df = df.drop_duplicates(subset="nTran", keep="first")
        today = datetime.now().strftime("%Y-%m-%d ")
        df["time"] = pd.to_datetime(today + df["hEven"].astype(str).str.zfill(6), format="%Y-%m-%d %H%M%S", errors="coerce")
        df = df.rename(columns={"pTran": "price", "qTitTran": "qty"}).dropna(subset=["time"])
        df = df[df["price"] > 0]
        return df[["time", "price", "qty"]].sort_values("time").reset_index(drop=True)

    # ───────────── history ─────────────
    async def daily_history(self, ins: str, limit: int = 400, include_halted: bool = False,
                            adjust: bool = True, close_source: str = "final") -> pd.DataFrame:
        rows = (await self._get(f"ClosingPrice/GetClosingPriceDailyList/{ins}/0", ttl=120)).get("closingPriceDaily") or []
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([_map(r, FIELDS["daily"]) for r in rows])
        df["ts"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
        df = df.dropna(subset=["ts"]).set_index("ts").sort_index()
        for col in ("open", "high", "low", "close", "final", "yesterday", "volume", "value", "count"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        df = df[(df["close"] > 0) | (df["final"] > 0)]
        df = df[~df.index.duplicated(keep="last")]

        # روزهای بدون معامله: پر کردن با پایانی (کندل صاف) یا حذف
        halted = df["volume"] <= 0
        for col in ("open", "high", "low", "close"):
            df.loc[halted | (df[col] <= 0), col] = df["final"]
        df["final"] = df["final"].where(df["final"] > 0, df["close"])

        if adjust:
            df = adjust_prices(df)               # قبل از حذف روزها تا زنجیرهٔ دیروز/پایانی سالم باشد
        if not include_halted:
            df = df[~halted]

        df["last"] = df["close"]                 # آخرین معامله را نگه می‌داریم
        if close_source == "final":
            df["close"] = df["final"]            # کندل مثل مفید: بسته = پایانی
        df["high"] = df[["high", "open", "close"]].max(axis=1)
        df["low"] = df[["low", "open", "close"]].min(axis=1)
        cols = ["open", "high", "low", "close", "last", "final", "volume", "value", "count"] + (["adj_factor"] if adjust else [])
        return df[cols].tail(limit).astype(float)

    # ───────────── whole market ─────────────
    async def market_watch(self) -> dict[str, dict]:
        """کل بازار در یک درخواست؛ کلید = ins_code. برای poller مرکزی در نسخه‌ی چندکاربره"""
        d = await self._get("ClosingPrice/GetMarketWatch?market=0&paperTypes[0]=1&paperTypes[1]=2"
                            "&industrialGroup=&withWithdrawal=1&withBestLimits=1&hEven=0&RefID=0")
        out = {}
        for r in d.get("marketwatch", []) or []:
            row = _map(r, FIELDS["watch"])
            row["symbol"], row["name"] = ar2fa(row["symbol"]), ar2fa(row["name"])
            row["orderbook"] = [{"row": b.get("n"), "bid_count": b.get("zmd"), "bid_vol": b.get("qmd"), "bid": b.get("pmd"),
                                 "ask": b.get("pmo"), "ask_vol": b.get("qmo"), "ask_count": b.get("zmo")}
                                for b in (r.get("blDs") or [])]
            out[str(r.get("insCode"))] = row
        return out


def build_intraday_candles(trades: pd.DataFrame, tf: str = "5min") -> pd.DataFrame:
    """کندل درون‌روزی از ریز معاملات (TSETMC خودش کندل نمی‌دهد)"""
    if trades is None or trades.empty:
        return pd.DataFrame()
    t = trades.set_index("time")
    o = t["price"].resample(tf).ohlc()
    o["volume"] = t["qty"].resample(tf).sum()
    o = o.dropna(subset=["close"])
    o["final"] = o["close"]; o["value"] = o["volume"] * o["close"]
    return o