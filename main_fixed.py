import json
import os
import re
from typing import Optional

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="Car Diagnostic API", version="7.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


FORUMS = {
    "ru": [
        "drive2.ru",
        "drom.ru",
        "auto.ru",
        "nissanstyle.ru",
        "nissan-org.ru",
        "carclub.ru",
    ],
    "en": [
        "pistonheads.com",
        "bobistheoilguy.com",
        "mechanics.stackexchange.com",
        "obd-codes.com",
        "nissanclub.com",
        "carcomplaints.com",
    ],
    "ja": ["minkara.carview.co.jp", "response.jp", "bestcarweb.jp"],
    "zh": ["autohome.com.cn", "xcar.com.cn", "pcauto.com.cn"],
    "de": ["motor-talk.de", "autoplenum.de"],
    "fr": ["forum.auto.fr"],
    "ka": ["ambebi.ge", "avtoportali.ge"],
}

EXTRA_FORUMS = {
    "general": [
        "mechanics.stackexchange.com",
        "garagejournal.com",
        "obd-codes.com",
        "carcomplaints.com",
        "bobistheoilguy.com",
        "pistonheads.com",
    ],
    "japan": [
        "clublexus.com",
        "toyotanation.com",
        "honda-tech.com",
        "nasioc.com",
        "subaruoutback.org",
        "mazda3revolution.com",
        "miata.net",
        "rx8club.com",
        "evolutionm.net",
        "cartune.me",
    ],
    "nissan": [
        "nissanclub.com",
        "nicoclub.com",
        "thenissanpath.com",
        "my350z.com",
    ],
    "bmw": [
        "bimmerpost.com",
        "bimmerfest.com",
        "e46fanatics.com",
        "e90post.com",
    ],
    "mercedes": [
        "mbworld.org",
        "benzworld.org",
    ],
    "vag": [
        "vwvortex.com",
        "audizine.com",
        "golfmk7.com",
        "tdiclub.com",
        "briskoda.net",
        "uk-polos.net",
    ],
    "usa": [
        "f150forum.com",
        "silveradosierra.com",
        "jeepforum.com",
        "cumminsforum.com",
        "dieselplace.com",
        "ls1tech.com",
        "corvetteforum.com",
    ],
    "korea": [
        "kia-forums.com",
        "hyundai-forums.com",
        "genesisowners.com",
    ],
    "eu": [
        "peugeotforums.com",
        "renaultforums.co.uk",
        "fiatforum.com",
        "alfabb.com",
        "volvoforums.org.uk",
        "swedespeed.com",
        "saabcentral.com",
        "honestjohn.co.uk",
    ],
}

# Used only if Claude rejects one of the wider domain lists.
FALLBACK_DOMAINS = [
    "drive2.ru",
    "drom.ru",
    "pistonheads.com",
    "bobistheoilguy.com",
    "mechanics.stackexchange.com",
    "obd-codes.com",
    "carcomplaints.com",
    "minkara.carview.co.jp",
]


class DiagnosticRequest(BaseModel):
    query: str
    lang: str = "ru"
    car_info: Optional[str] = None
    conversation_history: Optional[str] = None
    mode: str = "normal"


SYSTEM_PROMPT = """Ты — опытный автодиагност с 20+ лет практики. Специализируешься на японских, европейских и американских автомобилях, турбомоторах, системах ЭБУ/ECU.

У тебя есть инструмент web_search. ОБЯЗАТЕЛЬНО используй его для поиска реальных обсуждений на форумах перед ответом.

ФОРУМЫ ДЛЯ ПОИСКА:
RU: drive2.ru, drom.ru, auto.ru, nissanstyle.ru, nissan-org.ru, carclub.ru
EN: pistonheads.com, bobistheoilguy.com, mechanics.stackexchange.com, obd-codes.com, nissanclub.com, carcomplaints.com
JP: minkara.carview.co.jp, response.jp, bestcarweb.jp
CN: autohome.com.cn, xcar.com.cn, pcauto.com.cn
EU: motor-talk.de, autoplenum.de, forum.auto.fr
GE: avtoportali.ge

ЛОКАЛИЗАЦИЯ СЛЕНГА — ОБЯЗАТЕЛЬНЫЙ ШАГ ПЕРЕД ПОИСКОМ:
Переведи симптом на технический язык каждого форума, используй разные варианты формулировок в поисковых запросах.

СТРАТЕГИЯ ПОИСКА:
1. "[марка модель двигатель] [симптом] site:drive2.ru"
2. "[марка модель двигатель] [симптом] site:drom.ru"
3. "[марка модель] [symptom english] site:pistonheads.com OR site:mechanics.stackexchange.com"
4. "[марка модель] [OBD symptom] site:obd-codes.com OR site:carcomplaints.com"
5. "[марка модель] [симптом японский] site:minkara.carview.co.jp"

ПРАВИЛА АНАЛИЗА:
1. Определи симптом и переведи его на языки релевантных форумов
2. Найди реальные темы через web_search
3. Опирайся на найденные темы
4. Японские форумы — приоритет для Nissan/Toyota/Honda/Subaru/Mitsubishi
5. Русские форумы — приоритет для Lada, УАЗ и европейских автомобилей с пробегом
6. Если симптом после прогрева — анализируй датчики, ЭБУ, VVT/VCT, термостат и турбину
7. Если симптом звуковой — определи локацию: двигатель, подвеска, тормоза или трансмиссия
8. Дай пошаговый план диагностики от простого к сложному
9. Не выдумывай ссылки
10. Отвечай на языке запроса пользователя

КРИТИЧЕСКИ ВАЖНО: Верни ТОЛЬКО валидный JSON без markdown и backticks:
{
  "summary": "Анализ на основе найденных тем форумов",
  "common_causes": [
    {"cause": "Причина", "frequency": "high|medium|low", "source_langs": ["ru", "en", "jp"]}
  ],
  "solutions": [
    {"title": "Шаг", "description": "Инструкция", "priority": "high|medium|low", "cost": "free|cheap|moderate|expensive", "source_langs": ["ru"]}
  ],
  "unlikely_causes": ["Причина 1"],
  "regional_insights": {
    "ru": "Что нашли на русских форумах",
    "en": "Что нашли на английских форумах",
    "jp": "Что нашли на японских форумах",
    "cn": "Что нашли на китайских форумах",
    "eu": "Что нашли на европейских форумах"
  },
  "topics_found": [
    {"title": "Заголовок темы", "forum": "drive2.ru", "url": "https://реальная-ссылка", "lang": "ru", "relevance": "high", "key_info": "Что решило проблему"}
  ],
  "total_topics": 5,
  "confidence": "high|medium|low",
  "recommendation": "С чего начать",
  "need_more_info": false,
  "clarifying_question": ""
}"""


def unique_domains(domains: list[str]) -> list[str]:
    result = []
    seen = set()

    for domain in domains:
        normalized = str(domain or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

    return result


def detect_forum_groups(text: str) -> list[str]:
    t = text.lower()
    groups = ["general"]

    if any(x in t for x in ["nissan", "infiniti", "x-trail", "xtrail", "skyline", "patrol", "murano"]):
        groups += ["japan", "nissan"]

    if any(x in t for x in ["toyota", "lexus", "honda", "subaru", "mazda", "mitsubishi", "suzuki"]):
        groups += ["japan"]

    if any(x in t for x in ["bmw", "mini"]):
        groups += ["bmw"]

    if any(x in t for x in ["mercedes", "benz", "amg"]):
        groups += ["mercedes"]

    if any(x in t for x in ["vw", "volkswagen", "audi", "skoda", "seat", "porsche"]):
        groups += ["vag"]

    if any(x in t for x in ["ford", "chevrolet", "dodge", "jeep", "ram", "cadillac", "gmc"]):
        groups += ["usa"]

    if any(x in t for x in ["kia", "hyundai", "genesis"]):
        groups += ["korea"]

    if any(x in t for x in ["peugeot", "renault", "citroen", "fiat", "alfa", "volvo", "saab"]):
        groups += ["eu"]

    return list(dict.fromkeys(groups))


def build_allowed_domains(data: DiagnosticRequest) -> list[str]:
    base_domains = [
        "drive2.ru",
        "drom.ru",
        "auto.ru",
        "nissanstyle.ru",
        "nissan-org.ru",
        "carclub.ru",
        "pistonheads.com",
        "bobistheoilguy.com",
        "mechanics.stackexchange.com",
        "obd-codes.com",
        "carcomplaints.com",
        "nissanclub.com",
        "minkara.carview.co.jp",
        "autohome.com.cn",
        "xcar.com.cn",
        "pcauto.com.cn",
        "motor-talk.de",
        "forum.auto.fr",
        "avtoportali.ge",
    ]

    if data.mode.lower() != "deep":
        return unique_domains(base_domains)

    text = f"{data.query} {data.car_info or ''} {data.conversation_history or ''}"
    domains = list(base_domains)

    for group in detect_forum_groups(text):
        domains.extend(EXTRA_FORUMS.get(group, []))

    return unique_domains(domains)


def extract_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except (TypeError, json.JSONDecodeError):
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {
        "summary": cleaned,
        "common_causes": [],
        "solutions": [],
        "unlikely_causes": [],
        "regional_insights": {},
        "topics_found": [],
        "total_topics": 0,
        "confidence": "medium",
        "recommendation": "",
        "need_more_info": False,
        "clarifying_question": "",
    }


def format_for_telegram(result: dict) -> str:
    if result.get("need_more_info"):
        return f"🔍 {result.get('clarifying_question', '')}"

    lines = []
    total = result.get("total_topics", 0)

    if total > 0:
        lines.append(f"📊 Найдено {total} похожих случаев на форумах\n")

    if result.get("summary"):
        lines.append(f"🔍 Диагноз:\n{result['summary']}\n")

    causes = result.get("common_causes", [])
    if causes:
        lines.append("⚠️ Основные причины:")
        for index, cause in enumerate(causes, 1):
            frequency = cause.get("frequency", "") if isinstance(cause, dict) else ""
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(frequency, "•")
            cause_text = cause.get("cause", "") if isinstance(cause, dict) else str(cause)
            source_langs = cause.get("source_langs", []) if isinstance(cause, dict) else []
            langs = " ".join(f"[{lang.upper()}]" for lang in source_langs)
            lines.append(f"{index}. {emoji} {cause_text} {langs}".rstrip())
        lines.append("")

    solutions = result.get("solutions", [])
    if solutions:
        lines.append("🔧 Шаги диагностики:")
        for index, solution in enumerate(solutions, 1):
            if isinstance(solution, dict):
                lines.append(f"{index}. {solution.get('title', '')}")
                lines.append(f"   {solution.get('description', '')}")
            else:
                lines.append(f"{index}. {solution}")
        lines.append("")

    topics = result.get("topics_found", [])
    if topics:
        lines.append("🔗 Источники с форумов:")
        for topic in topics[:5]:
            if not isinstance(topic, dict):
                continue
            lines.append(f"• [{topic.get('forum', '')}] {topic.get('title', '')}")
            if topic.get("key_info"):
                lines.append(f"  💡 {topic['key_info']}")
            if topic.get("url"):
                lines.append(f"  {topic['url']}")
        lines.append("")

    if result.get("recommendation"):
        lines.append(f"💡 Рекомендация эксперта:\n{result['recommendation']}")

    return "\n".join(lines)


def collect_response_text(response) -> str:
    parts = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def run_claude_search(client, data: DiagnosticRequest, user_message: str, domains: list[str]):
    return client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=5000 if data.mode.lower() == "deep" else 4000,
        system=SYSTEM_PROMPT,
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 6 if data.mode.lower() == "deep" else 3,
                "allowed_domains": unique_domains(domains),
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )


@app.get("/")
def home():
    return {
        "message": "Car Diagnostic API is working",
        "version": "7.1",
        "engine": "Claude Haiku 4.5 + Real Web Search",
        "forums": "normal + deep",
        "role": "Real forum search with deep mode",
    }


@app.post("/diagnose")
def diagnose(data: DiagnosticRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    client = anthropic.Anthropic(api_key=api_key)
    mode = data.mode.lower().strip()
    context_parts = []

    if data.car_info:
        context_parts.append(f"Машина пользователя: {data.car_info}")
    if data.conversation_history:
        context_parts.append(f"История диалога: {data.conversation_history}")

    context = "\n".join(context_parts)
    user_message = (
        f"{context}\n\n"
        f"Запрос: {data.query}\n"
        f"Язык ответа: {data.lang}\n"
        f"Режим поиска: {mode}\n\n"
        "СНАЧАЛА переведи симптом на языки релевантных форумов, "
        "затем найди реальные темы через web_search, "
        "после чего верни ТОЛЬКО валидный JSON."
    )

    if mode == "deep":
        user_message += (
            "\n\nРЕЖИМ DEEP SEARCH: пользователь попросил больше информации. "
            "Ищи по расширенным автомобильным форумам, OEM-клубам и техническим сайтам. "
            "Не повторяй старый ответ. Найди дополнительные причины, редкие версии, "
            "подтверждённые случаи и новые реальные ссылки."
        )

    allowed_domains = build_allowed_domains(data)
    used_domains = allowed_domains
    fallback_used = False

    try:
        try:
            response = run_claude_search(client, data, user_message, allowed_domains)
        except Exception as first_error:
            error_text = str(first_error).lower()
            domain_error = (
                "domains are not accessible" in error_text
                or "allowed_domains" in error_text
                or "invalid_request_error" in error_text
            )

            if not domain_error:
                raise

            used_domains = unique_domains(FALLBACK_DOMAINS)
            fallback_used = True
            response = run_claude_search(client, data, user_message, used_domains)

        raw_text = collect_response_text(response)
        result = extract_json(raw_text)
        result["telegram_text"] = format_for_telegram(result)
        result["_meta"] = {
            "engine": "Claude Haiku 4.5 + web_search",
            "mode": mode,
            "allowed_domains": used_domains,
            "fallback_used": fallback_used,
            "version": "7.1",
        }
        return result

    except Exception as error:
        return {
            "error": str(error),
            "summary": "Сервис поиска временно недоступен. Повторите запрос позже.",
            "common_causes": [],
            "solutions": [],
            "topics_found": [],
            "total_topics": 0,
            "confidence": "low",
            "recommendation": "",
            "need_more_info": False,
            "clarifying_question": "",
            "telegram_text": "Сервис поиска временно недоступен. Повторите запрос позже.",
            "_meta": {
                "mode": mode,
                "allowed_domains": used_domains,
                "fallback_used": fallback_used,
                "version": "7.1",
            },
        }


@app.post("/search")
def search(data: DiagnosticRequest):
    return diagnose(data)


@app.get("/forums")
def list_forums():
    return {
        "forums": FORUMS,
        "extra_forums": EXTRA_FORUMS,
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": "7.1"}
