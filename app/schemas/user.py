from pydantic import BaseModel, Field


class UserRecord(BaseModel):
    id: str | None = None
    email: str = ""
    username: str = ""
    first_name: str = ""
    language: str = "en"


class KnowledgeCase(BaseModel):
    text: str = ""
    car_info: str = ""
    answer: str = ""
    links: list[dict] = Field(default_factory=list)
    language: str = "en"
