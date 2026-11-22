import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import DEMO_MODE, DEFAULT_SYMBOL, USER_PLAN, LLM_BASE_URL, LLM_MODEL, LLM_API_KEY
from backend.data.tsetmc import TSETMC
from backend.data.demo import DemoSource
from backend.engine.session import ChartSession
from backend.engine import poller, analytics
from backend.indicators import registry
from backend.agent import runner
from backend.schemas import NewSession, SetSymbol, SetTimeframe, AddIndicator, ChatIn

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("main")

SRC = DemoSource() if DEMO_MODE else TSETMC()
SESSIONS = poller.SESSIONS


# ─────────────────────────── helpers ───────────────────────────
async def make_session(sid: str, query: str | None = None, ins_code: str | None = None,
                       symbol: str | None = None, tf: str = "D") -> ChartSession:
    if not ins_code:
        res = await SRC.search(query or DEFAULT_SYMBOL)
        if not res:
            raise HTTPException(404, "نماد پیدا نشد")
        pick = next((r for r in res if r["active"]), res[0])
        ins_code, symbol = pick["ins_code"], pick["symbol"]

    s = ChartSession(sid, SRC, ins_code, symbol or ins_code, tf)
    if "RSI" in registry.REGISTRY:          # اندیکاتور پیش‌فرض برای دمو
        s.add_indicator("RSI")
    SESSIONS[sid] = s
    try:
        await s.refresh(confirmed=poller.bar_confirmed(s))
    except Exception as e:
        log.warning("initial refresh failed for %s: %s", sid, e)
    return s


def get_session(sid: str) -> ChartSession:
    if sid not in SESSIONS:
        raise HTTPException(404, f"session '{sid}' not found")
    return SESSIONS[sid]


def check_plan(name: str):
    try:
        cls = registry.get_indicator(name)
    except KeyError as e:
        raise HTTPException(400, str(e))
    if cls.premium and USER_PLAN != "premium":
        raise HTTPException(403, f"«{cls.name}» فقط در پلن پریمیوم فعال است")
    return cls


# ─────────────────────────── lifespan ───────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    ch = registry.scan(force=True)
    log.info("plugins loaded: %s | errors: %s", list(registry.REGISTRY), ch["errors"])
    log.info("data source: %s | plan: %s", "DEMO" if DEMO_MODE else "TSETMC", USER_PLAN)

    try:
        await make_session("main", DEFAULT_SYMBOL)
    except Exception as e:
        log.warning("default session failed: %s", e)

    tasks = [asyncio.create_task(poller.poll_loop()),
             asyncio.create_task(poller.plugin_watch_loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="TSE Copilot", version="0.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ─────────────────────────── general ───────────────────────────
@app.get("/health")
async def health():
    return {"ok": True, "demo": DEMO_MODE, "plan": USER_PLAN,
            "sessions": list(SESSIONS), "indicators": list(registry.REGISTRY),
            "plugin_errors": registry.plugin_errors()}


@app.get("/symbols/search")
async def search(q: str):
    return await SRC.search(q)


# ─────────────────────────── indicators / plugins ───────────────────────────
@app.get("/indicators")
async def indicators():
    return {"plan": USER_PLAN,
            "items": registry.list_indicators(USER_PLAN),
            "errors": registry.plugin_errors()}


@app.post("/indicators/reload")
async def reload_plugins():
    ch = registry.scan(force=True)
    for s in SESSIONS.values():
        s.refresh_classes()
    return ch


# ─────────────────────────── sessions ───────────────────────────
@app.post("/session")
async def create_session(body: NewSession):
    s = await make_session(body.session_id, body.query, body.ins_code, body.symbol, body.timeframe)
    return s.config()


@app.get("/session/{sid}")
async def session_config(sid: str):
    return get_session(sid).config()


@app.delete("/session/{sid}")
async def delete_session(sid: str):
    SESSIONS.pop(sid, None)
    runner.HISTORY.pop(sid, None)
    return {"ok": True}


@app.post("/session/{sid}/symbol")
async def set_symbol(sid: str, body: SetSymbol):
    s = get_session(sid)
    s.set_symbol(body.ins_code, body.symbol)
    await s.refresh(confirmed=poller.bar_confirmed(s))
    await poller.push(s, [])
    return s.config()


@app.post("/session/{sid}/timeframe")
async def set_timeframe(sid: str, body: SetTimeframe):
    s = get_session(sid)
    s.set_timeframe(body.timeframe)
    await s.refresh(confirmed=poller.bar_confirmed(s))
    await poller.push(s, [])
    return s.config()


@app.post("/session/{sid}/indicators")
async def add_indicator(sid: str, body: AddIndicator):
    s = get_session(sid)
    check_plan(body.name)
    iid = s.add_indicator(body.name, body.params)
    await s.refresh(confirmed=poller.bar_confirmed(s))
    await poller.push(s, [])
    return {"id": iid, **s.config()}


@app.delete("/session/{sid}/indicators/{iid}")
async def remove_indicator(sid: str, iid: str):
    s = get_session(sid)
    if not s.remove_indicator(iid):
        raise HTTPException(404, f"indicator '{iid}' not found")
    await s.refresh(confirmed=poller.bar_confirmed(s))
    await poller.push(s, [])
    return s.config()


@app.get("/session/{sid}/snapshot")
async def snapshot(sid: str):
    return analytics.snapshot(get_session(sid))


@app.get("/session/{sid}/summary")
async def summary(sid: str):
    return get_session(sid).summaries()


# ─────────────────────────── agent ───────────────────────────
@app.post("/session/{sid}/chat")
async def chat(sid: str, body: ChatIn):
    s = get_session(sid)
    out = await runner.chat(sid, s, SRC, body.message,
                            {"base_url": body.base_url, "api_key": body.api_key, "model": body.model})
    if s.dirty:                              # اگر LLM چارت را عوض کرد، فوراً به فرانت بفرست
        await poller.push(s, [])
    return {**out, "config": s.config()}


@app.get("/llm")
async def llm_defaults():
    """پیش‌فرض‌های سرور برای فرم تنظیمات مدل (کلید هرگز برنمی‌گردد)"""
    return {"base_url": LLM_BASE_URL, "model": LLM_MODEL, "has_key": bool(LLM_API_KEY)}


@app.delete("/session/{sid}/chat")
async def clear_chat(sid: str):
    runner.HISTORY.pop(sid, None)
    return {"ok": True}


# ─────────────────────────── websocket ───────────────────────────
@app.websocket("/ws/{sid}")
async def ws(websocket: WebSocket, sid: str):
    await websocket.accept()
    if sid not in SESSIONS:
        await websocket.close(code=4004)
        return
    s = SESSIONS[sid]
    s.subscribers.add(websocket)
    try:
        await websocket.send_json(s.payload_init())
        while True:
            await websocket.receive_text()   # ping کلاینت؛ فقط برای نگه‌داشتن اتصال
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug("ws closed %s: %s", sid, e)
    finally:
        s.subscribers.discard(websocket)