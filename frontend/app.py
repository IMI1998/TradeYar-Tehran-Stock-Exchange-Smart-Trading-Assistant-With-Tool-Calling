import sys, json
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
import streamlit.components.v1 as components
from config import BACKEND_URL, BACKEND_WS
from api_client import API
from chart_component import chart_html

st.set_page_config(page_title="TSE Copilot", layout="wide", initial_sidebar_state="expanded")
st.markdown("<style>.block-container{padding-top:1rem;padding-bottom:0}</style>", unsafe_allow_html=True)

api = API(BACKEND_URL)
SID = "main"

try:
    cfg = api.config(SID)
except Exception:
    st.error("بک‌اند در دسترس نیست. اول `uvicorn backend.main:app` را اجرا کن.")
    st.stop()

# ───────────────────────── Sidebar ─────────────────────────
with st.sidebar:
    st.title("📈 TSE Copilot")
    st.caption(f"نماد فعال: **{cfg['symbol']}** · تایم‌فریم: `{cfg['timeframe']}`")

    st.subheader("نماد")
    q = st.text_input("جستجو", placeholder="فولاد، خودرو، شپنا …")
    if q:
        res = api.search(q)
        if res:
            opt = st.selectbox("نتایج", res, format_func=lambda r: f"{r['symbol']} — {r['name']}" + ("" if r["active"] else " (غیرفعال)"))
            if st.button("باز کردن روی چارت", use_container_width=True):
                api.set_symbol(SID, opt["ins_code"], opt["symbol"]); st.rerun()
        else:
            st.info("چیزی پیدا نشد")

    tf = st.selectbox("تایم‌فریم", ["D", "5min", "15min", "30min", "1h"], index=["D", "5min", "15min", "30min", "1h"].index(cfg["timeframe"]))
    if tf != cfg["timeframe"]:
        api.set_tf(SID, tf); st.rerun()

    st.subheader("اندیکاتورها")
    resp = api.indicators()                       # حالا {"plan","items","errors"}
    all_inds, plan = resp["items"], resp["plan"]
    st.caption(f"پلن: **{plan}** · پلاگین‌ها از `backend/indicators/plugins/` خودکار لود می‌شوند")
    if resp.get("errors"):
        for f, e in resp["errors"].items(): st.error(f"{f}: {e}")
    avail = [i for i in all_inds if i["available"]]
    pick = st.selectbox("اضافه کردن", avail, format_func=lambda i: ("⭐ " if i["premium"] else "") + i["name"])
    params_txt = st.text_input("پارامترها (JSON)", value=json.dumps(pick["inputs"]), key=f"p_{pick['name']}")
    c1, c2 = st.columns(2)
    if c1.button("➕ افزودن", use_container_width=True):
        try: api.add_ind(SID, pick["name"], json.loads(params_txt or "{}")); st.rerun()
        except Exception as e: st.error(str(e))
    if c2.button("🔄 اسکن پلاگین‌ها", use_container_width=True):
        st.toast(str(api._r("POST", "/indicators/reload"))); st.rerun()
    for i in all_inds:
        if not i["available"]:
            st.button(f"🔒 {i['name']} (پریمیوم)", disabled=True, use_container_width=True)

    active = cfg.get("indicators") or []
    st.subheader(f"روی چارت ({len(active)})")
    if not active:
        st.caption("هیچ اندیکاتوری اضافه نشده.")
    for ind in active:
        c1, c2 = st.columns([4, 1])
        with c1:
            st.markdown(f"**{ind['name']}**" + (" ⭐" if ind.get("premium") else "") + f" · `{ind['id']}`")
            st.caption(json.dumps(ind["params"], ensure_ascii=False))
        if c2.button("🗑", key=f"del_{ind['id']}", help="حذف از چارت", use_container_width=True):
            try:
                api.del_ind(SID, ind["id"]); st.rerun()
            except Exception as e:
                st.error(str(e))

    st.subheader("⚙️ مدل هوش مصنوعی")
    try:
        llm_def = api.llm_defaults()
    except Exception:
        llm_def = {"base_url": "", "model": ""}
    st.session_state.setdefault("llm_base_url", llm_def["base_url"])
    st.session_state.setdefault("llm_model", llm_def["model"])
    base_url = st.text_input("Base URL", key="llm_base_url", placeholder="https://api.openai.com/v1")
    api_key = st.text_input("API Key", key="llm_api_key", type="password", placeholder="کلید خودت را اینجا بگذار")
    model_id = st.text_input("Model ID", key="llm_model", placeholder="gpt-4.1-mini")
    st.caption("هر کسی با مشخصات خودش کار می‌کند؛ خالی بماند، مقدار `.env` سرور استفاده می‌شود.")

# ───────────────────────── Main: یک ستون، دو ردیف ─────────────────────────
# ردیف ۱ — چارت
components.html(chart_html(f"{BACKEND_WS}/ws/{SID}", height=640), height=650)

st.divider()

# ردیف ۲ — دستیار (tool calling + تحلیل قیمت)
st.subheader("🤖 دستیار تریدر")
if "msgs" not in st.session_state:
    st.session_state.msgs = [{"role": "assistant", "content": "سلام! مثلاً بنویس: «MACD و EMA Cross بذار و بگو فولاد الان چه وضعیه، کجا بخرم کجا بفروشم»"}]

box = st.container(height=460, border=True)
for m in st.session_state.msgs:
    with box.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("trace"):
            with st.expander(f"🔧 {len(m['trace'])} فراخوانی ابزار"):
                for t in m["trace"]:
                    st.markdown(f"**{t['tool']}** `{json.dumps(t['input'], ensure_ascii=False)}`")
                    st.code(t["output"], language="json")

if prompt := st.chat_input("پیام به دستیار…"):
    st.session_state.msgs.append({"role": "user", "content": prompt})
    with box.chat_message("user"):
        st.markdown(prompt)
    with box.chat_message("assistant"):
        with st.spinner("در حال تحلیل…"):
            try:
                out = api.chat(SID, prompt, {"base_url": base_url, "api_key": api_key or None, "model": model_id})
                st.markdown(out["reply"])
                st.session_state.msgs.append({"role": "assistant", "content": out["reply"], "trace": out.get("trace", [])})
            except Exception as e:
                st.error(str(e))
    st.rerun()  # تا سایدبار با تغییرات LLM (نماد/اندیکاتور) سینک شود