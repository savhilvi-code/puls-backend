from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DiagnosticRequest(BaseModel):
    query: str
    lang: str = "ru"
    car_info: Optional[str] = None
    conversation_history: Optional[str] = None
    mode: str = "normal"
