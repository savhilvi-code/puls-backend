from __future__ import annotations

import json
import logging
import os
import re

import httpx

from app.schemas.parser import DiagnosticRequest
from app.services.search_provider import run_search_provider, unique_domains

logger = logging.getLogger(__name__)

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

GENERAL_TECHNICAL_DOMAINS = [
    "pistonheads.com",
    "bobistheoilguy.com",
    "mechanics.stackexchange.com",
    "obd-codes.com",
    "carcomplaints.com",
    "garagejournal.com",
]

REGIONAL_OWNER_DOMAINS = [
    "drive2.ru",
    "drom.ru",
    "auto.ru",
    "nissanstyle.ru",
    "nissan-org.ru",
    "carclub.ru",
    "minkara.carview.co.jp",
    "autohome.com.cn",
    "xcar.com.cn",
    "pcauto.com.cn",
    "motor-talk.de",
    "forum.auto.fr",
    "avtoportali.ge",
]


SYSTEM_PROMPT = """ТЫ — опытный автодиагност с 20+ лет практики. Специализируешься на японских, европейских и американских автомобилях, турбомоторах, системах ЭБУ/ECU.

У тебя есть инструмент web_search. ОБЯЗАТЕЛЬНО используй его для поиска реальных обсуждений на форумах перед ответом.
Для текущей стадии используй только переданные allowed domains и её Stage purpose; не повторяй другие группы источников.

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
4. Приоритет языка/региона выбирай по рынку, языку запроса и доступности источников, а не по hardcoded марке
5. Если регион неизвестен, сравни несколько релевантных рынков и явно отделяй факты от гипотез
6. Если симптом после прогрева — анализируй датчики, ЭБУ, VVT/VCT, термостат и турбину
7. Если симптом звуковой — определи локацию: двигатель, подвеска, тормоза или трансмиссия
8. Дай пошаговый план диагностики от простого к сложному
9. Не выдумывай ссылки
10. Обязательно заполни `links` реальными URL из найденных тем, если хоть один подходящий источник найден
11. Отвечай на языке запроса пользователя

КРИТИЧЕСКИ ВАЖНО: ищи молча. Не печатай ход поиска, переводы запросов, преамбулу или комментарии.
Верни ТОЛЬКО один компактный валидный JSON без markdown и backticks. summary — не более 500 символов; common_causes, solutions, links и topics_found — не более 4 элементов каждый; каждое description/key_info — не более 300 символов:
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
    {"title": "Название материала", "url": "https://real-link", "description": "Ключевая подсказка", "type": "link|video|image"}
  ],
  "topics_found": [
    {"title": "Заголовок темы", "forum": "drive2.ru", "url": "https://реальная-ссылка", "lang": "ru", "relevance": "high", "key_info": "Что решило проблему"}
  ],
  "total_topics": 5,
  "confidence": "high|medium|low",
  "recommendation": "С чего начать",
  "need_more_info": false,
  "clarifying_question": "",
  "sufficient_evidence": false
}

Set sufficient_evidence=true only when the conclusion is supported by the real URLs returned in links.
"""


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
    source_group = str(data.source_group or "all_configured").strip().lower()
    text = f"{data.query} {data.car_info or ''}"
    if source_group == "model_owner":
        domains = []
        for group in detect_forum_groups(text):
            if group != "general":
                domains.extend(EXTRA_FORUMS.get(group, []))
        if not domains:
            domains = ["auto.ru", "carclub.ru", "pistonheads.com"]
    elif source_group == "general_technical":
        domains = list(GENERAL_TECHNICAL_DOMAINS)
    elif source_group == "regional_owner":
        domains = list(REGIONAL_OWNER_DOMAINS)
    elif source_group == "video":
        domains = ["youtube.com", "youtu.be"]
    else:
        domains = list(REGIONAL_OWNER_DOMAINS) + list(GENERAL_TECHNICAL_DOMAINS)
        for group in detect_forum_groups(text):
            domains.extend(EXTRA_FORUMS.get(group, []))
    if _has_explicit_video_intent(data) and source_group == "all_configured":
        domains.extend(["youtube.com", "youtu.be"])
    return unique_domains(domains)


def _remote_parser_url() -> str:
    # The remote parser is optional. An unset variable must not silently call
    # a legacy deployment: production no longer exposes that endpoint and the
    # implicit fallback added one guaranteed 404 before every paid stage.
    raw = str(os.getenv("PARSER_API_URL", "") or "").strip()
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
        "evidence_context": data.evidence_context,
        "problem_context": data.problem_context,
        "source_group": data.source_group,
        "stage_purpose": data.stage_purpose,
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


def _combined_request_text(data: DiagnosticRequest) -> str:
    text = " ".join(
        part.strip()
        for part in (
            str(data.query or ""),
            str(data.car_info or ""),
            str(data.evidence_context or ""),
        )
        if str(part or "").strip()
    ).lower()
    return text


def _has_explicit_video_intent(data: DiagnosticRequest) -> bool:
    text = _combined_request_text(data)
    return any(
        term in text
        for term in (
            "youtube", "youtu.be", "ютуб", "видео", "video",
            "как заменить", "как поменять", "как снять", "как установить",
            "how to replace", "how to remove", "how to install",
        )
    )


def _has_explicit_visual_intent(data: DiagnosticRequest) -> bool:
    text = _combined_request_text(data)
    return any(
        term in text
        for term in (
            "покажи фото", "покажи изображение", "покажи схему",
            "как выглядит", "где находится", "image", "photo", "diagram",
            "what does it look like", "where is it located",
        )
    )


def _build_search_hints(data: DiagnosticRequest) -> list[str]:
    hints: list[str] = []
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
    )
    setup_markers = ("настро", "регулиров", "tune", "adjust", "setup", "set up")
    if any(term in text for term in airflow_terms) and any(term in text for term in setup_markers):
        hints.extend(
            [
                "Treat this as an airflow-meter adjustment request, not a generic power-loss diagnosis.",
                "Keep the source-specific sensor type: VAF/AFM/flap meter, hot-wire MAF, MAP, or another type only when the source supports it.",
                "Prefer sources that explicitly discuss adjustment, cleaning, wiring, bypass screws, spring tension, contact tracks, calibration, or test values for the requested vehicle context.",
                "Reject unrelated boost, knock, coolant, transmission, or suspension results unless they directly discuss the requested airflow-meter operation.",
            ]
        )
    turbo_markers = ("\u0442\u0443\u0440\u0431\u0438\u043d", "turbo", "boost", "wastegate", "\u0432\u0435\u0441\u0442\u0433\u0435\u0439\u0442")
    if any(term in text for term in turbo_markers) and any(term in text for term in setup_markers):
        hints.extend(
            [
                "Treat this as a turbo setup / boost control / wastegate adjustment request, not as a generic warm-engine power-loss diagnosis.",
                "Reject unrelated topics about coolant temperature sensor, ignition misfire, transmission noise, suspension, or general loss of power unless they explicitly discuss turbo boost control on the requested engine.",
                "Return only links and conclusions that explicitly discuss turbo setup, boost adjustment, wastegate, actuator preload, boost leaks, or boost controller behavior for the supplied vehicle context.",
                "In the final summary, answer the requested operation directly: what to check first, what is adjusted mechanically/electronically, and what mistakes are dangerous.",
            ]
        )
    video_terms = (
        "youtube",
        "youtu.be",
        "ютуб",
        "видео",
        "video",
    )
    how_to_terms = (
        "как заменить",
        "как поменять",
        "как снять",
        "как установить",
        "how to replace",
        "how to remove",
        "how to install",
    )
    if any(term in text for term in video_terms + how_to_terms):
        hints.extend(
            [
                "The user explicitly wants a how-to or video result. Include relevant YouTube results when they directly match the requested vehicle, part, and operation.",
                "Mark YouTube results with links[].type = video. Do not add generic or unrelated videos.",
            ]
        )
    image_terms = (
        "покажи фото",
        "покажи изображение",
        "покажи схему",
        "как выглядит",
        "где находится",
        "image",
        "photo",
        "diagram",
        "what does it look like",
        "where is it located",
    )
    if any(term in text for term in image_terms):
        hints.extend(
            [
                "The user explicitly wants visual material. Include a directly relevant image or diagram URL when the search result provides one.",
                "Mark direct visual results with links[].type = image and keep the source page URL when a direct image URL is unavailable.",
            ]
        )
    return hints


def _has_usable_remote_evidence(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    for key in (
        "links",
        "topics_found",
        "common_causes",
        "solutions",
        "extracted_cases",
    ):
        value = result.get(key)
        if isinstance(value, (list, dict)) and value:
            return True
    boilerplate = (
        "service is temporarily unavailable",
        "сервис поиска временно недоступен",
    )
    for key in ("summary", "parser_summary", "recommendation"):
        value = str(result.get(key) or "").strip().lower()
        if value and not any(text in value for text in boilerplate):
            return True
    return False


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
    blob = _result_text_blob(result)
    text = _combined_request_text(data)
    airflow_terms = (
        "расходомер",
        "vaf",
        "afm",
        "flap",
        "лопат",
        "air flow meter",
        "vane air",
    )
    setup_markers = ("настро", "регулиров", "tune", "adjust", "setup", "set up")
    if any(term in text for term in airflow_terms) and any(term in text for term in setup_markers):
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

    turbo_markers = ("\u0442\u0443\u0440\u0431\u0438\u043d", "turbo", "boost", "wastegate", "\u0432\u0435\u0441\u0442\u0433\u0435\u0439\u0442")
    setup_markers = ("\u043d\u0430\u0441\u0442\u0440\u043e", "\u0440\u0435\u0433\u0443\u043b\u0438\u0440\u043e\u0432", "tune", "adjust", "setup", "set up")
    turbo_setup_request = any(term in text for term in turbo_markers) and any(term in text for term in setup_markers)
    if turbo_setup_request:
        focus_terms = (
            "\u0442\u0443\u0440\u0431\u0438\u043d",
            "turbo",
            "boost",
            "wastegate",
            "\u0432\u0435\u0441\u0442\u0433\u0435\u0439\u0442",
            "\u043d\u0430\u0434\u0434\u0443\u0432",
            "actuator",
            "\u0430\u043a\u0442\u0443\u0430\u0442\u043e\u0440",
            "boost controller",
        )
        unrelated_terms = (
            "\u043f\u043e\u0434\u0432\u0435\u0441\u043a",
            "suspension",
            "transmission",
            "\u0442\u0440\u0430\u043d\u0441\u043c\u0438\u0441",
            "coolant temperature sensor",
            "\u0434\u0430\u0442\u0447\u0438\u043a \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u044b \u043e\u0445\u043b\u0430\u0436\u0434\u0430\u044e\u0449\u0435\u0439 \u0436\u0438\u0434\u043a\u043e\u0441\u0442\u0438",
            "\u0434\u0442\u043e\u0436",
        )
        has_focus = any(term in blob for term in focus_terms)
        has_only_unrelated = any(term in blob for term in unrelated_terms) and not has_focus
        return has_focus and not has_only_unrelated

    return True


async def diagnose(data: DiagnosticRequest) -> dict:
    mode = data.mode.lower().strip()
    allowed_domains = build_allowed_domains(data)
    remote_url = _remote_parser_url()

    if remote_url and not (
        _has_explicit_video_intent(data)
        or _has_explicit_visual_intent(data)
    ):
        try:
            remote_result = await _call_remote_parser(data, remote_url)
            if _has_usable_remote_evidence(remote_result):
                if remote_result.get("error"):
                    warning = str(remote_result.pop("error") or "").strip()
                    meta = remote_result.get("_meta")
                    if not isinstance(meta, dict):
                        meta = {}
                    meta["warning"] = warning
                    meta["partial_result_recovered"] = True
                    remote_result["_meta"] = meta
                return _normalize_parser_result(
                    remote_result,
                    mode=mode,
                    source="remote parser api",
                )
        except Exception as exc:
            logger.exception("Remote parser call failed for %s: %s", remote_url, exc)
            pass

    context_parts = []
    if data.car_info:
        context_parts.append(f"Машина пользователя: {data.car_info}")
    if data.evidence_context:
        context_parts.append(f"Previous search evidence: {data.evidence_context}")
    if data.problem_context:
        context_parts.append(
            "Compact Problem context: "
            + json.dumps(data.problem_context, ensure_ascii=False, separators=(",", ":"))[:4000]
        )
    if data.stage_purpose:
        context_parts.append(f"Stage purpose: {data.stage_purpose[:300]}")
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
    user_message += (
        "\n\nПриоритетные автомобильные домены для поиска: "
        + ", ".join(allowed_domains)
        + "."
    )
    if mode == "deep":
        user_message += (
            "\n\nРЕЖИМ DEEP SEARCH: пользователь попросил больше информации. "
            "Ищи по расширенным автомобильным форумам, OEM-клубам и техническим сайтам. "
            "Не повторяй старый ответ. Найди дополнительные причины, редкие версии, "
            "подтверждённые случаи и новые реальные ссылки."
        )
    search_hints = _build_search_hints(data)
    if search_hints:
        user_message += "\n\nSearch hints:\n- " + "\n- ".join(search_hints)

    return run_search_provider(
        data=data,
        user_message=user_message,
        allowed_domains=allowed_domains,
        fallback_domains=FALLBACK_DOMAINS,
        system_prompt=SYSTEM_PROMPT,
        search_hints=search_hints,
        extract_json=extract_json,
        result_matches_request=_result_matches_request,
    )
