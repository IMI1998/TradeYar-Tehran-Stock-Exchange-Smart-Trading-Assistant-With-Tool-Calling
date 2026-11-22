from backend.indicators.base import Indicator
from backend.indicators import ta

class EMA(Indicator):
    name = "EMA"; overlay = True; description = "میانگین متحرک نمایی"; inputs = {"length": 20}; colors = {"EMA": "#ffb74d"}
    def calc(self, df, p, confirmed=True):
        e = ta.ema(df.close, p["length"])
        return {"plots": {"EMA": e}, "summary": {"price_vs_ema_pct": round(float(df.close.iloc[-1] / e.iloc[-1] - 1) * 100, 2)}}