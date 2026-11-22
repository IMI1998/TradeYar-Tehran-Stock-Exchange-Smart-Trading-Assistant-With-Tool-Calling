"""محاسبات عددی که خروجی‌شان به LLM داده می‌شود (LLM فقط تفسیر می‌کند)"""
import numpy as np
import pandas as pd
from backend.indicators import ta


def money_flow(ct: pd.DataFrame, prices: pd.DataFrame, n: int = 20) -> dict:
    if ct is None or ct.empty:
        return {"error": "داده‌ی حقیقی/حقوقی موجود نیست"}
    d = ct.tail(n).copy()
    px = prices["close"].reindex(d.index, method="nearest") if prices is not None else pd.Series(1, index=d.index)
    d["net_real_value"] = (d.buy_real_vol - d.sell_real_vol) * px
    d["pc_buy"] = (d.buy_real_vol * px / d.buy_real_cnt.replace(0, np.nan)) / 1e7   # سرانه خرید حقیقی (میلیون تومان)
    d["pc_sell"] = (d.sell_real_vol * px / d.sell_real_cnt.replace(0, np.nan)) / 1e7
    d["buyer_power"] = d.pc_buy / d.pc_sell
    real_buy_share = float(d.buy_real_vol.iloc[-1] / (d.buy_real_vol.iloc[-1] + d.buy_legal_vol.iloc[-1] + 1e-9) * 100)
    return {
        "days": int(len(d)),
        "net_real_flow_today_bn_toman": round(float(d.net_real_value.iloc[-1]) / 1e10, 2),
        "net_real_flow_5d_bn_toman": round(float(d.net_real_value.tail(5).sum()) / 1e10, 2),
        "net_real_flow_20d_bn_toman": round(float(d.net_real_value.sum()) / 1e10, 2),
        "per_capita_buy_today_mtoman": round(float(d.pc_buy.iloc[-1]), 1),
        "per_capita_sell_today_mtoman": round(float(d.pc_sell.iloc[-1]), 1),
        "buyer_power_today": round(float(d.buyer_power.iloc[-1]), 2),
        "buyer_power_avg": round(float(d.buyer_power.mean()), 2),
        "real_buy_share_pct": round(real_buy_share, 1),
        "legal_to_real_days": int(((d.buy_real_vol > d.sell_real_vol) & (d.sell_legal_vol > d.buy_legal_vol)).sum()),
        "abnormal_per_capita": bool(d.pc_buy.iloc[-1] > 3 * d.pc_buy.mean()),
        "daily_net_real_last10": [round(float(x) / 1e10, 2) for x in d.net_real_value.tail(10)],
    }


def queue_status(ob: list[dict], info: dict, last: float) -> dict:
    if not ob:
        return {"queue": None}
    top = ob[0]; up, dn = info.get("limit_up"), info.get("limit_down")
    bid, ask = top.get("bid") or 0, top.get("ask") or 0
    if up and bid >= up and not ask:
        return {"queue": "buy", "queue_volume": top.get("bid_vol"), "queue_value_bn_toman": round(top["bid_vol"] * up / 1e10, 2),
                "queue_orders": top.get("bid_count"), "executable_entry": False}
    if dn and ask <= dn and not bid:
        return {"queue": "sell", "queue_volume": top.get("ask_vol"), "queue_value_bn_toman": round(top["ask_vol"] * dn / 1e10, 2),
                "queue_orders": top.get("ask_count"), "executable_exit": False}
    tb = sum(r.get("bid_vol") or 0 for r in ob); ta_ = sum(r.get("ask_vol") or 0 for r in ob)
    return {"queue": None, "best_bid": bid, "best_ask": ask,
            "spread_pct": round((ask - bid) / last * 100, 2) if bid and ask else None,
            "bid_ask_volume_ratio": round(tb / (ta_ + 1e-9), 2),
            "dist_to_limit_up_pct": round((up - last) / last * 100, 2) if up else None,
            "dist_to_limit_down_pct": round((last - dn) / last * 100, 2) if dn else None}


def find_levels(df: pd.DataFrame, window: int = 8, tol: float = 0.015) -> dict:
    h, l = df.high, df.low
    piv_h = h[(h == h.rolling(2 * window + 1, center=True).max())].dropna()
    piv_l = l[(l == l.rolling(2 * window + 1, center=True).min())].dropna()

    def cluster(vals):
        out = []
        for v in sorted(vals):
            if out and abs(v - out[-1]["price"]) / out[-1]["price"] < tol:
                c = out[-1]; c["touches"] += 1; c["price"] = (c["price"] * (c["touches"] - 1) + v) / c["touches"]
            else:
                out.append({"price": float(v), "touches": 1})
        return out

    last = float(df.close.iloc[-1])
    lv = cluster(list(piv_h.values) + list(piv_l.values))
    sup = sorted([x for x in lv if x["price"] < last], key=lambda x: -x["price"])[:3]
    res = sorted([x for x in lv if x["price"] > last], key=lambda x: x["price"])[:3]
    rnd = lambda xs: [{"price": round(x["price"]), "touches": x["touches"], "dist_pct": round((x["price"] / last - 1) * 100, 2)} for x in xs]
    return {"last": last, "support": rnd(sup), "resistance": rnd(res),
            "atr14": round(float(ta.atr(df, 14).iloc[-1]), 1),
            "hh_20": round(float(df.high.tail(20).max())), "ll_20": round(float(df.low.tail(20).min()))}


def snapshot(session) -> dict:
    """خلاصه‌ی ساختاریافته‌ی چارت برای LLM"""
    df = session.df
    if df is None:
        return {"error": "چارت هنوز داده ندارد"}
    c = df.close
    vol20 = float(df.volume.tail(20).mean()) or 1
    ind_summary = {}
    for iid, r in session.results.items():
        plots = {n: [round(float(x), 3) for x in s.tail(3)] for n, s in (r.get("plots") or {}).items()}
        sigs = {n: int(s.tail(10).fillna(False).sum()) for n, s in (r.get("signals") or {}).items()}
        last_sig = {n: (str(s[s.fillna(False)].index[-1]) if s.fillna(False).any() else None) for n, s in (r.get("signals") or {}).items()}
        ind_summary[iid] = {"params": session.indicators[iid]["params"], "last3": plots, "signals_last10bars": sigs, "last_signal_at": last_sig}
    return {
        "symbol": session.symbol, "timeframe": session.timeframe, "info": session.info, "meta": session.meta,
        "price": {"last": float(c.iloc[-1]), "chg_1_pct": round(float(c.pct_change().iloc[-1] * 100), 2),
                  "chg_5_pct": round(float((c.iloc[-1] / c.iloc[-6] - 1) * 100), 2) if len(c) > 6 else None,
                  "chg_20_pct": round(float((c.iloc[-1] / c.iloc[-21] - 1) * 100), 2) if len(c) > 21 else None,
                  "vs_sma20_pct": round(float((c.iloc[-1] / ta.sma(c, 20).iloc[-1] - 1) * 100), 2) if len(c) > 20 else None,
                  "vs_sma50_pct": round(float((c.iloc[-1] / ta.sma(c, 50).iloc[-1] - 1) * 100), 2) if len(c) > 50 else None,
                  "volume_vs_avg20": round(float(df.volume.iloc[-1] / vol20), 2),
                  "volume_vs_base": round(float(df.volume.iloc[-1] / session.info["base_volume"]), 2) if session.info.get("base_volume") else None},
        "last_5_bars": [{"t": str(i.date() if session.timeframe == "D" else i), "o": float(r.open), "h": float(r.high), "l": float(r.low), "c": float(r.close), "v": float(r.volume)}
                        for i, r in df.tail(5).iterrows()],
        "indicators": ind_summary,
    }