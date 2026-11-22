from backend.indicators.base import Indicator
from backend.indicators import ta

class MACD(Indicator):
    name = "MACD"; description = "MACD با خط سیگنال و هیستوگرام"; inputs = {"fast": 12, "slow": 26, "signal": 9}
    colors = {"MACD": "#2962ff", "Signal": "#ff6d00", "Hist": "#9e9e9e"}
    def calc(self, df, p, confirmed=True):
        m, s, h = ta.macd(df.close, p["fast"], p["slow"], p["signal"])
        return {"plots": {"MACD": m, "Signal": s, "Hist": h}, "levels": [0],
                "signals": {"buy": ta.crossover(m, s), "sell": ta.crossunder(m, s)},
                "summary": {"hist": round(float(h.iloc[-1]), 2), "above_zero": bool(m.iloc[-1] > 0)}}