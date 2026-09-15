from pydantic import BaseModel, Field
from pydantic import ConfigDict


class NormalizedInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    source: str = "web"
    text: str = ""
    auth_user_id: str = ""
    email: str = ""
    username: str = ""
    first_name: str = ""
    language: str = "en"
    conversation_id: int | None = None
    vehicle_id: int | None = None
    problem_id: int | None = None


class ChatRequest(NormalizedInput):
    text: str = Field(default="", alias="message")


class LinkItem(BaseModel):
    title: str = ""
    url: str = ""
    description: str = ""
    type: str = "link"


class ChatResponse(BaseModel):
    answer: str = ""
    links: list[LinkItem] = Field(default_factory=list)
    quota: dict = Field(default_factory=dict)
