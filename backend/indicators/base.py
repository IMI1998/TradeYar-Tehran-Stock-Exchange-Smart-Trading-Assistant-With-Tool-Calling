import pandas as pd


class Indicator:
    """
    calc(df, p, confirmed) برمی‌گرداند:
      plots:    {"نام": Series}                          مثل plot()
      signals:  {"buy": bool Series, "ribbon_buy": ...}  مثل plotshape()
      levels:   [30, 70]                                 مثل hline()
      zones:    [{"top","btm","from"(Timestamp),"to","color","label","extend"}]  مثل box
      lines:    [{"price","from","to","color","label","style"}]                 مثل line
      summary:  dict                                    خلاصه‌ی ساختاریافته برای LLM
    """
    name: str = ""
    description: str = ""
    overlay: bool = False
    inputs: dict = {}
    colors: dict = {}
    premium: bool = False
    heavy: bool = False            # محاسبات سنگین → خود اندیکاتور کش می‌کند
    signal_styles: dict = {}       # {"ribbon_buy": {"shape":"circle","color":"#42a5f5","position":"belowBar","text":"R"}}

    def calc(self, df: pd.DataFrame, p: dict, confirmed: bool = True) -> dict:
        raise NotImplementedError