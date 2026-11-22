<div dir="rtl" align="right">

# 📈 TSE Copilot — دستیار معاملاتی هوشمند بورس تهران

**چارت زندهٔ بازار + اندیکاتورهای قابل توسعه + تحلیل گفت‌وگویی با مدل زبانی**

یک داشبورد سبک و کامل برای رصد لحظه‌ای نمادهای بورس تهران (TSETMC) که چارت کندل‌استیک را از دادهٔ واقعی می‌سازد، اندیکاتورهای تکنیکال را روی آن اجرا می‌کند و در همان صفحه یک دستیار هوش مصنوعی دارد که با **Tool Calling** واقعی همان چارت را می‌خواند، نماد و تایم‌فریم را عوض می‌کند و اندیکاتور اضافه یا حذف می‌کند.

<br>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)
![Data](https://img.shields.io/badge/Data-TSETMC%20(live)-0A7D32)
![License](https://img.shields.io/badge/License-MIT-blue)

</div>

---

<div dir="rtl" align="right">

## ✨ چه کاری انجام می‌دهد؟

| قابلیت | توضیح |
| --- | --- |
| 🔴 دادهٔ زندهٔ TSETMC | قیمت، حجم، ارزش، سرانهٔ خرید/فروش، عمق بازار و ریزمعامله‌ها مستقیم از `cdn.tsetmc.com` |
| 🕯️ چارت کندل‌استیک | رندر سبک با **lightweight-charts** روی WebSocket؛ بدون رفرش صفحه به‌روز می‌شود |
| ⏱️ چند تایم‌فریم | `D` (روزانه) و `5min` / `15min` / `30min` / `1h` با آرشیو محلی کندل‌های درون‌روزی |
| 🧮 اندیکاتورهای افزونه‌ای | RSI، MACD، EMA، EMA Cross، Bollinger و **HSN Algo** (ساختار بازار، BOS/CHoCH، اردربلاک، لیکوییدیتی، پرمیوم/دیسکانت) |
| 🤖 دستیار LLM با ابزار | مدل زبانی خودش `get_snapshot`، `get_money_flow`، `get_orderbook`، `find_levels` و … را صدا می‌زند و بر اساس دادهٔ واقعی تحلیل می‌دهد |
| 🔑 تنظیمات مدل به‌ازای هر کاربر | `Base URL` / `API Key` / `Model ID` در سایدبار؛ هر کس با کلید و مدل خودش کار می‌کند |
| 🧹 مدیریت اندیکاتورها | فهرست اندیکاتورهای فعال روی چارت با پارامترها و دکمهٔ حذف، تا چارت شلوغ نشود |
| 🧩 پلاگین‌محور | هر اندیکاتور یک کلاس در `backend/indicators/plugins` است؛ اضافه‌کردن اندیکاتور جدید بدون دست‌زدن به هسته |

</div>

---

<div dir="rtl" align="right">

## 🏗️ معماری

</div>

```text
┌─────────────────────────────┐        HTTP / WS        ┌──────────────────────────────┐
│  Frontend — Streamlit       │  ───────────────────▶   │  Backend — FastAPI           │
│  • چارت lightweight-charts  │                         │  • Session / Poller          │
│  • سایدبار تنظیمات + LLM    │  ◀───────────────────   │  • Indicator Registry        │
│  • چت دستیار                │        JSON / WS         │  • Agent Runner (tool calls) │
└─────────────────────────────┘                         └───────────────┬──────────────┘
                                                                        │ httpx
                                                                ┌───────▼────────┐
                                                                │  TSETMC CDN    │
                                                                │  (دادهٔ زنده)  │
                                                                └────────────────┘
```

<div dir="rtl" align="right">

- **بک‌اند** مسئول داده، سشن، اندیکاتورها و فراخوانی مدل زبانی است.
- **فرانت** هیچ منطق تحلیلی ندارد؛ فقط نمایش و تعامل.
- **کلید API** فقط در حافظهٔ همان درخواست استفاده می‌شود و در سرور ذخیره یا لاگ نمی‌شود.

</div>

---

<div dir="rtl" align="right">

## 🚀 نصب و اجرا

### ۱) پیش‌نیاز

- Python **3.10** یا بالاتر
- دسترسی شبکه به `cdn.tsetmc.com`

### ۲) نصب وابستگی‌ها

</div>

```bash
git clone https://github.com/IMI1998/TradeYar-.git
cd TradeYar-

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

<div dir="rtl" align="right">

### ۳) تنظیمات محیطی

فایل نمونه را کپی کنید و مقادیر خودتان را بگذارید:

</div>

```bash
cp .env.example .env
```

<div dir="rtl" align="right">

| متغیر | پیش‌فرض | توضیح |
| --- | --- | --- |
| `BACKEND_URL` | `http://localhost:8000` | آدرس REST بک‌اند |
| `BACKEND_WS` | `ws://localhost:8000` | آدرس WebSocket چارت |
| `POLL_INTERVAL` | `3` | فاصلهٔ پولینگ داده (ثانیه) |
| `DEMO_MODE` | `0` | با `1` دادهٔ ساختگی به‌جای TSETMC |
| `DEFAULT_SYMBOL` | `فولاد` | نماد پیش‌فرض هنگام ساخت سشن |
| `LLM_BASE_URL` | — | آدرس سازگار با OpenAI (هر ارائه‌دهنده‌ای) |
| `LLM_API_KEY` | — | کلید پیش‌فرض؛ در سایدبار هم قابل جایگزینی است |
| `LLM_MODEL` | — | شناسهٔ مدل، مثل `gpt-oss-120b` |

> 💡 اگر از پروکسی/VPN استفاده می‌کنید و دریافت داده از TSETMC شکست می‌خورد، بک‌اند را با `NO_PROXY=cdn.tsetmc.com` اجرا کنید.

### ۴) اجرا

**الف) هر دو سرویس با یک دستور**

</div>

```bash
chmod +x run.sh && ./run.sh
```

<div dir="rtl" align="right">

**ب) یا جداگانه (مناسب توسعه)**

</div>

```bash
# ترمینال ۱ — بک‌اند
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# ترمینال ۲ — فرانت
streamlit run frontend/app.py --server.port 8501
```

<div dir="rtl" align="right">

سپس در مرورگر: **http://localhost:8501**

</div>

---

<div dir="rtl" align="right">

## 🖥️ رابط کاربری

صفحه یک‌ستونه و دو‌ردیفی است:

1. **ردیف بالا — چارت:** نماد، قیمت پایانی/آخرین، درصد تغییر روز، کندل‌ها، حجم و اندیکاتورهای فعال.
2. **ردیف پایین — دستیار:** گفت‌وگو با مدل زبانی که به ابزارهای زندهٔ چارت دسترسی دارد.

در سایدبار:

- انتخاب **نماد** و **تایم‌فریم** (`D`، `5min`، `15min`، `30min`، `1h`)
- بخش **⚙️ مدل هوش مصنوعی**: `Base URL`، `API Key`، `Model ID` — مخصوص همان کاربر
- بخش **روی چارت (n)**: نام، شناسه، پارامتر و دکمهٔ 🗑 هر اندیکاتور فعال
- افزودن اندیکاتور جدید از فهرست پلاگین‌های موجود

</div>

---

<div dir="rtl" align="right">

## 🔌 API — مرور سریع

| متد | مسیر | کار |
| --- | --- | --- |
| `GET` | `/health` | سلامت سرویس، حالت دمو و پلن |
| `GET` | `/symbols/search?q=فولاد` | جست‌وجوی نماد |
| `GET` | `/indicators` | فهرست اندیکاتورهای موجود و فعال |
| `POST` | `/indicators/reload` | اسکن مجدد پوشهٔ پلاگین‌ها |
| `POST` | `/session` | ساخت سشن چارت |
| `GET` | `/session/{sid}` | تنظیمات سشن |
| `POST` | `/session/{sid}/symbol` | تغییر نماد |
| `POST` | `/session/{sid}/timeframe` | تغییر تایم‌فریم |
| `POST` | `/session/{sid}/indicators` | افزودن اندیکاتور |
| `DELETE` | `/session/{sid}/indicators/{iid}` | حذف اندیکاتور |
| `GET` | `/session/{sid}/snapshot` | وضعیت کامل چارت + مقادیر اندیکاتورها |
| `GET` | `/session/{sid}/summary` | خلاصهٔ ساختاریافتهٔ اندیکاتورها |
| `POST` | `/session/{sid}/chat` | پرسش از دستیار (با تنظیمات LLM اختیاری) |
| `GET` | `/llm` | پیش‌فرض‌های مدل (کلید هرگز برنمی‌گردد) |
| `WS` | `/ws/{sid}` | جریان زندهٔ کندل‌ها برای چارت |

مستندات تعاملی: **http://localhost:8000/docs**

</div>

---

<div dir="rtl" align="right">

## 🧠 دستیار چه ابزارهایی دارد؟

مدل زبانی به‌جای حدس‌زدن، داده را از سرور می‌گیرد:

</div>

```text
search_symbol      · جست‌وجوی نماد با نام فارسی
set_symbol         · تغییر نماد چارت
set_timeframe      · D / 5min / 15min / 30min / 1h
list_indicators    · اندیکاتورهای موجود و فعال
add_indicator      · افزودن اندیکاتور با پارامتر
remove_indicator   · حذف اندیکاتور
reload_plugins     · اسکن مجدد پلاگین‌ها
get_snapshot       · وضعیت کامل چارت و مقادیر همهٔ اندیکاتورها
get_indicator_summary · روند، BOS/CHoCH، اردربلاک، S/R، لیکوییدیتی
get_money_flow     · ورود/خروج پول حقیقی، سرانه، قدرت خریدار
get_orderbook      · عمق بازار و وضعیت صف
find_levels        · حمایت/مقاومت از پیوت‌ها و ATR
```

---

<div dir="rtl" align="right">

## 🧮 اندیکاتورهای موجود

| اندیکاتور | پارامترها | نوع | توضیح |
| --- | --- | --- | --- |
| `RSI` | `length` | پنل جدا | شاخص قدرت نسبی و اشباع خرید/فروش |
| `MACD` | `fast`, `slow`, `signal` | پنل جدا | MACD با خط سیگنال و هیستوگرام |
| `EMA` | `length` | روی چارت | میانگین متحرک نمایی |
| `EMA Cross` | `fast`, `slow` | روی چارت | تقاطع دو میانگین نمایی |
| `Bollinger` | `length`, `mult` | روی چارت | باندهای بولینگر |
| `HSN Algo` ⭐ | — | روی چارت | ساختار بازار، BOS/CHoCH، اردربلاک، عرضه/تقاضا، لیکوییدیتی، پرمیوم/دیسکانت |

### افزودن اندیکاتور جدید

یک فایل در `backend/indicators/plugins/` بسازید و از کلاس پایه ارث‌بری کنید:

</div>

```python
from backend.indicators.base import Indicator

class MyIndicator(Indicator):
    name = "My Indicator"
    overlay = False            # True → روی چارت، False → پنل جدا
    description = "توضیح کوتاه"
    inputs = {"length": 14}

    def compute(self, df):
        length = self.params.get("length", 14)
        values = df["close"].rolling(length).mean()
        return {"plots": {"MyLine": values}}
```

<div dir="rtl" align="right">

سپس `POST /indicators/reload` (یا دکمهٔ اسکن در UI) را بزنید؛ پلاگین بدون ری‌استارت شناسایی می‌شود.

</div>

---

<div dir="rtl" align="right">

## 📂 ساختار پروژه

</div>

```text
TradeYar-/
├── backend/
│   ├── main.py               # اپ FastAPI و مسیرهای REST/WS
│   ├── schemas.py            # مدل‌های ورودی/خروجی
│   ├── agent/
│   │   ├── runner.py         # حلقهٔ Tool Calling و مدیریت کلاینت LLM
│   │   ├── tools.py          # تعریف ابزارهای مدل
│   │   └── prompts.py        # پرامپت سیستم
│   ├── data/
│   │   ├── tsetmc.py         # کلاینت TSETMC (سفارش‌بوک، ریزمعامله، پول حقیقی)
│   │   ├── candle_store.py   # آرشیو کندل‌های درون‌روزی
│   │   └── demo.py           # دادهٔ ساختگی برای حالت دمو
│   ├── engine/
│   │   ├── session.py        # سشن چارت، رفرش و اجرای اندیکاتورها
│   │   ├── poller.py         # پولینگ و پخش WebSocket
│   │   └── analytics.py      # snapshot و خلاصه‌های متنی
│   └── indicators/
│       ├── base.py           # کلاس پایهٔ اندیکاتور
│       ├── registry.py       # کشف و بارگذاری پلاگین‌ها
│       ├── ta.py             # توابع تکنیکال (RSI، EMA، ATR، …)
│       └── plugins/          # اندیکاتورها
├── frontend/
│   ├── app.py                # صفحهٔ Streamlit
│   ├── api_client.py         # لایهٔ ارتباط با بک‌اند
│   └── chart_component.py    # HTML/JS چارت lightweight-charts
├── config.py                 # خواندن تنظیمات از .env
├── requirements.txt
├── run.sh
├── .env.example              # نمونهٔ تنظیمات محیطی (بدون کلید واقعی)
├── .gitignore
├── .gitattributes
└── LICENSE
```

<div dir="rtl" align="right">

> 📦 پوشهٔ `data/` فقط کش محلی کندل‌هاست و در گیت ذخیره نمی‌شود؛ با اولین اجرا خودکار ساخته می‌شود.

</div>

---

<div dir="rtl" align="right">

## 🧪 بررسی سریع سلامت

</div>

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/symbols/search?q=فولاد"
curl http://localhost:8000/session/main/snapshot
```

<div dir="rtl" align="right">

---

## 🛠️ عیب‌یابی

| مشکل | علت محتمل | راه‌حل |
| --- | --- | --- |
| `httpx.ConnectError` به TSETMC | پروکسی/VPN سیستم | `NO_PROXY=cdn.tsetmc.com` هنگام اجرای بک‌اند |
| چارت خالی می‌ماند | نماد متوقف یا بازار بسته | نماد دیگری امتحان کنید؛ چارت آخرین داده را نگه می‌دارد |
| «تنظیمات مدل ناقص است» | `Base URL` یا `Model ID` خالی | هر سه فیلد سایدبار را پر کنید یا `.env` را تنظیم کنید |
| خطای ۴۰۱ از مدل | کلید نامعتبر | `API Key` را در سایدبار بررسی کنید |
| حذف اندیکاتور ۴۰۴ | شناسه شامل `#` | شناسه را URL-encode کنید (`RSI%231`) |

---

## ⚠️ سلب مسئولیت

این پروژه یک ابزار **تحلیلی و آموزشی** است و توصیهٔ سرمایه‌گذاری نیست. تحلیل‌های مدل زبانی ممکن است اشتباه باشند؛ مسئولیت هر تصمیم معاملاتی با خود شماست. دادهٔ TSETMC متعلق به سازمان بورس و اوراق بهادار است و نرخ درخواست را رعایت کنید.

## 📄 مجوز

انتشار تحت مجوز **MIT** — استفاده، تغییر و توزیع با ذکر منبع آزاد است.

---

<div align="center">

**ساخته‌شده برای معامله‌گران فارسی‌زبان** 🇮🇷

⭐هدف این پروژه تحلیل بورس ایران توسط هوش مصنوعی و اندیکاتورهای پریمیوم سیگنال دهی است در صورت حمایت اندیکاتور های بیشتری اضافه میشود.
اگر این پروژه برایتان مفید بود، ستاره بدهید.

</div>

</div>
