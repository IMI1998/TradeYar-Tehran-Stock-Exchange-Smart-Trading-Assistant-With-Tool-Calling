"""HSN Algo [V9.5] — پلاگین پریمیوم. موتور در _hsn_engine.py است و هرگز به کلاینت نمی‌رود."""
import time
import numpy as np
import pandas as pd
from backend.indicators.base import Indicator
from ._hsn_engine import HSNParams, compute_hsn, hsn_trend_signal, ribbon_signals, rsi_reversal, volume_spike

BULL = "rgba(38,166,154,0.18)"; BEAR = "rgba(239,83,80,0.18)"
GREY = "rgba(120,123,134,0.16)"; GOLD = "rgba(255,213,79,0.22)"
STRUCT_KEYS = ["i_bull_bos", "i_bull_choch", "i_bull_chochp", "i_bear_bos", "i_bear_choch", "i_bear_chochp",
               "s_bull_bos", "s_bull_choch", "s_bull_chochp", "s_bear_bos", "s_bear_choch", "s_bear_chochp"]
ALERT_KEYS = STRUCT_KEYS + ["bull_ob", "bear_ob", "bull_ob_touch", "bear_ob_touch", "supply_break", "demand_break",
                            "trendline_break_up", "trendline_break_down", "bullish_volume", "bearish_volume",
                            "major_line_confirm", "major_line_cross", "liquidity_line_touch"]


class HSNAlgo(Indicator):
    name = "HSN Algo"; premium = True; heavy = True; overlay = True
    description = ("سیگنال اصلی (SuperTrend)، ریبون روند، ساختار بازار BOS/CHoCH، اردر بلاک حجمی، "
                   "عرضه/تقاضا، حمایت/مقاومت، الگوی مستر و لیکوییدیتی، سطوح روز/هفته/ماه قبل")
    inputs = {"st_multiplier": 3.2, "st_periods": 40, "internal_lookback": 5, "swing_lookback": 50,
              "sd_swing_length": 8, "sd_box_width": 4.0, "sr_strength": 6, "sr_zone_width_pct": 1.0,
              "show_trendlines": True, "mintick": 1.0, "max_bars": 600, "heavy_refresh_sec": 60}
    colors = {"SuperTrend": "#26a69a", "EMA12": "#42a5f5", "EMA26": "#ffa726", "VWMA20": "#ab47bc"}
    signal_styles = {
        "buy":  {"shape": "arrowUp", "color": "#26a69a", "position": "belowBar", "text": "BUY"},
        "sell": {"shape": "arrowDown", "color": "#ef5350", "position": "aboveBar", "text": "SELL"},
        "ribbon_buy":  {"shape": "circle", "color": "#42a5f5", "position": "belowBar", "text": "R"},
        "ribbon_sell": {"shape": "circle", "color": "#ffa726", "position": "aboveBar", "text": "R"},
        "rsi_rev_up":   {"shape": "square", "color": "#ffd54f", "position": "belowBar", "text": "RSI"},
        "rsi_rev_down": {"shape": "square", "color": "#ffd54f", "position": "aboveBar", "text": "RSI"},
        "bos_bull":   {"shape": "circle", "color": "#26a69a", "position": "aboveBar", "text": "BOS"},
        "choch_bull": {"shape": "circle", "color": "#26a69a", "position": "aboveBar", "text": "CHoCH"},
        "bos_bear":   {"shape": "circle", "color": "#ef5350", "position": "belowBar", "text": "BOS"},
        "choch_bear": {"shape": "circle", "color": "#ef5350", "position": "belowBar", "text": "CHoCH"},
        "ob_touch_bull": {"shape": "square", "color": "#26a69a", "position": "belowBar", "text": "OB"},
        "ob_touch_bear": {"shape": "square", "color": "#ef5350", "position": "aboveBar", "text": "OB"},
        "liquidity_touch": {"shape": "circle", "color": "#ffd54f", "position": "aboveBar", "text": "LIQ"},
    }

    def __init__(self):
        self._cache = {"key": None, "at": 0.0, "res": None, "objs": None, "err": None}

    def _params(self, p):
        f = HSNParams.__dataclass_fields__
        return HSNParams(**{k: v for k, v in p.items() if k in f})

    def _heavy(self, df, p, confirmed):
        key = (len(df), str(df.index[-1]), str(df.index[0]))
        c = self._cache
        if c["res"] is not None and c["key"] == key and time.time() - c["at"] < float(p["heavy_refresh_sec"]):
            return c["res"], c["objs"], c["err"]
        try:
            res, objs = compute_hsn(df, self._params(p), last_bar_confirmed=confirmed); err = None
        except Exception as e:
            res, objs, err = c["res"], c["objs"], f"{type(e).__name__}: {e}"
        c.update(key=key, at=time.time(), res=res, objs=objs, err=err)
        return res, objs, err

    def calc(self, df, p, confirmed=True):
        df = df.tail(int(p.get("max_bars", 600)))
        idx = df.index; n = len(df); last = n - 1
        o, h, l, c, v = (df[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
        S = lambda a: pd.Series(np.asarray(a), index=idx)
        f = lambda x: None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)
        T = lambda i: idx[max(0, min(int(i), last))]

        st = hsn_trend_signal(h, l, c, p["st_multiplier"], p["st_periods"])
        rb = ribbon_signals(c); rs = rsi_reversal(c); vs = volume_spike(o, c, v)
        st_line = np.where(st["trend"] == 1, st["st_up"], st["st_dn"])
        plots = {"SuperTrend": S(st_line), "EMA12": S(rb["ribbon_fast"]), "EMA26": S(rb["ribbon_slow"])}
        signals = {"buy": S(st["buy"]), "sell": S(st["sell"]),
                   "ribbon_buy": S(rb["ribbon_buy"]), "ribbon_sell": S(rb["ribbon_sell"]),
                   "rsi_rev_up": S(rs["reversal_up"]), "rsi_rev_down": S(rs["reversal_down"])}
        any_sig = st["buy"] | st["sell"]
        summary = {
            "main_trend": "bull" if st["trend"][-1] == 1 else "bear",
            "supertrend_stop": f(st_line[-1]),
            "bars_since_main_signal": int(np.argmax(any_sig[::-1])) if any_sig.any() else None,
            "ribbon": "bull" if rb["ribbon_bull"][-1] else "bear" if rb["ribbon_bear"][-1] else "neutral",
            "ribbon_color": next((k for k in ("green", "red", "blue", "lblue", "orange", "yellow") if rb[f"ribbon_{k}"][-1]), None),
            "rsi": f(round(rs["rsi"][-1], 1)) if not np.isnan(rs["rsi"][-1]) else None,
            "volume_spike": "bull" if vs["bullish_volume"][-1] else "bear" if vs["bearish_volume"][-1] else None,
            "last_bar_confirmed": bool(confirmed),
        }
        out = {"plots": plots, "signals": signals, "zones": [], "lines": [], "summary": summary}
        if n < 120:
            summary["note"] = f"فقط {n} کندل؛ ساختار بازار/اردر بلاک نیاز به ≥120 کندل دارد"
            return out

        res, objs, err = self._heavy(df, p, confirmed)
        if err: summary["heavy_error"] = err
        if res is None or len(res) != n:
            return out
        summary["heavy_age_sec"] = int(time.time() - self._cache["at"])
        R = lambda k: res[k].to_numpy()

        plots["VWMA20"] = S(R("vwma20"))
        signals.update({
            "bos_bull": S(R("i_bull_bos") | R("s_bull_bos")),
            "choch_bull": S(R("i_bull_choch") | R("i_bull_chochp") | R("s_bull_choch") | R("s_bull_chochp")),
            "bos_bear": S(R("i_bear_bos") | R("s_bear_bos")),
            "choch_bear": S(R("i_bear_choch") | R("i_bear_chochp") | R("s_bear_choch") | R("s_bear_chochp")),
            "ob_touch_bull": S(R("bull_ob_touch")), "ob_touch_bear": S(R("bear_ob_touch")),
            "liquidity_touch": S(R("liquidity_line_touch")),
        })

        zones, lines = out["zones"], out["lines"]
        ob = objs["order_blocks"]
        for b in ob["bull"][:3]:
            zones.append({"top": b["top"], "btm": b["btm"], "from": T(b["left_bar"]), "to": T(last), "extend": True, "color": BULL, "label": f"Bull OB {b['vol_pct'] or ''}%"})
        for b in ob["bear"][:3]:
            zones.append({"top": b["top"], "btm": b["btm"], "from": T(b["left_bar"]), "to": T(last), "extend": True, "color": BEAR, "label": f"Bear OB {b['vol_pct'] or ''}%"})
        sd = objs["supply_demand"]
        for b in sd["supply"][:3]:
            zones.append({"top": b["top"], "btm": b["btm"], "from": T(b["left_bar"]), "to": T(last), "extend": True, "color": BEAR, "label": "Supply"})
        for b in sd["demand"][:3]:
            zones.append({"top": b["top"], "btm": b["btm"], "from": T(b["left_bar"]), "to": T(last), "extend": True, "color": BULL, "label": "Demand"})
        half = 0.005 * c[-1]
        for lv in objs["sr"]["levels"][:6]:
            z0, z1 = lv["zone"]
            if np.isnan(z0) or np.isnan(z1): z0, z1 = lv["price"] - half, lv["price"] + half
            zones.append({"top": z1, "btm": z0, "from": T(0), "to": T(last), "extend": True, "color": GREY, "label": f"S/R {lv['kind']}"})
        for bx in objs["master_pattern"]["boxes"][-3:]:
            zones.append({"top": bx["top"], "btm": bx["bottom"], "from": T(bx["left"]), "to": T(bx["right"]), "extend": False, "color": GOLD, "label": "MP"})
        for ln in objs["master_pattern"]["liquidity_lines"][-4:]:
            lines.append({"price": ln["y1"], "from": T(ln["x1"]), "to": T(last), "color": "#ffd54f" if ln["side"] == "buy" else "#ef5350",
                          "label": f"Liq {ln['side']}", "style": "dashed" if ln["crossed"] else "solid"})
        for ln in objs["master_pattern"]["expansion_lines"][-3:]:
            lines.append({"price": ln["y1"], "from": T(ln["x1"]), "to": T(ln["x2"]), "color": "#b0bec5", "label": "Exp", "style": "dotted"})
        for k, lab in (("pdh", "PDH"), ("pdl", "PDL"), ("pwh", "PWH"), ("pwl", "PWL"), ("pmh", "PMH"), ("pml", "PML")):
            if k in res and not np.isnan(res[k].iloc[-1]):
                lines.append({"price": float(res[k].iloc[-1]), "from": T(last - 30), "to": T(last), "color": "#787b86", "label": lab, "style": "dotted"})

        cl = c[-1]; L = lambda k: res[k].iloc[-1]
        zone = ("premium" if cl >= L("premium_low") else "discount" if cl <= L("discount_high")
                else "equilibrium" if L("eq_btm") <= cl <= L("eq_top") else "mid")
        date = lambda i: str(T(i).date()) if hasattr(T(i), "date") else str(T(i))
        summary.update({
            "internal_structure": "bull" if L("itrend") > 0 else "bear" if L("itrend") < 0 else "none",
            "swing_structure": "bull" if L("swing_trend") > 0 else "bear" if L("swing_trend") < 0 else "none",
            "price_zone": zone, "range_top": f(L("range_top")), "range_btm": f(L("range_btm")),
            "in_supply": bool(L("in_supply")), "in_demand": bool(L("in_demand")),
            "bull_order_blocks": [{"top": f(b["top"]), "btm": f(b["btm"]), "vol_pct": b["vol_pct"], "from": date(b["left_bar"])} for b in ob["bull"][:3]],
            "bear_order_blocks": [{"top": f(b["top"]), "btm": f(b["btm"]), "vol_pct": b["vol_pct"], "from": date(b["left_bar"])} for b in ob["bear"][:3]],
            "supply_zones": [{"top": f(b["top"]), "btm": f(b["btm"]), "vol_pct": f(b["vol_pct"])} for b in sd["supply"][:3]],
            "demand_zones": [{"top": f(b["top"]), "btm": f(b["btm"]), "vol_pct": f(b["vol_pct"])} for b in sd["demand"][:3]],
            "sr_levels": [{"price": f(round(x["price"])), "kind": x["kind"]} for x in objs["sr"]["levels"][:8]],
            "liquidity_lines": [{"price": f(ln["y1"]), "side": ln["side"], "swept": bool(ln["crossed"])} for ln in objs["master_pattern"]["liquidity_lines"][-4:]],
            "htf_levels": {k.upper(): f(res[k].iloc[-1]) for k in ("pdh", "pdl", "pwh", "pwl", "pmh", "pml") if k in res},
            "recent_structure_events": [{"date": date(e["bar"]), "type": e["type"], "side": e["side"], "scope": e["scope"], "level": f(e["level"])} for e in objs["ms_events"][-6:]],
            "alerts_now": [k for k in ALERT_KEYS if bool(res[k].iloc[-1])],
            "alerts_last_5_bars": {k: int(res[k].tail(5).sum()) for k in ALERT_KEYS if res[k].tail(5).any()},
        })
        return out