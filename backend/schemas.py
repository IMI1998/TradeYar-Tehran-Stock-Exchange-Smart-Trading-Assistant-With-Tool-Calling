from pydantic import BaseModel


class NewSession(BaseModel):
    session_id: str = "main"
    query: str | None = None
    ins_code: str | None = None
    symbol: str | None = None
    timeframe: str = "D"


class SetSymbol(BaseModel):
    ins_code: str
    symbol: str


class SetTimeframe(BaseModel):
    timeframe: str


class AddIndicator(BaseModel):
    name: str
    params: dict | None = None


class ChatIn(BaseModel):
    message: str
    # تنظیمات مدل هر کاربر؛ خالی = مقدار .env سرور
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None