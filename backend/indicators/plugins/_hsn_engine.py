"""
HSN Algo [V9.5]  ->  Python port (signal engine)
Requirements: numpy, pandas
Input: DataFrame with columns open, high, low, close, volume (+ DatetimeIndex optional)
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional

NAN = float("nan")

#  Pine-compatible primitives
def isna(x):
    try:
        return x is None or np.isnan(x)
    except TypeError:
        return False

def nz(x, r=0.0):
    return r if isna(x) else x

def pine_range(start, end):
    """Pine for-loop semantics: counts down if end < start."""
    return range(start, end + 1) if end >= start else range(start, end - 1, -1)

def sma(a, n):
    return pd.Series(np.asarray(a, float)).rolling(n, min_periods=n).mean().to_numpy()

def _ewm_pine(a, n, alpha):
    a = np.asarray(a, float); out = np.full(len(a), NAN)
    seed = sma(a, n); started = False
    for i in range(len(a)):
        if not started:
            if not np.isnan(seed[i]):
                out[i] = seed[i]; started = True
        else:
            out[i] = alpha * a[i] + (1 - alpha) * out[i - 1]
    return out

def ema(a, n):  return _ewm_pine(a, n, 2.0 / (n + 1))
def rma(a, n):  return _ewm_pine(a, n, 1.0 / n)

def true_range(h, l, c):
    n = len(c); tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr

def atr(h, l, c, n): return rma(true_range(h, l, c), n)

def rsi(c, n):
    c = np.asarray(c, float); ch = np.diff(c, prepend=NAN)
    up = rma(np.where(ch > 0, ch, 0.0), n)
    dn = rma(np.where(ch < 0, -ch, 0.0), n)
    out = np.full(len(c), NAN)
    for i in range(len(c)):
        if np.isnan(up[i]) or np.isnan(dn[i]): continue
        out[i] = 100.0 if dn[i] == 0 else (0.0 if up[i] == 0 else 100 - 100 / (1 + up[i] / dn[i]))
    return out

def highest(a, n): return pd.Series(np.asarray(a, float)).rolling(n, min_periods=n).max().to_numpy()
def lowest(a, n):  return pd.Series(np.asarray(a, float)).rolling(n, min_periods=n).min().to_numpy()

def vwma(src, vol, n): return sma(np.asarray(src) * np.asarray(vol), n) / sma(vol, n)

def pivothigh(a, L, R):
    """Value placed on the confirmation bar (i), refers to a[i-R] - Pine semantics."""
    a = np.asarray(a, float); n = len(a); out = np.full(n, NAN)
    for i in range(L + R, n):
        k = i - R; v = a[k]
        if np.all(a[k - L:k] < v) and np.all(a[k + 1:i + 1] <= v):
            out[i] = v
    return out

def pivotlow(a, L, R):
    a = np.asarray(a, float); n = len(a); out = np.full(n, NAN)
    for i in range(L + R, n):
        k = i - R; v = a[k]
        if np.all(a[k - L:k] > v) and np.all(a[k + 1:i + 1] >= v):
            out[i] = v
    return out

def crossover(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    pa = np.roll(a, 1); pb = np.roll(b, 1); pa[0] = NAN; pb[0] = NAN
    with np.errstate(invalid="ignore"):
        return (a > b) & (pa <= pb)

def crossunder(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    pa = np.roll(a, 1); pb = np.roll(b, 1); pa[0] = NAN; pb[0] = NAN
    with np.errstate(invalid="ignore"):
        return (a < b) & (pa >= pb)

def barssince(cond):
    out = np.full(len(cond), NAN); cnt = None
    for i, cnd in enumerate(cond):
        if cnd: cnt = 0
        elif cnt is not None: cnt += 1
        out[i] = NAN if cnt is None else cnt
    return out


@dataclass
class HSNParams:
    # --- Main signal (HSN Algo Signal) ---
    st_multiplier: float = 3.2
    st_periods: int = 40
    # --- Market structure ---
    internal_lookback: int = 5
    swing_lookback: int = 50
    ob_filter: str = "None"          # None / BOS / CHoCH / CHoCH+
    ob_num: int = 5
    ob_pos: str = "Precise"          # Full / Middle / Accurate / Precise
    ob_mitigation: str = "Absolute"  # Absolute / Middle
    use_overlap: bool = True
    overlap_method: str = "Previous" # Recent / Previous
    ob_show: bool = True
    ob_swings: bool = False
    # --- Supply & Demand ---
    sd_swing_length: int = 8
    sd_box_width: float = 4.0
    # --- S/R ---
    sr_strength: int = 6
    sr_zone_width_pct: float = 1.0
    # --- Master pattern ---
    mp_max_bars: int = 150
    mp_indi_type: int = 1
    mp_show_minor_expansion: bool = True
    mintick: float = 0.01
    # --- Trendlines ---
    show_trendlines: bool = False    # default false in Pine -> breakouts only if True
    trelen: int = 7
    tl_space: float = 0.5
    # --- Volume / RSI ---
    vol_lookback: int = 100
    rsi_len: int = 14
    rsi_ob: float = 75
    rsi_os: float = 25

#   1) MAIN BUY/SELL  (SuperTrend hl2, ATR(40) rma, mult 3.2) - EXACT
def hsn_trend_signal(h, l, c, mult=3.2, periods=40):
    n = len(c); src = (h + l) / 2; a = atr(h, l, c, periods)
    up = np.full(n, NAN); dn = np.full(n, NAN); tr = np.ones(n, int)
    buy = np.zeros(n, bool); sell = np.zeros(n, bool)
    for i in range(n):
        u = src[i] - mult * a[i]; d = src[i] + mult * a[i]
        up1 = up[i - 1] if i > 0 and not np.isnan(up[i - 1]) else u
        dn1 = dn[i - 1] if i > 0 and not np.isnan(dn[i - 1]) else d
        c1 = c[i - 1] if i > 0 else NAN
        if not np.isnan(c1) and not np.isnan(up1) and c1 > up1: u = max(u, up1)
        if not np.isnan(c1) and not np.isnan(dn1) and c1 < dn1: d = min(d, dn1)
        up[i] = u; dn[i] = d
        t = tr[i - 1] if i > 0 else 1
        if t == -1 and not np.isnan(dn1) and c[i] > dn1: t = 1
        elif t == 1 and not np.isnan(up1) and c[i] < up1: t = -1
        tr[i] = t
        if i > 0:
            buy[i] = t == 1 and tr[i - 1] == -1
            sell[i] = t == -1 and tr[i - 1] == 1
    return dict(st_up=up, st_dn=dn, trend=tr, buy=buy, sell=sell)

#   2) Trend Ribbon (CDC ActionZone, EMA 12/26)
def ribbon_signals(c):
    fast = ema(c, 12); slow = ema(c, 26)
    with np.errstate(invalid="ignore"):
        green = (fast > slow) & (c > fast); red = (fast < slow) & (c < fast)
        blue = (fast < slow) & (c > fast) & (c > slow)
        lblue = (fast < slow) & (c > fast) & (c < slow)
        orange = (fast > slow) & (c < fast) & (c < slow)
        yellow = (fast > slow) & (c < fast) & (c > slow)
    gp = np.roll(green, 1); gp[0] = False; rp = np.roll(red, 1); rp[0] = False
    buycond = green & ~gp; sellcond = red & ~rp
    bsb = barssince(buycond); bss = barssince(sellcond)
    with np.errstate(invalid="ignore"):
        bull = bsb < bss; bear = bss < bsb
    bull_p = np.roll(bull, 1); bull_p[0] = False; bear_p = np.roll(bear, 1); bear_p[0] = False
    return dict(ribbon_fast=fast, ribbon_slow=slow, ribbon_green=green, ribbon_red=red,
                ribbon_blue=blue, ribbon_lblue=lblue, ribbon_orange=orange, ribbon_yellow=yellow,
                ribbon_bull=bull, ribbon_bear=bear,
                ribbon_buy=bear_p & buycond, ribbon_sell=bull_p & sellcond)

#   3) RSI Reversal & Volume spike
def rsi_reversal(c, n=14, ob=75, os_=25):
    r = rsi(c, n); lvl_ob = np.full(len(c), ob); lvl_os = np.full(len(c), os_)
    return dict(rsi=r, reversal_down=crossover(r, lvl_ob), reversal_up=crossunder(r, lvl_os))

def volume_spike(o, c, v, lookback=100):
    hv = highest(v, lookback)
    with np.errstate(invalid="ignore"):
        return dict(bullish_volume=(v >= hv) & (c >= o), bearish_volume=(v >= hv) & (c < o))

#   4) Market Structure (BOS/CHoCH/CHoCH+) + Volumetric Order Blocks
#      + Premium/Discount (Zphl)   -- one stateful bar loop
class _MSArr:
    def __init__(self): self.p = []; self.n = []; self.l = []

class _OB:
    def __init__(self): self.top=[]; self.btm=[]; self.left=[]; self.avg=[]; self.cV=[]; self.dir=[]; self.dV=[]
    def remove(self, k):
        for a in (self.top, self.btm, self.left, self.avg, self.cV, self.dir): del a[k]

class SMCEngine:
    def __init__(self, p: HSNParams): self.p = p

    def run(self, o, h, l, c, v, last_bar_confirmed=True):
        p = self.p; n = len(c); iLen = p.internal_lookback; sLen = p.swing_lookback
        iH = ~np.isnan(pivothigh(h, iLen, iLen)); iL = ~np.isnan(pivotlow(l, iLen, iLen))
        sH = ~np.isnan(pivothigh(h, sLen, sLen)); sL = ~np.isnan(pivotlow(l, sLen, sLen))
        hl2 = (h + l) / 2; hlcc4 = (h + l + c + c) / 4; ohlc4 = (o + h + l + c) / 4
        pos = h if p.ob_pos == "Full" else ohlc4 if p.ob_pos == "Middle" else hl2   # per-side handled below
        up, dn, sup, sdn = _MSArr(), _MSArr(), _MSArr(), _MSArr()
        itrend = 0; trend = 0; xmem = {}
        hN = lN = hS = lS = 0
        obs = {"bull": _OB(), "bear": _OB(), "sbull": _OB(), "sbear": _OB()}
        hiS = highest(h, sLen); loS = lowest(l, sLen)
        zhl_out = NAN; topy = 0.0; bottomy = 0.0
        tup = h[0]; tdn = l[0]; tupx = 0; tdnx = 0; uV = NAN; dV = NAN

        keys = ["i_bull_bos","i_bull_choch","i_bull_chochp","i_bear_bos","i_bear_choch","i_bear_chochp",
                "s_bull_bos","s_bull_choch","s_bull_chochp","s_bear_bos","s_bear_choch","s_bear_chochp",
                "bull_ob","bear_ob","s_bull_ob","s_bear_ob","bull_ob_touch","bear_ob_touch"]
        out = {k: np.zeros(n, bool) for k in keys}
        itrend_a = np.zeros(n, int); trend_a = np.zeros(n, int)
        ms_level = np.full(n, NAN)
        bull_ob_top = np.full(n, NAN); bull_ob_btm = np.full(n, NAN)
        bear_ob_top = np.full(n, NAN); bear_ob_btm = np.full(n, NAN)
        tup_a = np.full(n, NAN); tdn_a = np.full(n, NAN)
        strong_high = np.zeros(n, bool); strong_low = np.zeros(n, bool)
        ms_events = []

        def xover(key, a, b):
            pa, pb = xmem.get(key, (NAN, NAN))
            r = (a > b) and (not isna(pa)) and (not isna(pb)) and pa <= pb
            xmem[key] = (a, b); return r
        def xunder(key, a, b):
            pa, pb = xmem.get(key, (NAN, NAN))
            r = (a < b) and (not isna(pa)) and (not isna(pb)) and pa >= pb
            xmem[key] = (a, b); return r
        def ob_allowed(txt):
            return p.ob_filter == "None" or p.ob_filter == txt

        def draw_vob(ob: _OB, cdn, bull, loc, i, confirmed):
            if cdn:
                hh, ll, nn = [], [], []
                for k in pine_range(1, abs(loc - i) - 1):
                    if i - k < 0: continue
                    hh.append(h[i - k]); ll.append(l[i - k]); nn.append(i - k)
                if not hh: return
                iU = ll.index(min(ll)) + 1; iD = hh.index(max(hh)) + 1
                bU, bD = i - iU, i - iD
                d = (1 if c[bU] > o[bU] else -1) if bull else (1 if c[bD] > o[bD] else -1)
                top = pos[bU] if bull else max(hh)
                btm = min(ll) if bull else pos[bD]
                left = nn[ll.index(min(ll))] if bull else nn[hh.index(max(hh))]
                avg = (top + btm) / 2; cV = v[bU] if bull else v[bD]
                if p.ob_pos == "Precise":
                    if bull:
                        if avg < min(c[bU], o[bU]) and top > hlcc4[bU]:
                            top = avg; avg = (top + btm) / 2
                    else:
                        ref = o[bD] if c[bU] < o[bU] else c[bD]   # literal quirk from Pine
                        if avg > ref and btm < hlcc4[bD]:
                            btm = avg; avg = (top + btm) / 2
                for a_, val in ((ob.top, top), (ob.btm, btm), (ob.left, left), (ob.avg, avg), (ob.cV, cV), (ob.dir, d)):
                    a_.insert(0, val)
                if p.use_overlap and len(ob.avg) > 1:
                    rmP = 1 if p.overlap_method == "Recent" else 0
                    if (ob.btm[0] < ob.top[1]) if bull else (ob.top[0] > ob.btm[1]):
                        ob.remove(rmP)
            if confirmed and ob.avg:
                tg = ob.avg if p.ob_mitigation == "Middle" else (ob.btm if bull else ob.top)
                keep = [k for k, pt in enumerate(tg) if not ((c[i] < pt) if bull else (c[i] > pt))]
                for k in reversed(range(len(tg))):
                    if k not in keep: ob.remove(k)
            touch = False
            if ob.avg:
                key = f"obt_{id(ob)}"
                touch = xunder(key, l[i], ob.top[0]) if bull else xover(key, h[i], ob.btm[0])
                tV = sum(ob.cV[:min(p.ob_num, len(ob.cV))])
                ob.dV = [int(np.floor(x / tV * 100)) if tV > 0 else 0 for x in ob.cV[:min(p.ob_num, len(ob.cV))]]
            return touch

        for i in range(n):
            confirmed = (i < n - 1) or last_bar_confirmed
            bull_ob = bear_ob = s_bull_ob = s_bear_ob = False
            # ---- Pine `switch` : only the FIRST true case executes ----
            if iH[i]:
                up.p.insert(0, h[i - iLen]); up.l.insert(0, h[i - iLen]); up.n.insert(0, i - iLen)
            elif iL[i]:
                dn.p.insert(0, l[i - iLen]); dn.l.insert(0, l[i - iLen]); dn.n.insert(0, i - iLen)
            elif sL[i]:
                sdn.p.insert(0, l[i - sLen]); sdn.l.insert(0, l[i - sLen]); sdn.n.insert(0, i - sLen)
            elif sH[i]:
                sup.p.insert(0, h[i - sLen]); sup.l.insert(0, h[i - sLen]); sup.n.insert(0, i - sLen)

            # ---- internal bullish ----
            if up.p and len(dn.l) > 1 and xover("ib", c[i], up.p[0]):
                if itrend >= 0: txt = "BOS"; out["i_bull_bos"][i] = True
                else:
                    txt = "CHoCH+" if dn.l[0] > dn.l[1] else "CHoCH"
                    out["i_bull_chochp" if txt == "CHoCH+" else "i_bull_choch"][i] = True
                bull_ob = ob_allowed(txt); ms_level[i] = up.p[0]
                ms_events.append(dict(bar=i, type=txt, side="bull", scope="internal", level=up.p[0], pivot_bar=up.n[0]))
                itrend = 1; up.n.clear(); up.p.clear()
            # ---- internal bearish ----
            if dn.p and len(up.l) > 1 and xunder("ibr", c[i], dn.p[0]):
                if itrend <= 0: txt = "BOS"; out["i_bear_bos"][i] = True
                else:
                    txt = "CHoCH+" if up.l[0] < up.l[1] else "CHoCH"
                    out["i_bear_chochp" if txt == "CHoCH+" else "i_bear_choch"][i] = True
                bear_ob = ob_allowed(txt); ms_level[i] = dn.p[0]
                ms_events.append(dict(bar=i, type=txt, side="bear", scope="internal", level=dn.p[0], pivot_bar=dn.n[0]))
                itrend = -1; dn.n.clear(); dn.p.clear()
            # ---- swing bullish ----
            if sup.p and len(sdn.l) > 1 and xover("sb", c[i], sup.p[0]):
                if trend >= 0: txt = "BOS"; out["s_bull_bos"][i] = True
                else:
                    txt = "CHoCH+" if sdn.l[0] > sdn.l[1] else "CHoCH"
                    out["s_bull_chochp" if txt == "CHoCH+" else "s_bull_choch"][i] = True
                s_bull_ob = ob_allowed(txt)
                ms_events.append(dict(bar=i, type=txt, side="bull", scope="swing", level=sup.p[0], pivot_bar=sup.n[0]))
                trend = 1; sup.n.clear(); sup.p.clear()
            # ---- swing bearish ----
            if sdn.p and len(sup.l) > 1 and xunder("sbr", c[i], sdn.p[0]):
                if trend <= 0: txt = "BOS"; out["s_bear_bos"][i] = True
                else:
                    txt = "CHoCH+" if sup.l[0] < sup.l[1] else "CHoCH"
                    out["s_bear_chochp" if txt == "CHoCH+" else "s_bear_choch"][i] = True
                s_bear_ob = ob_allowed(txt)
                ms_events.append(dict(bar=i, type=txt, side="bear", scope="swing", level=sdn.p[0], pivot_bar=sdn.n[0]))
                trend = -1; sdn.n.clear(); sdn.p.clear()
            itrend_a[i] = itrend; trend_a[i] = trend

            # ---- Premium / Discount (zhl + upphl/dnphl) ----
            if i >= sLen and not np.isnan(hiS[i]):
                prev = zhl_out
                zo = 0 if h[i - sLen] > hiS[i] else 1 if l[i - sLen] < loS[i] else prev
                top = h[i - sLen] if (zo == 0 and prev != 0) else 0
                btm = l[i - sLen] if (zo == 1 and prev != 1) else 0
                zhl_out = zo
                if top: topy = top; tup = top; tupx = i - sLen
                if btm: bottomy = btm; tdn = btm; tdnx = i - sLen
            tup_prev, tdn_prev = tup, tdn
            tup = max(h[i], tup); tupx = i if tup == h[i] else tupx
            uV = v[i] if tup != tup_prev else uV
            tdn = min(l[i], tdn); tdnx = i if tdn == l[i] else tdnx
            dV = v[i] if tdn != tdn_prev else dV
            tup_a[i] = tup; tdn_a[i] = tdn
            strong_high[i] = trend < 0; strong_low[i] = trend > 0

            # ---- Order blocks ----
            if iH[i]: hN = i - iLen
            if iL[i]: lN = i - iLen
            if sH[i]: hS = i - sLen
            if sL[i]: lS = i - sLen
            if p.ob_show:
                out["bull_ob_touch"][i] = bool(draw_vob(obs["bull"], bull_ob, True, hN, i, confirmed))
                out["bear_ob_touch"][i] = bool(draw_vob(obs["bear"], bear_ob, False, lN, i, confirmed))
            if p.ob_swings:
                draw_vob(obs["sbull"], s_bull_ob, True, hS, i, confirmed)
                draw_vob(obs["sbear"], s_bear_ob, False, lS, i, confirmed)
            out["bull_ob"][i] = bull_ob; out["bear_ob"][i] = bear_ob
            out["s_bull_ob"][i] = s_bull_ob; out["s_bear_ob"][i] = s_bear_ob
            if obs["bull"].top: bull_ob_top[i] = obs["bull"].top[0]; bull_ob_btm[i] = obs["bull"].btm[0]
            if obs["bear"].top: bear_ob_top[i] = obs["bear"].top[0]; bear_ob_btm[i] = obs["bear"].btm[0]

        out.update(itrend=itrend_a, swing_trend=trend_a, ms_level=ms_level,
                   bull_ob_top=bull_ob_top, bull_ob_btm=bull_ob_btm,
                   bear_ob_top=bear_ob_top, bear_ob_btm=bear_ob_btm,
                   range_top=tup_a, range_btm=tdn_a, strong_high=strong_high, strong_low=strong_low,
                   premium_low=0.95 * tup_a + 0.05 * tdn_a,
                   eq_top=0.525 * tup_a + 0.475 * tdn_a, eq_btm=0.525 * tdn_a + 0.475 * tup_a,
                   discount_high=0.95 * tdn_a + 0.05 * tup_a)
        zones = {}
        for k, ob in obs.items():
            zones[k] = [dict(top=ob.top[j], btm=ob.btm[j], avg=ob.avg[j], left_bar=ob.left[j],
                             volume=ob.cV[j], dir=ob.dir[j], vol_pct=(ob.dV[j] if j < len(ob.dV) else None))
                        for j in range(min(p.ob_num, len(ob.top)))]
        return out, dict(order_blocks=zones, ms_events=ms_events, high_vol=uV, low_vol=dV)

#   5) Supply & Demand
def supply_demand(h, l, c, v, swing_length=8, box_width=4.0):
    n = len(c); a50 = atr(h, l, c, 50)
    sh = pivothigh(h, swing_length, swing_length); sl = pivotlow(l, swing_length, swing_length)
    hv20 = highest(v, 20)
    supply: List[dict] = []; demand: List[dict] = []
    in_supply = np.zeros(n, bool); in_demand = np.zeros(n, bool)
    supply_break = np.zeros(n, bool); demand_break = np.zeros(n, bool)

    def overlapping(poi, boxes, a):
        thr = a * 2
        for b in boxes:
            if b["poi"] - thr <= poi <= b["poi"] + thr: return True
        return False

    def add(i, boxes, kind):
        a = a50[i]
        if np.isnan(a): return
        buf = a * (box_width / 15)
        if kind == 1: top = sh[i]; btm = top - buf
        else: btm = sl[i]; top = btm + buf
        poi = (top + btm) / 2
        if overlapping(poi, boxes, a): return
        vp = min(round(v[i - swing_length] / hv20[i] * 100), 100) if not np.isnan(hv20[i]) and hv20[i] > 0 else NAN
        if len(boxes) >= 16: del boxes[15:]
        boxes.insert(0, dict(top=top, btm=btm, poi=poi, left_bar=i - swing_length, created=i, vol_pct=vp))

    for i in range(n):
        if not np.isnan(sh[i]): add(i, supply, 1)
        elif not np.isnan(sl[i]): add(i, demand, -1)
        b0 = len(supply); supply[:] = [b for b in supply if not c[i] >= b["top"]]; supply_break[i] = len(supply) < b0
        b0 = len(demand); demand[:] = [b for b in demand if not c[i] <= b["btm"]]; demand_break[i] = len(demand) < b0
        if not np.isnan(sl[i]): add(i, demand, -1)   # duplicated block in the original
        if not np.isnan(sh[i]): add(i, supply, 1)
        in_supply[i] = any(b["btm"] <= h[i] <= b["top"] or b["btm"] <= c[i] <= b["top"] for b in supply)
        in_demand[i] = any(b["btm"] <= l[i] <= b["top"] or b["btm"] <= c[i] <= b["top"] for b in demand)
    return dict(in_supply=in_supply, in_demand=in_demand, supply_break=supply_break, demand_break=demand_break), \
           dict(supply=supply, demand=demand)

#   6) Support / Resistance (HSN Algo SR)
def support_resistance(h, l, c, strength=6, zone_width_pct=1.0, rb=10, prd=284, channel_w=10, only_last=True):
    n = len(c)
    phs = pivothigh(h, rb, rb); pls = pivotlow(l, rb, rb)
    hi_prd = highest(h, prd); lo_prd = lowest(l, prd)
    zone_perc = (highest(h, 300) - lowest(l, 300)) * zone_width_pct / 100
    highestph = np.full(n, NAN); lowestpl = np.full(n, NAN)
    hp = NAN; lp = NAN; levels = [NAN] * 21
    piv_bars = [i for i in range(n) if not (np.isnan(phs[i]) and np.isnan(pls[i]))]
    todo = set(piv_bars[-1:]) if only_last else set(piv_bars)
    mx = lambda *a: max(x for x in a if not isna(x)) if any(not isna(x) for x in a) else NAN
    mn = lambda *a: min(x for x in a if not isna(x)) if any(not isna(x) for x in a) else NAN
    for i in range(n):
        if i in todo:
            cw = (hi_prd[i] - lo_prd[i]) * channel_w / 100
            levels = [NAN] * 21; hp = lo_prd[i]; lp = hi_prd[i]; countpp = 0; aas = [True] * 41
            for x in range(prd + 1):
                k = i - x
                if k < 0: break
                ph, pl = phs[k], pls[k]
                if np.isnan(ph) and np.isnan(pl): continue
                hp = mx(hp, nz(ph, lo_prd[i]), nz(pl, lo_prd[i])); lp = mn(lp, nz(ph, hi_prd[i]), nz(pl, hi_prd[i]))
                countpp += 1
                if countpp > 40: break
                if aas[countpp]:
                    is_ph = not np.isnan(ph) and ph != 0
                    base = h[k - rb] if is_ph else l[k - rb]
                    upl, dnl = base + cw, base - cw
                    tmp = [True] * 41; cnt = 0; tpoint = 0
                    for xx in range(prd + 1):
                        kk = i - xx
                        if kk < 0: break
                        ph2, pl2 = phs[kk], pls[kk]
                        if np.isnan(ph2) and np.isnan(pl2): continue
                        chg = False; cnt += 1
                        if cnt > 40: break
                        if aas[cnt]:
                            if not np.isnan(ph2) and dnl <= h[kk - rb] <= upl: tpoint += 1; chg = True
                            if not np.isnan(pl2) and dnl <= l[kk - rb] <= upl: tpoint += 1; chg = True
                        if chg and cnt < 41: tmp[cnt] = False
                    if tpoint >= strength:
                        for g in range(41):
                            if not tmp[g]: aas[g] = False
                        if is_ph and countpp < 21: levels[countpp] = h[k - rb]
                        if (not np.isnan(pl) and pl != 0) and countpp < 21: levels[countpp] = l[k - rb]
        highestph[i] = hp; lowestpl[i] = lp
    lv = [x for x in levels if not isna(x) and x != 0]
    last_c = c[-1]
    return dict(sr_highest=highestph, sr_lowest=lowestpl), \
           dict(levels=[dict(price=x, kind="support" if last_c >= x else "resistance",
                             zone=(x - zone_perc[-1], x + zone_perc[-1])) for x in lv],
                highest_zone=(highestph[-1], zone_perc[-1]), lowest_zone=(lowestpl[-1], zone_perc[-1]))

#   7) Trendlines (breakouts "Br")
class _Line:
    __slots__ = ("x1", "y1", "x2", "y2")
    def __init__(s, x1, y1, x2, y2): s.x1, s.y1, s.x2, s.y2 = x1, y1, x2, y2
    def slope(s): return (s.y2 - s.y1) / (s.x2 - s.x1) if s.x2 != s.x1 else 0.0

def trendlines(h, l, c, trelen=7, space=0.5, show=True):
    n = len(c); ph = ~np.isnan(pivothigh(h, trelen, trelen)); pl = ~np.isnan(pivotlow(l, trelen, trelen))
    a200 = atr(h, l, c, 200)
    vol = lambda i: min(a200[i] * 0.1, c[i] * 0.001) if not np.isnan(a200[i]) else 0.0
    upbin, dnbin, upln, dnln = [], [], [], []
    broken = False; valid_up = False; valid_dn = False
    plup = np.zeros(n, bool); pldn = np.zeros(n, bool)

    def process(i, is_high):
        nonlocal broken, valid_up, valid_dn
        binn = upbin if is_high else dnbin; lines = upln if is_high else dnln
        src = h if is_high else l; oth = l if is_high else h
        binn.insert(0, (src[i - trelen], i - trelen))
        if len(binn) <= 1: return
        cur, bef = binn[0], binn[1]
        cond = cur[0] < bef[0] if is_high else cur[0] > bef[0]
        if not cond: return
        if broken: valid = True
        else:
            valid = False
            if len(binn) > 3:
                po, pc, now, late = binn[3], binn[2], binn[1], binn[0]
                if is_high: valid = now[0] < pc[0] and now[0] < po[0] and late[0] < pc[0] and late[0] < po[0]
                else:       valid = now[0] > pc[0] and now[0] > po[0] and late[0] > pc[0] and late[0] > po[0]
        if is_high: valid_up = valid
        else: valid_dn = valid
        if not (valid and show): return
        sgn = -1 if is_high else 1
        mk = lambda: [ _Line(bef[1], bef[0] + sgn * vol(i) * space, cur[1], cur[0] + sgn * vol(i) * space),
                       _Line(bef[1], bef[0], cur[1], cur[0]) ]
        lines[:] = mk(); ln = lines[1]; remove = False
        for k in pine_range(0, i - bef[1]):
            if i - k < 0: break
            s = ln.slope(); ln.x2 = i - k; ln.y2 -= s
            if (oth[i - k] > ln.y2) if is_high else (oth[i - k] < ln.y2): remove = True; break
        if remove: lines.clear(); binn.clear(); broken = True
        else: lines[:] = mk(); binn.clear(); broken = False

    for i in range(n):
        if ph[i]: process(i, True)
        if len(upln) > 1:
            btm, top = upln[0], upln[1]
            if l[i] > top.y2: upln.clear(); broken = True; upbin.clear(); plup[i] = True
            if len(upln) > 1:
                su, sd = top.slope(), btm.slope(); top.x2 = i; top.y2 += su; btm.x2 = i; btm.y2 += sd
        if pl[i]: process(i, False)
        if len(dnln) > 1:
            btm, top = dnln[0], dnln[1]
            if h[i] < btm.y2: dnln.clear(); broken = True; dnbin.clear(); pldn[i] = True
            if len(dnln) > 1:
                su, sd = top.slope(), btm.slope(); top.x2 = i; top.y2 += su; btm.x2 = i; btm.y2 += sd
    return dict(trendline_break_up=plup, trendline_break_down=pldn)

#   8) Master Pattern & Liquidity
def master_pattern(h, l, c, mintick=0.01, depth=3, deviation=1, backstep=1, max_bars=150,
                   show_minor_expansion=True, last_bar_confirmed=True):
    n = len(c); last_bar = n - 1
    lw = hg = 1; last_h = last_l = 1
    zz, yy = [], []
    bs_h = bs_l = bs_d = None
    highing_prev = lowing_prev = downn_prev = False
    minorBoxes = []; expansionLines = []; minorExp = []; check = []; checkMinor = []
    majorLines = []; majorType = []; majorRef = []; crossed = []
    lastMinorExp = 0
    confirm_a = np.zeros(n, bool); cross_a = np.zeros(n, bool); touch_a = np.zeros(n, bool)

    def update_exp(T, lines, clear, checktimes):
        size = len(lines)
        for x in range(size):
            if x < len(checktimes) and x < len(lines) and T > checktimes[x]:
                lines[x]["x2"] = T
                if clear: del lines[x]
    def high_off(i, T):
        x = 1; hi = h[i]; res = 0
        while i - x >= 0 and i - x >= T:
            if h[i - x] > hi: hi = h[i - x]; res = x
            x += 1
        return res
    def low_off(i, T):
        x = 1; lo = l[i]; res = 0
        while i - x >= 0 and i - x >= T:
            if l[i - x] < lo: lo = l[i - x]; res = x
            x += 1
        return res

    for i in range(n):
        confirmed = (i < n - 1) or last_bar_confirmed
        lw += 1; hg += 1
        if i >= depth - 1:
            p_lw = min(range(depth), key=lambda o_: (l[i - o_], o_))
            p_hg = min(range(depth), key=lambda o_: (-h[i - o_], o_))
            lowing = (lw == p_lw) or (l[i] - l[i - p_lw] > deviation * mintick)
            highing = (hg == p_hg) or (h[i - p_hg] - h[i] > deviation * mintick)
            lh = 0 if not highing_prev else (None if bs_h is None else bs_h + 1); bs_h = lh
            ll = 0 if not lowing_prev else (None if bs_l is None else bs_l + 1); bs_l = ll
            cond2 = not (lh is not None and ll is not None and lh > ll)
            bsd = 0 if cond2 else (None if bs_d is None else bs_d + 1); bs_d = bsd
            downn = bsd is not None and bsd >= backstep
            lower = i - lw >= 0 and l[i - lw] > l[i - p_lw]
            higher = i - hg >= 0 and h[i - hg] < h[i - p_hg]
            if lw != p_lw and (not downn_prev or lower): lw = p_lw if p_lw < hg else 0
            if hg != p_hg and (downn_prev or higher): hg = p_hg if p_hg < lw else 0
            x1 = lw if downn else hg
            y1 = (l[i - lw] if i - lw >= 0 else NAN) if downn else (h[i - hg] if i - hg >= 0 else NAN)
            if downn == downn_prev and zz: zz.pop(); yy.pop()
            if downn != downn_prev:
                if downn: last_h = hg
                else: last_l = lw
            zz.append(y1); yy.append(i - x1)
            downn_prev, highing_prev, lowing_prev = downn, highing, lowing
        # checkTrigger
        RES = False
        if len(zz) >= 4:
            v1, v2, v3, v4 = zz[-1], zz[-2], zz[-3], zz[-4]; POS = yy[-2]
            RES = (v1 < v2 and v1 > v3 and v4 > v2) or (v1 > v2 and v1 < v3 and v4 < v2)
            if RES and (last_bar - i <= max_bars):
                minorBoxes.append(dict(left=POS, right=i, top=max(v1, v2), bottom=min(v1, v2),
                                       name="Active Box", ch=False, cl=False, major=False))
        update_exp(i, expansionLines, False, check); update_exp(i, minorExp, False, checkMinor)
        # operateMinorBox
        confirm = False
        if minorBoxes:
            bx = minorBoxes[-1]
            if bx["name"] != "NULL":
                top, bottom, t1, t2 = bx["top"], bx["bottom"], bx["left"], bx["right"]; ppp = bottom + (top - bottom) / 2
                oCH, oCL = bx["ch"], bx["cl"]
                if not bx["ch"] and not bx["cl"]:
                    if confirmed:
                        if c[i] > top: bx["ch"] = True
                        if c[i] < bottom: bx["cl"] = True
                    else:
                        if h[i] > top: bx["ch"] = True
                        if l[i] < bottom: bx["cl"] = True
                if bx["ch"] and bx["cl"]:
                    bx["name"] = "NULL"; bx["major"] = True
                    update_exp(t2, expansionLines, True, check); confirm = True
                    if show_minor_expansion: update_exp(t2, minorExp, True, checkMinor)
                    expansionLines.append(dict(x1=t2, y1=ppp, x2=i, y2=ppp)); check.append(t2)
                    hi_pos, lo_pos = high_off(i, t2), low_off(i, t2)
                    if not oCH:
                        r = l[i - lo_pos]; majorLines.append(dict(x1=i - lo_pos, y1=r, x2=i, y2=r)); majorType.append(0)
                    elif not oCL:
                        r = h[i - hi_pos]; majorLines.append(dict(x1=i - hi_pos, y1=r, x2=i, y2=r)); majorType.append(1)
                    majorRef.append(t2); crossed.append(False)
                elif not bx["ch"] and not bx["cl"]:
                    bx["right"] = i
                elif show_minor_expansion and t1 != lastMinorExp:
                    update_exp(t2, minorExp, True, checkMinor)
                    minorExp.append(dict(x1=t2, y1=ppp, x2=i, y2=ppp)); checkMinor.append(t2); lastMinorExp = t1
        confirm_a[i] = confirm
        # checkCross
        if i > 0:
            for ln in expansionLines:
                P = ln["y1"]
                if (c[i] > P and c[i - 1] <= P) or (c[i] < P and c[i - 1] >= P): cross_a[i] = True; break
        # operateLiquidity
        res = False
        if majorLines and len(majorLines) == len(majorType) == len(majorRef) == len(crossed):
            z = len(majorLines) - 1
            for x in range(z + 1):
                lp_ = majorLines[x]["y2"]; hi_pos = high_off(i, majorRef[x]); lo_pos = low_off(i, majorRef[x])
                if majorType[x] == 0 and l[i] <= lp_:
                    if not crossed[x]: res = True
                    qq = h[i - hi_pos]
                    if x == z: majorLines[x] = dict(x1=i - hi_pos, y1=qq, x2=i, y2=qq); majorType[x] = 1
                    else: crossed[x] = True
                elif majorType[x] == 1 and h[i] >= lp_:
                    if not crossed[x]: res = True
                    qq = l[i - lo_pos]
                    if x == z: majorLines[x] = dict(x1=i - lo_pos, y1=qq, x2=i, y2=qq); majorType[x] = 0
                    else: crossed[x] = True
                if not crossed[x]: majorLines[x]["x2"] = i
        touch_a[i] = res
    return dict(major_line_confirm=confirm_a, major_line_cross=cross_a, liquidity_line_touch=touch_a), \
           dict(boxes=minorBoxes, expansion_lines=expansionLines, minor_expansion_lines=minorExp,
                liquidity_lines=[dict(**majorLines[k], side="buy" if majorType[k] == 0 else "sell", crossed=crossed[k])
                                 for k in range(len(majorLines))])

#   9) Higher-timeframe levels (PDH/PDL, PWH/PWL, PMH/PML, PYH/PYL)
def htf_levels(df):
    """Previous completed period high/low, needs DatetimeIndex. Mirrors ta.valuewhen(h != h[1], h, 1)."""
    out = {}
    if not isinstance(df.index, pd.DatetimeIndex): return out
    for name, rule in (("pd", "1D"), ("pw", "1W"), ("pm", "1MS"), ("py", "1YS")):
        g = df.resample(rule).agg(high=("high", "max"), low=("low", "min")).dropna()
        prev = g.shift(1)
        out[name + "h"] = prev["high"].reindex(df.index, method="ffill").to_numpy()
        out[name + "l"] = prev["low"].reindex(df.index, method="ffill").to_numpy()
    return out

def mtf_trends(df, p: HSNParams, rules=("5min", "15min", "30min", "60min", "240min", "1D", "1W")):
    """itrend of structure(true) on other timeframes (request.security equivalent)."""
    res = {}
    if not isinstance(df.index, pd.DatetimeIndex): return res
    for r in rules:
        g = df.resample(r).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                               close=("close", "last"), volume=("volume", "sum")).dropna()
        if len(g) < p.internal_lookback * 2 + 2: continue
        o_, h_, l_, c_, v_ = (g[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
        out, _ = SMCEngine(p).run(o_, h_, l_, c_, v_)
        res["itrend_" + r] = pd.Series(out["itrend"], index=g.index).reindex(df.index, method="ffill").to_numpy()
    return res


def compute_hsn(df: pd.DataFrame, p: HSNParams = HSNParams(), last_bar_confirmed=True,
                with_mtf=False, sr_only_last=True):
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    cols = {}; objs = {}
    cols.update(hsn_trend_signal(h, l, c, p.st_multiplier, p.st_periods))
    cols.update(ribbon_signals(c))
    cols.update(rsi_reversal(c, p.rsi_len, p.rsi_ob, p.rsi_os))
    cols.update(volume_spike(o, c, v, p.vol_lookback))
    smc, smc_obj = SMCEngine(p).run(o, h, l, c, v, last_bar_confirmed); cols.update(smc); objs.update(smc_obj)
    sd, sd_obj = supply_demand(h, l, c, v, p.sd_swing_length, p.sd_box_width); cols.update(sd); objs["supply_demand"] = sd_obj
    sr, sr_obj = support_resistance(h, l, c, p.sr_strength, p.sr_zone_width_pct, only_last=sr_only_last); cols.update(sr); objs["sr"] = sr_obj
    cols.update(trendlines(h, l, c, p.trelen, p.tl_space, p.show_trendlines))
    mp, mp_obj = master_pattern(h, l, c, p.mintick, 2 if p.mp_indi_type == 2 else 3, 1, 1, p.mp_max_bars,
                                p.mp_show_minor_expansion, last_bar_confirmed); cols.update(mp); objs["master_pattern"] = mp_obj
    cols.update(htf_levels(df))
    if with_mtf: cols.update(mtf_trends(df, p))
    cols["vwma20"] = vwma(c, v, 20)
    res = pd.DataFrame(cols, index=df.index)
    return res, objs

class HSNLive:
    """
    Feed candles as they update. Pine recalculates the whole script on every tick of the
    forming bar and 'commits' state only on bar close -> we do the same by recomputing on
    each update; signals flagged on the forming bar are provisional until is_closed=True.
    """
    ALERT_COLS = ["buy", "sell", "reversal_up", "reversal_down", "ribbon_buy", "ribbon_sell",
                  "i_bull_bos", "i_bull_choch", "i_bull_chochp", "i_bear_bos", "i_bear_choch", "i_bear_chochp",
                  "s_bull_bos", "s_bull_choch", "s_bull_chochp", "s_bear_bos", "s_bear_choch", "s_bear_chochp",
                  "bull_ob", "bear_ob", "bull_ob_touch", "bear_ob_touch", "supply_break", "demand_break",
                  "trendline_break_up", "trendline_break_down", "bullish_volume", "bearish_volume",
                  "major_line_confirm", "major_line_cross", "liquidity_line_touch"]

    def __init__(self, history: pd.DataFrame, params: HSNParams = HSNParams(), max_bars=3000, callback=None):
        self.p = params; self.max_bars = max_bars; self.cb = callback
        self.df = history.copy().iloc[-max_bars:]
        self.result = None; self.objects = None

    def on_candle(self, ts, o, h, l, c, v, is_closed: bool):
        row = pd.DataFrame([[o, h, l, c, v]], columns=["open", "high", "low", "close", "volume"], index=[ts])
        if len(self.df) and self.df.index[-1] == ts:
            self.df.iloc[-1] = row.iloc[0]          # update forming bar
        else:
            self.df = pd.concat([self.df, row]).iloc[-self.max_bars:]   # new bar
        self.result, self.objects = compute_hsn(self.df, self.p, last_bar_confirmed=is_closed)
        last = self.result.iloc[-1]
        fired = [k for k in self.ALERT_COLS if k in last and bool(last[k])]
        state = dict(time=ts, close=c, confirmed=is_closed, alerts=fired,
                     trend=int(last["trend"]), st_up=last["st_up"], st_dn=last["st_dn"],
                     itrend=int(last["itrend"]), swing_trend=int(last["swing_trend"]),
                     zone=("premium" if c >= last["premium_low"] else "discount" if c <= last["discount_high"]
                           else "equilibrium" if last["eq_btm"] <= c <= last["eq_top"] else "mid"))
        if self.cb: self.cb(state)
        return state