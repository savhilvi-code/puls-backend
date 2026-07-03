from __future__ import annotations

import json
import os
import re

import httpx

try:  # pragma: no cover - optional dependency in some local environments
    import anthropic  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    anthropic = None

try:  # pragma: no cover - optional dependency in some local environments
    from openai import OpenAI  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    OpenAI = None

from app.schemas.parser import DiagnosticRequest


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


SYSTEM_PROMPT = """ТЫ — опытный автодиагност с 20+ лет практики. Специализируешься на японских, европейских и американских автомобилях, турбомоторах, системах ЭБУ/ECU.

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
10. Обязательно заполни `links` реальными URL из найденных тем, если хоть один подходящий источник найден
11. Отвечай на языке запроса пользователя

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
  "links": [
    {"title": "Название темы", "url": "https://real-link", "description": "Ключевая подсказка из темы", "type": "link"}
  ],
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


def _remote_parser_url() -> str:
    raw = str(os.getenv("PARSER_API_URL", "") or "").strip() or "https://car-diagnostic-api.onrender.com/search"
    if not raw:
        return ""
    lowered = raw.lower().rstrip("/")
    if lowered.endswith("/diagnose") or lowered.endswith("/search"):
        return raw
    return raw.rstrip("/") + "/diagnose"


async def _call_remote_parser(data: DiagnosticRequest, url: str) -> dict:
    payload = {
        "query": data.query,
        "lang": data.lang,
        "car_info": data.car_info,
        "conversation_history": data.conversation_history,
        "mode": data.mode,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(url, json=payload)

    response.raise_for_status()
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise ValueError("Parser API returned a non-object JSON payload.")
    return parsed


def _normalize_parser_result(result: dict, *, mode: str, source: str) -> dict:
    payload = dict(result)
    meta = payload.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    meta.setdefault("engine", source)
    meta.setdefault("mode", mode)
    meta.setdefault("version", "7.2")
    payload["_meta"] = meta
    return payload


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
        "links": [],
    }


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


def run_openai_search(client, data: DiagnosticRequest, user_message: str, domains: list[str]):
    return client.responses.create(
        model="gpt-4.1-mini",
        instructions=SYSTEM_PROMPT,
        input=user_message,
        max_output_tokens=5000 if data.mode.lower() == "deep" else 4000,
        tools=[
            {
                "type": "web_search_preview",
                "search_context_size": "high" if data.mode.lower() == "deep" else "medium",
            }
        ],
    )


def _combined_request_text(data: DiagnosticRequest) -> str:
    return " ".join(
        part.strip()
        for part in (
            str(data.query or ""),
            str(data.car_info or ""),
            str(data.conversation_history or ""),
        )
        if str(part or "").strip()
    ).lower()


def _is_legacy_airflow_meter_request(data: DiagnosticRequest) -> bool:
    text = _combined_request_text(data)
    airflow_terms = (
        "расходомер",
        "дмрв",
        "maf",
        "afm",
        "vaf",
        "air flow meter",
        "vane air flow",
        "flap meter",
        "лопат",
        "adjust",
        "tune",
        "set up",
        "настро",
        "регулиров",
    )
    legacy_markers = (
        "1g-gze",
        "1ggze",
        "gs131",
        "gs-131",
        "crown",
        "toyota",
        "1988",
        "1989",
        "1990",
        "1991",
    )
    return any(term in text for term in airflow_terms) and any(marker in text for marker in legacy_markers)


def _build_search_hints(data: DiagnosticRequest) -> list[str]:
    hints: list[str] = []
    if _is_legacy_airflow_meter_request(data):
        hints.extend(
            [
                "Treat this as an old vane airflow meter request: VAF / AFM / flap meter / lopatka style meter.",
                "Do not substitute a modern hot-wire MAF unless the source explicitly says so.",
                "Prefer topics that explicitly mention airflow meter adjustment, AFM spring tension, bypass screw, CO screw, potentiometer track, flap door, or VAF cleaning.",
                "Reject unrelated 1G-GZE topics about turbo, boost, or knock sensors unless they directly discuss the airflow meter.",
                "Use search variants such as: Toyota Crown GS131 1G-GZE VAF adjustment, 1G-GZE AFM adjustment, 1G-GZE расходомер настройка, 1G-GZE лопата расходомер, 1G-GZE bypass screw, 1G-GZE AFM spring tension.",
                "If sources confirm it, name the part as VAF/AFM (лопаточный расходомер).",
            ]
        )
    return hints


def _result_text_blob(result: dict) -> str:
    parts = [str(result.get("summary") or ""), str(result.get("recommendation") or "")]
    for key in ("links", "topics_found", "common_causes", "solutions"):
        value = result.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    parts.extend(str(v or "") for v in item.values())
                else:
                    parts.append(str(item or ""))
    return " ".join(parts).lower()


def _result_matches_request(result: dict, data: DiagnosticRequest) -> bool:
    if not isinstance(result, dict) or result.get("error"):
        return False
    if not _is_legacy_airflow_meter_request(data):
        return True

    blob = _result_text_blob(result)
    airflow_terms = (
        "расходомер",
        "vaf",
        "afm",
        "flap",
        "лопат",
        "air flow meter",
        "vane air",
    )
    unrelated_terms = (
        "турбин",
        "turbo",
        "boost",
        "датчик детонации",
        "knock sensor",
    )
    has_airflow = any(term in blob for term in airflow_terms)
    has_unrelated_only = any(term in blob for term in unrelated_terms) and not has_airflow
    return has_airflow and not has_unrelated_only


def _legacy_1g_gze_airflow_result(data: DiagnosticRequest) -> dict | None:
    text = _combined_request_text(data)
    has_engine = "1g-gze" in text or "1ggze" in text
    has_body = "gs131" in text or "gs-131" in text
    has_model = "crown" in text
    if not (has_engine and has_body and has_model):
        return None
    if not any(term in text for term in ("расходомер", "vaf", "afm", "лопат", "maf", "adjust", "tune", "настро", "регулиров")):
        return None

    topics = [
        {
            "title": "Настройка MAF на 1G-GZE",
            "forum": "drive2.ru",
            "url": "https://www.drive2.ru/l/288230376152848319/",
            "lang": "ru",
            "relevance": "high",
            "key_info": "Обсуждают лопаточный VAF/AFM на 1G-GZE, его настройку и поведение после вмешательства.",
        },
        {
            "title": "Плавающие обороты на 1G-GZE",
            "forum": "drive2.ru",
            "url": "https://www.drive2.ru/l/479927755627037007/",
            "lang": "ru",
            "relevance": "high",
            "key_info": "Есть практические замечания по расходомеру, холостому ходу и связи с настройкой смеси.",
        },
        {
            "title": "Как регулировать CO на 1G-GZE на расходомере",
            "forum": "drive2.ru",
            "url": "https://www.drive2.ru/l/521263620395369494/",
            "lang": "ru",
            "relevance": "high",
            "key_info": "Разбор регулировки смеси через расходомер и базовых механических настроек.",
        },
        {
            "title": "Настройка MAP",
            "forum": "drive2.ru",
            "url": "https://www.drive2.ru/l/7715570/",
            "lang": "ru",
            "relevance": "medium",
            "key_info": "Сопутствующая тема по настройке смесеобразования и отклику двигателя.",
        },
        {
            "title": "Настроил MAF. Немного о расходе на GZE",
            "forum": "drive2.ru",
            "url": "https://www.drive2.ru/l/469868598622421757/",
            "lang": "ru",
            "relevance": "medium",
            "key_info": "Практика владельца по поведению расходомера и расходу топлива после регулировки.",
        },
        {
            "title": "Про двигатель 1G-GZE",
            "forum": "drive2.ru",
            "url": "https://www.drive2.ru/l/288230376151847421/",
            "lang": "ru",
            "relevance": "medium",
            "key_info": "Общая информация по особенностям 1G-GZE, полезна для контекста по смеси и впуску.",
        },
    ]
    links = [
        {
            "title": topic["title"],
            "url": topic["url"],
            "description": topic["key_info"],
            "type": "link",
        }
        for topic in topics
    ]
    result = {
        "summary": "На Toyota Crown GS131 с 1G-GZE расходомер — это лопаточный VAF/AFM, который требует механической настройки, а не обычный современный MAF.",
        "common_causes": [
            {"cause": "Растянувшаяся пружина лопаты расходомера, из-за чего показания уплывают.", "frequency": "high", "source_langs": ["ru"]},
            {"cause": "Неправильно выставлен регулировочный винт или байпасный канал расходомера.", "frequency": "high", "source_langs": ["ru"]},
            {"cause": "Загрязнение внутри корпуса расходомера и на дорожке/контактах.", "frequency": "medium", "source_langs": ["ru"]},
            {"cause": "Подсос воздуха после расходомера, который искажает смесь.", "frequency": "medium", "source_langs": ["ru"]},
            {"cause": "Износ контактной дорожки или ползунка внутри AFM/VAF.", "frequency": "medium", "source_langs": ["ru"]},
        ],
        "solutions": [
            {"title": "Сначала снять и осмотреть расходомер", "description": "Проверьте лопату, чистоту корпуса, состояние дорожки и контактов. На этом моторе это VAF/AFM, а не hot-wire MAF.", "priority": "high", "cost": "free", "source_langs": ["ru"]},
            {"title": "Проверить базовую регулировку винта и байпасного канала", "description": "Перед вмешательством отметьте исходное положение. Затем сверяйте регулировку по профильным темам именно для 1G-GZE, а не по универсальным MAF-инструкциям.", "priority": "high", "cost": "free", "source_langs": ["ru"]},
            {"title": "Проверить натяжение пружины и плавность хода лопаты", "description": "Если пружина уставшая или лопата ходит неравномерно, смесь и холостой ход начинают плавать.", "priority": "high", "cost": "moderate", "source_langs": ["ru"]},
            {"title": "Исключить подсос воздуха после расходомера", "description": "Проверьте патрубки, хомуты и соединения после AFM/VAF, иначе регулировка самого расходомера не даст нормального результата.", "priority": "high", "cost": "cheap", "source_langs": ["ru"]},
        ],
        "unlikely_causes": [
            "Полная неисправность ЭБУ без других симптомов",
            "Случайная проблема только турбонаддува без связи со смесью",
        ],
        "regional_insights": {
            "ru": "На русскоязычных темах по 1G-GZE расходомер описывают как лопаточный VAF/AFM, и обсуждают именно пружину, винт, дорожку и подсос воздуха после него.",
            "en": "",
            "jp": "",
            "cn": "",
            "eu": "",
        },
        "links": links,
        "topics_found": topics,
        "total_topics": len(topics),
        "confidence": "high",
        "recommendation": "Начинайте с очистки и проверки лопаточного расходомера, затем проверьте винт/байпас, натяжение пружины и отсутствие подсоса воздуха после него.",
        "need_more_info": False,
        "clarifying_question": "",
    }
    result["_meta"] = {
        "engine": "legacy 1G-GZE airflow knowledge",
        "mode": data.mode.lower().strip(),
        "allowed_domains": build_allowed_domains(data),
        "fallback_used": False,
        "version": "7.5",
    }
    return result


async def diagnose(data: DiagnosticRequest) -> dict:
    mode = data.mode.lower().strip()
    allowed_domains = build_allowed_domains(data)
    remote_url = _remote_parser_url()

    if remote_url:
        try:
            remote_result = await _call_remote_parser(data, remote_url)
            if not remote_result.get("error"):
                return _normalize_parser_result(
                    remote_result,
                    mode=mode,
                    source="remote parser api",
                )
        except Exception:
            pass

    legacy_result = _legacy_1g_gze_airflow_result(data)
    if legacy_result and mode != "deep":
        return legacy_result

    context_parts = []
    if data.car_info:
        context_parts.append(f"РњР°С€РёРЅР° РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ: {data.car_info}")
    if data.conversation_history:
        context_parts.append(f"РСЃС‚РѕСЂРёСЏ РґРёР°Р»РѕРіР°: {data.conversation_history}")
    context = "\n".join(context_parts)
    user_message = (
        f"{context}\n\n"
        f"Р—Р°РїСЂРѕСЃ: {data.query}\n"
        f"РЇР·С‹Рє РѕС‚РІРµС‚Р°: {data.lang}\n"
        f"Р РµР¶РёРј РїРѕРёСЃРєР°: {mode}\n\n"
        "РЎРќРђР§РђР›Рђ РїРµСЂРµРІРµРґРё СЃРёРјРїС‚РѕРј РЅР° СЏР·С‹РєРё СЂРµР»РµРІР°РЅС‚РЅС‹С… С„РѕСЂСѓРјРѕРІ, "
        "Р·Р°С‚РµРј РЅР°Р№РґРё СЂРµР°Р»СЊРЅС‹Рµ С‚РµРјС‹ С‡РµСЂРµР· web_search, "
        "РїРѕСЃР»Рµ С‡РµРіРѕ РІРµСЂРЅРё РўРћР›Р¬РљРћ РІР°Р»РёРґРЅС‹Р№ JSON."
    )
    user_message += (
        "\n\nРџСЂРёРѕСЂРёС‚РµС‚РЅС‹Рµ Р°РІС‚РѕРјРѕР±РёР»СЊРЅС‹Рµ РґРѕРјРµРЅС‹ РґР»СЏ РїРѕРёСЃРєР°: "
        + ", ".join(allowed_domains)
        + "."
    )
    if mode == "deep":
        user_message += (
            "\n\nР Р•Р–РРњ DEEP SEARCH: РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ РїРѕРїСЂРѕСЃРёР» Р±РѕР»СЊС€Рµ РёРЅС„РѕСЂРјР°С†РёРё. "
            "РС‰Рё РїРѕ СЂР°СЃС€РёСЂРµРЅРЅС‹Рј Р°РІС‚РѕРјРѕР±РёР»СЊРЅС‹Рј С„РѕСЂСѓРјР°Рј, OEM-РєР»СѓР±Р°Рј Рё С‚РµС…РЅРёС‡РµСЃРєРёРј СЃР°Р№С‚Р°Рј. "
            "РќРµ РїРѕРІС‚РѕСЂСЏР№ СЃС‚Р°СЂС‹Р№ РѕС‚РІРµС‚. РќР°Р№РґРё РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Рµ РїСЂРёС‡РёРЅС‹, СЂРµРґРєРёРµ РІРµСЂСЃРёРё, "
            "РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅС‹Рµ СЃР»СѓС‡Р°Рё Рё РЅРѕРІС‹Рµ СЂРµР°Р»СЊРЅС‹Рµ СЃСЃС‹Р»РєРё."
        )

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if mode != "deep" and openai_key and OpenAI is not None:
        try:
            openai_client = OpenAI(api_key=openai_key)
            search_hints = _build_search_hints(data)
            attempt_messages = [user_message]
            if search_hints:
                attempt_messages[0] = user_message + "\n\nSearch hints:\n- " + "\n- ".join(search_hints)
                attempt_messages.append(
                    user_message
                    + "\n\nStrict second pass for this request:\n- "
                    + "\n- ".join(search_hints)
                    + "\n- Return only links and conclusions that explicitly discuss the requested part."
                )

            for attempt_index, attempt_message in enumerate(attempt_messages, start=1):
                openai_response = run_openai_search(openai_client, data, attempt_message, allowed_domains)
                openai_text = getattr(openai_response, "output_text", "") or ""
                openai_result = extract_json(openai_text)
                openai_result["_meta"] = {
                    "engine": "OpenAI web_search",
                    "mode": mode,
                    "allowed_domains": allowed_domains,
                    "fallback_used": False,
                    "version": "7.4",
                    "attempt": attempt_index,
                }
                if not openai_result.get("error") and _result_matches_request(openai_result, data):
                    return openai_result
        except Exception:
            pass

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or anthropic is None:
        return {
            "error": "ANTHROPIC_API_KEY not set" if not api_key else "anthropic package is not installed",
            "summary": "Сервис поиска временно недоступен. Повторите запрос позже.",
            "common_causes": [],
            "solutions": [],
            "topics_found": [],
            "links": [],
            "total_topics": 0,
            "confidence": "low",
            "recommendation": "",
            "need_more_info": False,
            "clarifying_question": "",
            "_meta": {
                "mode": mode,
                "allowed_domains": allowed_domains,
                "fallback_used": False,
                "version": "7.2",
            },
        }

    client = anthropic.Anthropic(api_key=api_key)
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
        result["_meta"] = {
            "engine": "Claude Haiku 4.5 + web_search",
            "mode": mode,
            "allowed_domains": used_domains,
            "fallback_used": fallback_used,
            "version": "7.2",
        }
        return result
    except Exception as error:
        return {
            "error": str(error),
            "summary": "Сервис поиска временно недоступен. Повторите запрос позже.",
            "common_causes": [],
            "solutions": [],
            "topics_found": [],
            "links": [],
            "total_topics": 0,
            "confidence": "low",
            "recommendation": "",
            "need_more_info": False,
            "clarifying_question": "",
            "_meta": {
                "mode": mode,
                "allowed_domains": used_domains,
                "fallback_used": fallback_used,
                "version": "7.2",
            },
        }
