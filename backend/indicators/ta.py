"""معادل‌های Pine Script ta.* — برای پورت آسان اندیکاتورها"""
import numpy as np
import pandas as pd


def sma(s, n): return s.rolling(n).mean()
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rma(s, n): return s.ewm(alpha=1 / n, adjust=False).mean()
def stdev(s, n): return s.rolling(n).std(ddof=0)
def highest(s, n): return s.rolling(n).max()
def lowest(s, n): return s.rolling(n).min()
def change(s, n=1): return s.diff(n)
def nz(s, v=0): return s.fillna(v)


def rsi(s, n=14):
    d = s.diff()
    up, dn = rma(d.clip(lower=0), n), rma(-d.clip(upper=0), n)
    r = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    # صف/روز بدون نوسان: مخرج صفر می‌شود و RSI قبلاً کامل NaN بود (پنل خالی)
    r = r.mask((dn == 0) & (up > 0), 100.0)
    return r.mask((dn == 0) & (up == 0), 50.0)


def macd(s, fast=12, slow=26, sig=9):
    m = ema(s, fast) - ema(s, slow)
    sl = ema(m, sig)
    return m, sl, m - sl


def bbands(s, n=20, mult=2.0):
    mid = sma(s, n); sd = stdev(s, n)
    return mid + mult * sd, mid, mid - mult * sd


def atr(df, n=14):
    tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    return rma(tr, n)


def crossover(a, b):
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a > b) & (a.shift() <= b.shift())


def crossunder(a, b):
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a < b) & (a.shift() >= b.shift())