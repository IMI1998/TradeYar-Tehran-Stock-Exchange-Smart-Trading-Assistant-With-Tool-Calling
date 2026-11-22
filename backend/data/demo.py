"""منبع داده‌ی شبیه‌سازی‌شده — برای تست وقتی بازار بسته است یا TSETMC در دسترس نیست"""
import zlib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

SYMBOLS = {
    "DEMO_FOLD": ("فولاد", "فولاد مبارکه اصفهان (دمو)", "فلزات اساسی"),
    "DEMO_KHOD": ("خودرو", "ایران خودرو (دمو)", "خودرو"),
    "DEMO_SHPNA": ("شپنا", "پالایش نفت اصفهان (دمو)", "فرآورده‌های نفتی"),
}


class DemoSource:
    def __init__(self):
        self.state = {}

    def _s(self, ins):
        if ins not in self.state:
            rng = np.random.default_rng(zlib.crc32(ins.encode()))
            n = 400
            close = 5000 * (1 + rng.random() * 3) * np.cumprod(1 + rng.normal(0.0005, 0.02, n).clip(-0.05, 0.05))
            idx = pd.bdate_range(end=datetime.now().date() - timedelta(days=1), periods=n)
            df = pd.DataFrame(index=idx)
            df["close"] = close
            df["open"] = df["close"].shift(1).fillna(close[0])
            df["high"] = np.maximum(df.open, df.close) * (1 + rng.random(n) * 0.02)
            df["low"] = np.minimum(df.open, df.close) * (1 - rng.random(n) * 0.02)
            df["final"] = df["close"]
            df["volume"] = rng.integers(1_000_000, 50_000_000, n).astype(float)
            df["value"] = df.volume * df.close
            last = float(close[-1])
            self.state[ins] = {"hist": df, "y": last, "last": last, "open": last, "high": last, "low": last,
                               "vol": 0.0, "cnt": 0, "trades": [], "rng": np.random.default_rng()}
        return self.state[ins]

    async def search(self, q, limit=10):
        rows = [{"ins_code": k, "symbol": v[0], "name": v[1], "active": True}
                for k, v in SYMBOLS.items() if q in v[0] or q in v[1] or q in k]
        return rows or [{"ins_code": k, "symbol": v[0], "name": v[1], "active": True} for k, v in SYMBOLS.items()]

    async def info(self, ins):
        s = self._s(ins); sym = SYMBOLS.get(ins, ("DEMO", ins, "-"))
        return {"symbol": sym[0], "name": sym[1], "sector": sym[2], "base_volume": 5_000_000,
                "limit_up": round(s["y"] * 1.05), "limit_down": round(s["y"] * 0.95), "eps": 900, "sector_pe": 7.5}

    async def price(self, ins):
        s = self._s(ins)
        s["last"] = float(np.clip(s["last"] * (1 + s["rng"].normal(0, 0.003)), s["y"] * 0.95, s["y"] * 1.05))
        s["high"], s["low"] = max(s["high"], s["last"]), min(s["low"], s["last"])
        q = int(s["rng"].integers(1000, 200000)); s["vol"] += q; s["cnt"] += 1
        s["trades"].append((datetime.now(), s["last"], q))
        return {"last": s["last"], "final": (s["last"] + s["y"]) / 2, "open": s["open"], "high": s["high"],
                "low": s["low"], "yesterday": s["y"], "volume": s["vol"], "value": s["vol"] * s["last"],
                "count": s["cnt"], "date": int(datetime.now().strftime("%Y%m%d")), "time": int(datetime.now().strftime("%H%M%S"))}

    async def orderbook(self, ins):
        s = self._s(ins); p = round(s["last"])
        return [{"row": i + 1, "bid_count": 10 + i, "bid_vol": 50000 * (i + 1), "bid": p - 10 * (i + 1),
                 "ask": p + 10 * (i + 1), "ask_vol": 40000 * (i + 1), "ask_count": 8 + i} for i in range(5)]

    async def client_type(self, ins):
        s = self._s(ins); v = s["vol"] or 1e6
        return {"buy_real_vol": v * 0.7, "buy_legal_vol": v * 0.3, "sell_real_vol": v * 0.55, "sell_legal_vol": v * 0.45,
                "buy_real_cnt": 800, "buy_legal_cnt": 5, "sell_real_cnt": 1200, "sell_legal_cnt": 4}

    async def client_type_history(self, ins, days=30):
        s = self._s(ins); h = s["hist"].tail(days); rng = s["rng"]
        df = pd.DataFrame(index=h.index)
        df["buy_real_vol"] = h.volume * rng.uniform(0.4, 0.9, len(h)); df["sell_real_vol"] = h.volume * rng.uniform(0.4, 0.9, len(h))
        df["buy_legal_vol"] = h.volume - df.buy_real_vol; df["sell_legal_vol"] = h.volume - df.sell_real_vol
        df["buy_real_cnt"] = rng.integers(300, 2000, len(h)); df["sell_real_cnt"] = rng.integers(300, 2000, len(h))
        df["buy_legal_cnt"] = 5; df["sell_legal_cnt"] = 5
        return df

    async def trades(self, ins):
        s = self._s(ins)
        return pd.DataFrame(s["trades"], columns=["time", "price", "qty"])

    async def daily_history(self, ins, limit=400, **kw):
        df = self._s(ins)["hist"].tail(limit).copy()
        df["last"] = df["close"]
        return df