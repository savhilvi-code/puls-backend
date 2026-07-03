from pydantic import BaseModel, Field


class UserRecord(BaseModel):
    id: int | None = None
    auth_user_id: str = ""
    email: str = ""
    username: str = ""
    first_name: str = ""
    car_info: str = ""
    language: str = "en"
    conversation_history: str = ""
    requests_left: int = 5


class KnowledgeCase(BaseModel):
    text: str = ""
    car_info: str = ""
    answer: str = ""
    links: list[dict] = Field(default_factory=list)
    language: str = "en"
