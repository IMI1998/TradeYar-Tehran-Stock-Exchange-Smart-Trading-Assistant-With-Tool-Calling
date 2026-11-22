"""
Agent runner — اتصال به هر API سازگار با OpenAI (9Router، OpenAI، OpenRouter، …)

تنظیمات مدل (base_url / api_key / model) از فرانت می‌آید تا هر کاربر با
مشخصات خودش کار کند؛ هر فیلدی خالی بماند از .env سرور خوانده می‌شود.
"""
import json
import logging

import httpx
from openai import AsyncOpenAI

from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_PROXY
from .prompts import SYSTEM
from .tools import build_tools, execute

log = logging.getLogger("agent")

DEFAULTS = {"base_url": LLM_BASE_URL, "api_key": LLM_API_KEY, "model": LLM_MODEL}
_CLIENTS: dict[tuple[str, str], AsyncOpenAI] = {}

HISTORY: dict[str, list] = {}
MAX_MSGS = 30


def resolve_llm(cfg: dict | None = None) -> dict:
    """تنظیمات کاربر را با .env کامل می‌کند"""
    cfg = cfg or {}
    return {
        "base_url": (cfg.get("base_url") or DEFAULTS["base_url"] or "").strip(),
        "api_key": (cfg.get("api_key") or DEFAULTS["api_key"] or "").strip(),
        "model": (cfg.get("model") or DEFAULTS["model"] or "").strip(),
    }


def _client(base_url: str, api_key: str) -> AsyncOpenAI:
    c = _CLIENTS.get((base_url, api_key))
    if c is None:
        if len(_CLIENTS) >= 8:            # کلیدهای زیادی در حافظه نگه نداریم
            _CLIENTS.clear()
        kwargs = {"timeout": 180.0}
        if LLM_PROXY:                     # فقط برای 9Router لوکال
            kwargs["proxy"] = LLM_PROXY
        c = AsyncOpenAI(base_url=base_url.rstrip("/"), api_key=api_key,
                        http_client=httpx.AsyncClient(**kwargs))
        _CLIENTS[(base_url, api_key)] = c
    return c


def _openai_tools():
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    } for t in build_tools()]


def _friendly_error(e: Exception, llm: dict) -> str:
    msg = str(e)
    low = msg.lower()
    where = llm.get("base_url") or "Base URL"
    if "connect" in low or "connection" in low or "refused" in low:
        return f"اتصال به {where} برقرار نشد. Base URL و روشن بودن سرویس/اینترنت را چک کن."
    if "401" in msg or "403" in msg or "unauthorized" in low or "invalid api" in low:
        return "API Key نامعتبر است یا اجازهٔ استفاده از این مدل را ندارد."
    if "429" in msg or "rate" in low or "quota" in low or "credit" in low:
        return "سهمیه یا نرخ درخواست تمام شده. کمی صبر کن یا کلید/مدل دیگری بگذار."
    if "model" in low and ("not found" in low or "invalid" in low or "does not exist" in low):
        return f"مدل «{llm.get('model')}» روی این سرویس پیدا نشد. Model ID را چک کن."
    if "<!doctype" in low or "cloudflare" in low:
        return f"پاسخ HTML گرفتیم — احتمالاً Base URL اشتباه است (معمولاً باید به …/v1 ختم شود): {where}"
    return msg[:400]


async def chat(sid: str, session, src, message: str, llm: dict | None = None) -> dict:
    cfg = resolve_llm(llm)
    if not cfg["base_url"] or not cfg["api_key"] or not cfg["model"]:
        return {"reply": "تنظیمات مدل کامل نیست. در سایدبار «⚙️ مدل هوش مصنوعی» "
                         "Base URL، API Key و Model ID را پر کن.", "trace": []}

    client = _client(cfg["base_url"], cfg["api_key"])
    hist = HISTORY.setdefault(sid, [])
    hist.append({"role": "user", "content": message})
    trace = []

    for _ in range(12):
        try:
            resp = await client.chat.completions.create(
                model=cfg["model"],
                messages=[{"role": "system", "content": SYSTEM}] + hist,
                tools=_openai_tools(),
                tool_choice="auto",
                temperature=0.2,
                max_tokens=3000,
            )
        except Exception as e:
            log.exception("LLM error")
            return {"reply": f"⚠️ خطای LLM: {_friendly_error(e, cfg)}", "trace": trace}

        msg = resp.choices[0].message
        assistant_msg = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
        hist.append(assistant_msg)

        if not msg.tool_calls:
            del hist[:-MAX_MSGS]
            return {"reply": msg.content or "", "trace": trace}

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                out = await execute(tc.function.name, args, session, src)
            except Exception as ex:
                out = {"error": str(ex)}
            s = json.dumps(out, ensure_ascii=False, default=str)
            trace.append({"tool": tc.function.name, "input": args, "output": s[:500]})
            hist.append({"role": "tool", "tool_call_id": tc.id, "content": s[:15000]})

    return {"reply": "به سقف فراخوانی ابزار رسیدم؛ سؤال را ساده‌تر بپرس.", "trace": trace}
