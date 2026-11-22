from backend.indicators.base import Indicator
from backend.indicators import ta

class RSI(Indicator):
    name = "RSI"; description = "شاخص قدرت نسبی؛ خرید در عبور از اشباع فروش، فروش در عبور از اشباع خرید"
    inputs = {"length": 14, "overbought": 70, "oversold": 30}; colors = {"RSI": "#7e57c2"}
    def calc(self, df, p, confirmed=True):
        r = ta.rsi(df.close, p["length"])
        return {"plots": {"RSI": r}, "levels": [p["oversold"], p["overbought"]],
                "signals": {"buy": ta.crossover(r, p["oversold"]), "sell": ta.crossunder(r, p["overbought"])},
                "summary": {"rsi": round(float(r.iloc[-1]), 1)}}