import requests
from urllib.parse import quote

class API:
    def __init__(self, base: str):
        self.b = base.rstrip("/")

    def _r(self, m, path, **kw):
        r = requests.request(m, f"{self.b}{path}", timeout=kw.pop("timeout", 30), **kw)
        r.raise_for_status()
        return r.json()

    def health(self): return self._r("GET", "/health")
    def search(self, q): return self._r("GET", "/symbols/search", params={"q": q})
    def indicators(self): return self._r("GET", "/indicators")
    def config(self, sid): return self._r("GET", f"/session/{sid}")
    def create(self, sid, query, tf="D"): return self._r("POST", "/session", json={"session_id": sid, "query": query, "timeframe": tf})
    def set_symbol(self, sid, ins, sym): return self._r("POST", f"/session/{sid}/symbol", json={"ins_code": ins, "symbol": sym})
    def set_tf(self, sid, tf): return self._r("POST", f"/session/{sid}/timeframe", json={"timeframe": tf})
    def add_ind(self, sid, name, params=None): return self._r("POST", f"/session/{sid}/indicators", json={"name": name, "params": params})
    # id اندیکاتورها «#» دارند؛ بدون encode، بقیه‌ی آدرس fragment حساب و حذف ۴۰۴ می‌شود
    def del_ind(self, sid, iid): return self._r("DELETE", f"/session/{sid}/indicators/{quote(str(iid), safe='')}")
    def chat(self, sid, msg, llm=None): return self._r("POST", f"/session/{sid}/chat", json={"message": msg, **(llm or {})}, timeout=180)
    def llm_defaults(self): return self._r("GET", "/llm")