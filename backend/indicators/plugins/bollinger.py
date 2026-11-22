from backend.indicators.base import Indicator
from backend.indicators import ta

class Bollinger(Indicator):
    name = "Bollinger"; overlay = True; description = "باندهای بولینگر"; inputs = {"length": 20, "mult": 2.0}
    colors = {"Upper": "#90a4ae", "Mid": "#ffd54f", "Lower": "#90a4ae"}
    def calc(self, df, p, confirmed=True):
        u, m, l = ta.bbands(df.close, p["length"], p["mult"])
        c = df.close.iloc[-1]
        return {"plots": {"Upper": u, "Mid": m, "Lower": l},
                "signals": {"buy": ta.crossover(df.close, l), "sell": ta.crossunder(df.close, u)},
                "summary": {"pct_b": round(float((c - l.iloc[-1]) / (u.iloc[-1] - l.iloc[-1])), 2)}}