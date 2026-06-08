from pydantic import BaseModel


class RouterDecision(BaseModel):
    message_type: str = "general"
    language: str = "en"
    need_car_info: bool = False
    need_clarification: bool = False
    ready_to_search: bool = False
    deep_search: bool = False
    user_says_helped: bool = False
    user_says_not_helped: bool = False
    question: str = ""
    car_info: str = ""
    active_car: str = ""
    symptom: str = ""
    response: str = ""

