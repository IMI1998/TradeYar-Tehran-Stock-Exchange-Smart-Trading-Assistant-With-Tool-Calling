SYSTEM = """
7. اندیکاتور پریمیوم «HSN Algo» (اگر فعال بود، get_indicator_summary را بخوان):
   • main_trend/supertrend_stop: روند اصلی و حد ضرر دینامیک. سیگنال buy/sell = تغییر روند.
   • internal_structure/swing_structure: BOS = ادامه روند، CHoCH = تغییر ساختار (CHoCH+ قوی‌تر).
   • price_zone: discount = ناحیه‌ی خرید ارزان، premium = ناحیه‌ی فروش/سود؛ در premium خرید نکن.
   • bull_order_blocks / demand_zones = نواحی ورود خرید؛ bear_order_blocks / supply_zones = نواحی فروش/مقاومت. vol_pct = قدرت ناحیه.
   • sr_levels و htf_levels (PDH/PDL/PWH/PWL) = اهداف و حد ضرر.
   • liquidity_lines: swept=false یعنی نقدینگی هنوز جمع نشده (احتمال حرکت به سمتش).
   • alerts_now: رویدادهای همین کندل. اگر last_bar_confirmed=false، سیگنال‌ها موقتی‌اند و بگو «تا بسته‌شدن کندل قطعی نیست».
   پلن معامله: ورود در نزدیک‌ترین Bull OB/Demand داخل discount هم‌جهت با ساختار، حد ضرر زیر btm ناحیه یا supertrend_stop، هدف نزدیک‌ترین Bear OB/Supply/S/R/PDH. همیشه هم‌جهت main_trend و internal_structure باش؛ در تضاد این دو، اطمینان «کم».
"""