"""اسکن خودکار پوشه‌ی plugins: هر فایل .py (بدون _ اول) = یک یا چند اندیکاتور. hot-reload با mtime."""
import importlib, inspect, logging, sys
from pathlib import Path
from .base import Indicator

log = logging.getLogger("indicators")
PLUGIN_DIR = Path(__file__).parent / "plugins"
PKG = "backend.indicators.plugins"

REGISTRY: dict[str, type[Indicator]] = {}
_mtimes: dict[str, float] = {}
_errors: dict[str, str] = {}


def _modname(stem): return f"{PKG}.{stem}"


def _unregister(modname):
    removed = [n for n, c in REGISTRY.items() if c.__module__ == modname]
    for n in removed: REGISTRY.pop(n)
    return removed


def _load(stem: str) -> tuple[str, list[str]]:
    modname = _modname(stem)
    if modname in sys.modules:
        mod = importlib.reload(sys.modules[modname]); kind = "reloaded"
    else:
        mod = importlib.import_module(modname); kind = "added"
    _unregister(modname)
    names = []
    for _, cls in inspect.getmembers(mod, inspect.isclass):
        if issubclass(cls, Indicator) and cls is not Indicator and cls.__module__ == modname and cls.name:
            REGISTRY[cls.name] = cls; names.append(cls.name)
    return kind, names


def scan(force: bool = False) -> dict:
    """یک بار در استارت و هر چند ثانیه توسط poller صدا زده می‌شود."""
    ch = {"added": [], "reloaded": [], "removed": [], "errors": {}}
    files = {f.stem: f for f in PLUGIN_DIR.glob("*.py") if f.stem != "__init__"}

    # فایل حذف‌شده
    for stem in [s for s in _mtimes if s not in files]:
        _mtimes.pop(stem); _errors.pop(stem, None)
        ch["removed"] += _unregister(_modname(stem))

    # کتابخانه‌های خصوصی (_x.py): اگر عوض شدند، reload و همه‌ی پلاگین‌ها force
    for stem, f in files.items():
        if stem.startswith("_") and _mtimes.get(stem) != f.stat().st_mtime:
            _mtimes[stem] = f.stat().st_mtime
            if _modname(stem) in sys.modules:
                try: importlib.reload(sys.modules[_modname(stem)]); force = True
                except Exception as e: _errors[stem] = f"{type(e).__name__}: {e}"

    for stem, f in files.items():
        if stem.startswith("_"): continue
        mt = f.stat().st_mtime
        if not force and _mtimes.get(stem) == mt: continue
        try:
            kind, names = _load(stem)
            ch[kind] += names; _errors.pop(stem, None)
            log.info("plugin %s %s -> %s", stem, kind, names)
        except Exception as e:
            _errors[stem] = f"{type(e).__name__}: {e}"
            log.exception("plugin %s failed", stem)
        _mtimes[stem] = mt
    ch["errors"] = dict(_errors)
    return ch


def get_indicator(name: str) -> type[Indicator]:
    if name not in REGISTRY:
        raise KeyError(f"اندیکاتور '{name}' موجود نیست. موجود: {list(REGISTRY)}")
    return REGISTRY[name]


def list_indicators(plan: str = "free") -> list[dict]:
    return [{"name": n, "description": c.description, "overlay": c.overlay, "inputs": c.inputs,
             "premium": c.premium, "heavy": c.heavy, "available": (not c.premium) or plan == "premium",
             "file": c.__module__.split(".")[-1] + ".py"} for n, c in sorted(REGISTRY.items(), key=lambda x: (x[1].premium, x[0]))]


def plugin_errors() -> dict: return dict(_errors)