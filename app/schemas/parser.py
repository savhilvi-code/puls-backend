from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class DiagnosticRequest(BaseModel):
    query: str
    lang: str = "ru"
    car_info: Optional[str] = None
    evidence_context: Optional[str] = None
    problem_context: Optional[dict[str, Any]] = None
    source_group: str = ""
    stage_purpose: str = ""
    mode: str = "normal"
