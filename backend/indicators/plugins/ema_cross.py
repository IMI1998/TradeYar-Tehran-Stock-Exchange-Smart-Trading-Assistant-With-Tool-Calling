from backend.indicators.base import Indicator
from backend.indicators import ta

class EMACross(Indicator):
    name = "EMA Cross"; overlay = True; description = "تقاطع دو EMA"; inputs = {"fast": 9, "slow": 21}
    colors = {"Fast": "#26a69a", "Slow": "#ef5350"}
    def calc(self, df, p, confirmed=True):
        f, s = ta.ema(df.close, p["fast"]), ta.ema(df.close, p["slow"])
        return {"plots": {"Fast": f, "Slow": s}, "signals": {"buy": ta.crossover(f, s), "sell": ta.crossunder(f, s)},
                "summary": {"state": "bull" if f.iloc[-1] > s.iloc[-1] else "bear"}}