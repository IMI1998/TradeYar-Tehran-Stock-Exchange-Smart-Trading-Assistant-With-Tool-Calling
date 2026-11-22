import os, json
from backend.indicators.registry import list_indicators, get_indicator, scan, plugin_errors
from backend.engine import analytics

PLAN = lambda: os.getenv("USER_PLAN", "free")

def _add_desc():
    names = [i["name"] for i in list_indicators(PLAN()) if i["available"]]
    return f"اندیکاتور را روی چارت می‌گذارد. name دقیقاً یکی از: {names}. params اختیاری مثل {{\"length\": 14}}"

def build_tools():
    """هر بار قبل از فراخوانی LLM ساخته می‌شود تا لیست اندیکاتورها به‌روز باشد"""
    return [
        {"name": "search_symbol", "description": "جستجوی نماد بورس ایران با نام فارسی",
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "set_symbol", "description": "سهم فعال چارت را عوض می‌کند (نام فارسی مثل فولاد)",
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "set_timeframe", "description": "D یا 5min/15min/30min/1h",
         "input_schema": {"type": "object", "properties": {"timeframe": {"type": "string"}}, "required": ["timeframe"]}},
        {"name": "list_indicators", "description": "لیست اندیکاتورهای موجود (رایگان/پریمیوم) و فعال روی چارت",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "add_indicator", "description": _add_desc(),
         "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "params": {"type": "object"}}, "required": ["name"]}},
        {"name": "remove_indicator", "description": "حذف اندیکاتور با id مثل RSI#1",
         "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
        {"name": "reload_plugins", "description": "اسکن مجدد پوشه‌ی پلاگین‌ها؛ اگر اندیکاتوری که کاربر می‌گوید در لیست نبود صدا بزن",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_snapshot", "description": "وضعیت کامل چارت + مقادیر/سیگنال‌های همه‌ی اندیکاتورها. قبل از هر تحلیل صدا بزن",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_indicator_summary", "description": "خلاصه‌ی ساختاریافته‌ی اندیکاتورها؛ برای HSN Algo: روند، BOS/CHoCH، اردر بلاک، عرضه/تقاضا، S/R، لیکوییدیتی، premium/discount، هشدارهای الان. قبل از پلن معامله حتماً",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_money_flow", "description": "ورود/خروج پول حقیقی، سرانه، قدرت خریدار",
         "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "default": 20}}}},
        {"name": "get_orderbook", "description": "عمق بازار + وضعیت صف",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "find_levels", "description": "حمایت/مقاومت از پیوت‌ها، ATR، سقف/کف ۲۰ کندل",
         "input_schema": {"type": "object", "properties": {}}},
    ]


async def execute(name, args, session, src):
    if name == "search_symbol":
        return {"results": await src.search(args["query"])}
    if name == "set_symbol":
        res = await src.search(args["query"])
        if not res: return {"error": "نمادی پیدا نشد"}
        pick = next((r for r in res if r["active"]), res[0])
        session.set_symbol(pick["ins_code"], pick["symbol"]); await session.refresh()
        return {"ok": True, "selected": pick}
    if name == "set_timeframe":
        session.set_timeframe(args["timeframe"]); await session.refresh()
        return {"ok": True, "bars": int(len(session.df)) if session.df is not None else 0}
    if name == "list_indicators":
        return {"plan": PLAN(), "indicators": list_indicators(PLAN()), "active": session.config()["indicators"], "plugin_errors": plugin_errors()}
    if name == "add_indicator":
        try: cls = get_indicator(args["name"])
        except KeyError as e: return {"error": str(e), "hint": "اسم را از list_indicators بردار یا reload_plugins بزن"}
        if cls.premium and PLAN() != "premium":
            return {"error": f"{cls.name} فقط در پلن پریمیوم فعال است؛ به کاربر بگو اشتراک بگیرد"}
        iid = session.add_indicator(args["name"], args.get("params")); await session.refresh()
        return {"ok": True, "id": iid, "active": session.config()["indicators"], "summary": session.summaries().get(iid)}
    if name == "remove_indicator":
        return {"ok": session.remove_indicator(args["id"]), "active": session.config()["indicators"]}
    if name == "reload_plugins":
        ch = scan(force=True); session.refresh_classes(); return ch
    if name == "get_snapshot":
        if session.df is None: await session.refresh()
        return analytics.snapshot(session)
    if name == "get_indicator_summary":
        if session.df is None: await session.refresh()
        return session.summaries()
    if name == "get_money_flow":
        ct = await src.client_type_history(session.ins, int(args.get("days", 20) or 20))
        return analytics.money_flow(ct, session._hist if session._hist is not None else session.df)
    if name == "get_orderbook":
        ob = await src.orderbook(session.ins)
        last = float(session.df.close.iloc[-1]) if session.df is not None else 0
        return {"depth": ob, "status": analytics.queue_status(ob, session.info, last)}
    if name == "find_levels":
        if session.df is None: await session.refresh()
        return analytics.find_levels(session.df)
    return {"error": f"ابزار ناشناخته: {name}"}