import asyncio
import logging
from datetime import datetime
from config import POLL_INTERVAL, DEMO_MODE, PLUGIN_SCAN_SEC
from backend.indicators import registry
from .session import ChartSession

log = logging.getLogger("poller")
SESSIONS: dict[str, ChartSession] = {}


def market_open() -> bool:
    now = datetime.now()
    return now.weekday() in (5, 6, 0, 1, 2) and (8, 45) <= (now.hour, now.minute) <= (12, 35)


def bar_confirmed(session) -> bool:
    return not (DEMO_MODE or market_open())


async def push(session, new_signals):
    if session.dirty:
        await session.broadcast(session.payload_init())
        session.dirty = False
    else:
        await session.broadcast(session.payload_update(new_signals))


async def plugin_watch_loop():
    while True:
        try:
            ch = registry.scan()
            if ch["added"] or ch["reloaded"] or ch["removed"]:
                log.info("plugins changed: %s", ch)
                for s in SESSIONS.values():
                    s.refresh_classes()
        except Exception as e:
            log.warning("plugin scan error: %s", e)
        await asyncio.sleep(PLUGIN_SCAN_SEC)


async def poll_loop():
    while True:
        for s in list(SESSIONS.values()):
            try:
                new = await s.refresh(confirmed=bar_confirmed(s))
                await push(s, new)
                if new:
                    log.info("SIGNAL %s %s", s.symbol, new)
            except Exception as e:
                log.warning("poll error %s: %s", s.symbol, e)
        await asyncio.sleep(POLL_INTERVAL if (DEMO_MODE or market_open()) else 30)