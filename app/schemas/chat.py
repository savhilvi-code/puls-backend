from pydantic import BaseModel, Field
from pydantic import ConfigDict


class NormalizedInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    source: str = "web"
    text: str = ""
    language: str = "en"
    conversation_id: str | None = None
    vehicle_id: str | None = None
    problem_id: str | None = None


class ChatRequest(NormalizedInput):
    text: str = Field(default="", alias="message")


class LinkItem(BaseModel):
    title: str = ""
    url: str = ""
    description: str = ""
    type: str = "link"
    source_url: str = ""


class ChatResponse(BaseModel):
    trace_id: str | None = None
    conversation_id: str | None = None
    vehicle_id: str | None = None
    problem_id: str | None = None
    answer: str = ""
    links: list[LinkItem] = Field(default_factory=list)
    quota: dict = Field(default_factory=dict)
