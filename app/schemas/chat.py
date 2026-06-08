from pydantic import BaseModel, Field
from pydantic import ConfigDict


class NormalizedInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    source: str = "web"
    text: str = ""
    auth_user_id: str = ""
    telegram_id: str = ""
    chat_id: str = ""
    email: str = ""
    username: str = ""
    first_name: str = ""
    car_info: str = ""
    language: str = "en"


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
