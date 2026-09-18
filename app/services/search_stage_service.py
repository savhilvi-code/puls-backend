from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.services import v2_repository as repo
from app.services.parser_service import (
    ParserUnavailableError,
    parse_diagnostic,
)
from app.services.provider_config import get_search_provider
from app.services.link_service import sanitize_search_links
from app.services.trace_service import bind_trace, emit_event
from app.services.subscription_service import (
    can_run_research,
    consume_research_credit,
)


StageRunner = Callable[
    [dict[str, Any]],
    Awaitable[dict[str, Any]],
]


@dataclass
class ResearchResult:
    episode: dict[str, Any] | None
    runs: list[dict[str, Any]] = field(
        default_factory=list
    )
    links: list[dict[str, Any]] = field(
        default_factory=list
    )
    summary: str = ""
    evidence: dict[str, Any] = field(
        default_factory=dict
    )
    sufficient: bool = False
    quota: dict[str, Any] | None = None
    reused: bool = False


_EVIDENCE_LIST_FIELDS = (
    "common_causes",
    "solutions",
    "unlikely_causes",
    "extracted_cases",
    "topics_found",
)

NO_EVIDENCE = "NO_EVIDENCE"
USEFUL_PRELIMINARY_EVIDENCE = "USEFUL_PRELIMINARY_EVIDENCE"
SUFFICIENT_EVIDENCE = "SUFFICIENT_EVIDENCE"

DEFAULT_DIAGNOSTIC_STRATEGIES = (
    {
        "key": "model_owner",
        "purpose": "Manufacturer/model-specific owner forums and communities.",
    },
    {
        "key": "general_technical",
        "purpose": "General automotive technical and mechanic communities.",
    },
    {
        "key": "regional_owner",
        "purpose": "Regional and language-specific owner communities.",
    },
)

DEFAULT_HOWTO_STRATEGIES = (
    {
        "key": "video",
        "purpose": "Vehicle-specific video and visual how-to sources.",
    },
    *DEFAULT_DIAGNOSTIC_STRATEGIES,
)


def _bounded_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return str(value or "")[:500]
    if isinstance(value, str):
        return value[:600]
    if isinstance(value, list):
        return [_bounded_value(item, depth=depth + 1) for item in value[:4]]
    if isinstance(value, dict):
        return {
            str(key)[:80]: _bounded_value(item, depth=depth + 1)
            for key, item in list(value.items())[:10]
        }
    return value


def _compact_problem_context(context: dict[str, Any] | None) -> dict[str, Any]:
    source = context if isinstance(context, dict) else {}
    vehicle = source.get("vehicle") if isinstance(source.get("vehicle"), dict) else {}
    problem = source.get("problem") if isinstance(source.get("problem"), dict) else {}
    conditions = problem.get("conditions") if isinstance(problem.get("conditions"), dict) else {}

    def texts(value: Any) -> list[str]:
        return [str(item or "")[:260] for item in value[:4] if str(item or "").strip()] if isinstance(value, list) else []

    return {
        "vehicle": {str(key)[:60]: str(value or "")[:100] for key, value in list(vehicle.items())[:8]},
        "problem": {
            "title": str(problem.get("title") or "")[:180],
            "problem_class": str(problem.get("problem_class") or "")[:80],
            "component": str(problem.get("component") or "")[:100],
            "symptoms": texts(problem.get("symptoms")),
            "conditions": {
                str(key)[:60]: str(value or "")[:180]
                for key, value in list(conditions.items())[:5]
            },
            "confirmed_facts": texts(problem.get("confirmed_facts")),
            "checks_summary": str(problem.get("checks_summary") or "")[:350],
            "current_conclusion": str(problem.get("current_conclusion") or "")[:350],
            "next_step": str(problem.get("next_step") or "")[:250],
        },
        "latest_clarification": str(source.get("latest_clarification") or "")[:700],
    }


def _structured_evidence(
    result: dict[str, Any],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    raw = result.get("_raw")
    raw = raw if isinstance(raw, dict) else {}

    for key in _EVIDENCE_LIST_FIELDS:
        value = result.get(key)
        if not isinstance(value, list):
            value = raw.get(key)
        if isinstance(value, list) and value:
            evidence[key] = _bounded_value(value)

    regional = result.get("regional_insights")
    if not isinstance(regional, dict):
        regional = raw.get("regional_insights")
    if isinstance(regional, dict) and regional:
        evidence["regional_insights"] = _bounded_value(regional)

    for key in (
        "recommendation",
        "clarifying_question",
        "confidence",
    ):
        value = str(
            result.get(key)
            or raw.get(key)
            or ""
        ).strip()
        if value:
            evidence[key] = value[:600]

    evidence["need_more_info"] = bool(
        result.get("need_more_info")
        or raw.get("need_more_info")
    )
    return evidence


def _merge_evidence(
    target: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(target)
    for key in _EVIDENCE_LIST_FIELDS:
        values = incoming.get(key)
        if not isinstance(values, list):
            continue
        current = merged.get(key)
        current = current if isinstance(current, list) else []
        seen = {json.dumps(item, sort_keys=True, ensure_ascii=False, default=str) for item in current}
        for item in values:
            marker = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
            if marker not in seen:
                current.append(item)
                seen.add(marker)
        merged[key] = current
    regional = incoming.get("regional_insights")
    if isinstance(regional, dict):
        merged["regional_insights"] = {
            **(merged.get("regional_insights") or {}),
            **regional,
        }
    for key in (
        "recommendation",
        "clarifying_question",
        "confidence",
        "need_more_info",
    ):
        if incoming.get(key) not in (None, "", False):
            merged[key] = incoming[key]
    return merged


def _has_useful_evidence(result: dict[str, Any]) -> bool:
    evidence = _structured_evidence(result)
    return any(
        evidence.get(key)
        for key in (
            "common_causes",
            "solutions",
            "extracted_cases",
            "topics_found",
            "recommendation",
        )
    )


def evidence_is_sufficient(
    result: dict[str, Any],
    *,
    stage_number: int,
) -> bool:
    summary = str(
        result.get("parser_summary")
        or result.get("summary")
        or ""
    ).strip()

    links = (
        result.get("links")
        if isinstance(
            result.get("links"),
            list,
        )
        else []
    )

    cases = (
        result.get("extracted_cases")
        if isinstance(
            result.get("extracted_cases"),
            list,
        )
        else []
    )

    useful = bool(summary or cases or _has_useful_evidence(result))
    evidence_items = len(cases) + sum(
        len(result.get(key) or [])
        for key in ("common_causes", "solutions")
        if isinstance(result.get(key), list)
    )
    strong_source_set = len(links) >= 2 and (evidence_items >= 2 or bool(summary))
    return bool(useful and links and (result.get("sufficient_evidence") is True or strong_source_set))


def accumulated_evidence_state(
    *,
    summary: str,
    evidence: dict[str, Any],
    links: list[dict[str, Any]],
    provider_sufficient: bool = False,
) -> str:
    useful = bool(
        str(summary or "").strip()
        or any(evidence.get(key) for key in _EVIDENCE_LIST_FIELDS)
        or evidence.get("recommendation")
    )
    if not useful:
        return NO_EVIDENCE
    # Provider confidence is advisory; source-backed sufficiency still needs
    # normalized provenance. Useful unlinked analysis remains preliminary.
    evidence_items = sum(
        len(evidence.get(key) or [])
        for key in ("common_causes", "solutions", "extracted_cases")
        if isinstance(evidence.get(key), list)
    )
    strong_source_set = len(links) >= 2 and (evidence_items >= 2 or bool(summary))
    if links and (provider_sufficient or strong_source_set):
        return SUFFICIENT_EVIDENCE
    return USEFUL_PRELIMINARY_EVIDENCE


def next_stage_reason(
    result: dict[str, Any],
    *,
    stage_number: int,
) -> str:
    if evidence_is_sufficient(
        result,
        stage_number=stage_number,
    ):
        return ""

    if stage_number == 1:
        return (
            "Initial stage did not return enough "
            "source-backed evidence."
        )

    return (
        "Previous stage still lacked a clear "
        "source-backed conclusion."
    )


def _links_from_result(
    result: dict[str, Any],
    *,
    query: str = "",
    visual_requested: bool = False,
) -> list[dict[str, Any]]:
    links = result.get("links")

    if not isinstance(links, list):
        return []

    return sanitize_search_links([
        item
        for item in links
        if isinstance(item, dict)
    ], query=query, visual_requested=visual_requested)


def _summary_from_result(
    result: dict[str, Any],
) -> str:
    return str(
        result.get("parser_summary")
        or result.get("summary")
        or result.get("recommendation")
        or ""
    ).strip()


def _stage_payload(
    *,
    stage_number: int,
    vehicle_label: str,
    query: str,
    language: str,
    previous_evidence: list[dict[str, Any]],
    problem_context: dict[str, Any] | None,
    strategy: dict[str, str],
    deep: bool,
) -> dict[str, Any]:
    compact_previous = [
        {
            "stage_number": item.get("stage_number"),
            "source_group": item.get("source_group"),
            "result_summary": str(item.get("result_summary") or "")[:600],
            "evidence": _bounded_value(item.get("evidence") or {}),
            "sources": _bounded_value(item.get("sources") or []),
            "unresolved_reason": str(item.get("unresolved_reason") or "")[:300],
        }
        for item in previous_evidence[-3:]
    ]
    previous_summary = json.dumps(
        compact_previous,
        ensure_ascii=False,
        separators=(",", ":"),
    ) if previous_evidence else ""
    if len(previous_summary) > 6000:
        previous_summary = previous_summary[:6000]

    return {
        "active_car": vehicle_label[:400],
        "symptom": query[:1600],
        "query": query[:1600],
        "evidence_context": previous_summary,
        "problem_context": _compact_problem_context(problem_context),
        "source_group": strategy["key"],
        "stage_purpose": strategy["purpose"],
        "mode": "deep" if deep else "normal",
        "language": language,
    }


def _stage_strategies(trigger_type: str) -> tuple[dict[str, str], ...]:
    return (
        DEFAULT_HOWTO_STRATEGIES
        if str(trigger_type or "").upper() == "HOWTO"
        else DEFAULT_DIAGNOSTIC_STRATEGIES
    )


def _explicit_deep_request(query: str) -> bool:
    lowered = " ".join(str(query or "").lower().split())
    return any(marker in lowered for marker in (
        "глубокий поиск", "поищи глубже", "глубже", "search deeper", "deep search",
    ))


def _deduplicate_links(
    links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in links:
        url = str(
            item.get("url") or ""
        ).strip()

        key = (
            repo.canonical_url(url)
            if url
            else str(item)
        )

        if not key or key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def _explicit_new_research_objective(query: str) -> bool:
    text = " ".join(str(query or "").lower().split())
    markers = (
        "поищи еще",
        "поищи ещё",
        "глубже",
        "другие источники",
        "повтори поиск",
        "не помогло",
        "search again",
        "search deeper",
        "more sources",
        "not helped",
        "youtube",
        "ютуб",
        "видео",
        "video",
        "покажи фото",
        "покажи изображение",
        "покажи схему",
        "как выглядит",
        "где находится",
        "image",
        "photo",
        "diagram",
        "как заменить",
        "как поменять",
        "как снять",
        "как установить",
        "how to replace",
        "how to remove",
        "how to install",
    )
    return any(marker in text for marker in markers)


def _query_terms(text: str) -> set[str]:
    stop = {
        "with", "that", "this", "when", "from", "have",
        "что", "это", "как", "при", "для", "или", "еще", "ещё",
        "меня", "машина", "авто", "теперь", "стало",
    }
    words = {
        "".join(char for char in part.lower() if char.isalnum())
        for part in str(text or "").split()
    }
    return {word[:6] for word in words if len(word) >= 4 and word not in stop}


def _research_intent(text: str, declared: str = "DIAGNOSTIC") -> str:
    lowered = " ".join(str(text or "").lower().split())
    if any(marker in lowered for marker in (
        "youtube", "ютуб", "видео", "video", "как заменить", "как поменять",
        "как снять", "как установить", "how to replace", "how to remove",
        "how to install",
    )):
        return "HOWTO"
    if any(marker in lowered for marker in (
        "мануал", "manual", "инструкц", "ссылк", "link", "схем", "diagram",
        "какое масло", "какую жидкость", "what oil", "which oil", "спецификац",
    )):
        return "REFERENCE"
    normalized = str(declared or "DIAGNOSTIC").upper()
    return normalized if normalized in {"DIAGNOSTIC", "HOWTO", "REFERENCE"} else "DIAGNOSTIC"


def _is_persisted_continuation(
    query: str,
    state: dict[str, Any],
    *,
    trigger_type: str,
) -> bool:
    episode = state.get("episode")
    episode = episode if isinstance(episode, dict) else {}
    context = episode.get("search_context")
    context = context if isinstance(context, dict) else {}
    previous_query = str(context.get("reason") or "").strip()
    if not previous_query:
        return False
    current_trigger = str(trigger_type or "DIAGNOSTIC").upper()
    previous_trigger = str(episode.get("trigger_type") or "DIAGNOSTIC").upper()
    if previous_trigger != current_trigger:
        return False
    if _research_intent(previous_query, previous_trigger) != _research_intent(query, current_trigger):
        return False
    new_terms = _query_terms(query)
    previous_terms = _query_terms(previous_query)
    if not new_terms or not previous_terms:
        return False
    return bool(new_terms & previous_terms)


def _links_from_persisted_sources(
    relations: Any,
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for relation in relations if isinstance(relations, list) else []:
        if not isinstance(relation, dict):
            continue
        source = relation.get("sources")
        source = source if isinstance(source, dict) else relation
        url = str(source.get("url") or "").strip()
        if not url:
            continue
        links.append(
            {
                "title": str(source.get("title") or url).strip(),
                "url": url,
                "description": str(
                    source.get("description")
                    or relation.get("extracted_evidence")
                    or ""
                ).strip(),
                "type": str(source.get("source_type") or source.get("type") or "link").lower(),
                "source_url": str(
                    ((source.get("metadata") or {}) if isinstance(source.get("metadata"), dict) else {}).get("source_page_url")
                    or ""
                ).strip(),
            }
        )
    return _deduplicate_links(links)


def _result_from_persisted_research(
    state: dict[str, Any],
    *,
    quota: dict[str, Any] | None,
    query: str = "",
    visual_requested: bool = False,
) -> ResearchResult:
    episode = state.get("episode")
    runs = state.get("runs")
    runs = runs if isinstance(runs, list) else []
    evidence: dict[str, Any] = {}
    summary = str((episode or {}).get("final_summary") or "").strip()
    sufficient = False
    for run in runs:
        if not isinstance(run, dict):
            continue
        data = run.get("result_data")
        if isinstance(data, dict):
            evidence = _merge_evidence(evidence, _structured_evidence(data))
            summary = _summary_from_result(data) or summary
        sufficient = sufficient or run.get("sufficient_evidence") is True
    return ResearchResult(
        episode=episode if isinstance(episode, dict) else None,
        runs=runs,
        links=sanitize_search_links(
            _links_from_persisted_sources(state.get("sources")),
            query=query,
            visual_requested=visual_requested,
        ),
        summary=summary,
        evidence=evidence,
        sufficient=sufficient,
        quota=quota,
        reused=True,
    )


async def run_search_stages(
    *,
    user_id: str | None,
    vehicle_id: str | None,
    problem_id: str | None,
    vehicle_label: str,
    query: str,
    language: str,
    problem_context: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    trigger_type: str = "DIAGNOSTIC",
    allow_reuse: bool = True,
    max_stages: int | None = None,
    runner: StageRunner = parse_diagnostic,
) -> ResearchResult:
    emit_event("SEARCH", module="search_stage_service", operation="CONTEXT", from_node="Knowledge", to_node="Search Episode", edge_label="MISS → SEARCH", input_data={"trigger_type": trigger_type, "query": query[:240]})
    can_run, subscription = can_run_research(
        user_id=user_id
    )

    # A search episode belongs to a diagnostic problem.
    # Without a persisted problem there is no valid V2
    # search ownership chain.
    if (
        user_id is None
        or problem_id is None
    ):
        return ResearchResult(
            episode=None,
            quota=subscription,
        )

    if allow_reuse and not _explicit_new_research_objective(query):
        persisted = repo.get_latest_problem_research(
            user_id=user_id,
            problem_id=problem_id,
        )
        if (
            isinstance(persisted, dict)
            and persisted.get("episode")
            and _is_persisted_continuation(
                query,
                persisted,
                trigger_type=trigger_type,
            )
        ):
            reused = _result_from_persisted_research(
                persisted,
                quota=subscription,
                query=query,
                visual_requested=bool(
                    ((problem_context or {}).get("request") or {}).get("visual_requested")
                ),
            )
            if reused.summary or reused.links or _has_useful_evidence(reused.evidence):
                return reused

    if not can_run:
        return ResearchResult(
            episode=None,
            quota=subscription,
        )

    episode = repo.create_search_episode(
        user_id=user_id,
        vehicle_id=vehicle_id,
        problem_id=problem_id,
        reason=query,
        conversation_id=conversation_id,
        trigger_type=trigger_type,
    )

    episode_id = (
        episode or {}
    ).get("id")

    if episode_id:
        bind_trace(search_episode_id=episode_id)
        emit_event("SEARCH_EPISODE", module="search_stage_service", operation="WRITE", from_node="Search Episode", to_node="search_episodes", table_name="search_episodes", record_id=episode_id, output_data={"trigger_type": trigger_type})

    if episode_id is None:
        return ResearchResult(
            episode=None,
            quota=subscription,
        )

    previous_evidence: list[
        dict[str, Any]
    ] = []

    all_links: list[
        dict[str, Any]
    ] = []

    runs: list[
        dict[str, Any]
    ] = []

    final_summary = ""
    accumulated_evidence: dict[str, Any] = {}
    sufficient = False
    evidence_state = NO_EVIDENCE
    provider_sufficient = False
    final_status = "INSUFFICIENT_EVIDENCE"

    strategies = _stage_strategies(trigger_type)
    total_stages = len(strategies) if max_stages is None else min(max(int(max_stages), 1), len(strategies))
    deep_requested = _explicit_deep_request(query)

    for stage_number in range(
        1,
        total_stages + 1,
    ):
        strategy = strategies[stage_number - 1]
        emit_event("SEARCH_STAGE", module="search_stage_service", operation="SEARCH", status="STARTED", from_node="Search Episode" if stage_number == 1 else f"Stage {stage_number - 1}", to_node=f"Stage {stage_number}", edge_label=strategy["key"], stage_number=stage_number, source_group=strategy["key"], provider=get_search_provider())
        emit_event("SOURCE_GROUP", module="search_stage_service", operation="CONTEXT", from_node=f"Stage {stage_number}", to_node=strategy["key"], edge_label="SOURCE GROUP", stage_number=stage_number, source_group=strategy["key"])
        emit_event("PROVIDER", module="search_stage_service", operation="SEARCH", status="STARTED", from_node=strategy["key"], to_node=get_search_provider(), edge_label="PROVIDER", stage_number=stage_number, source_group=strategy["key"], provider=get_search_provider())
        stage_started = time.monotonic()
        input_context = {
            "vehicle": vehicle_label,
            "query": query,
            "previous_stages": previous_evidence,
            "problem_context": _compact_problem_context(problem_context),
            "source_group": strategy["key"],
            "stage_purpose": strategy["purpose"],
        }

        try:
            result = await runner(
                _stage_payload(
                    stage_number=stage_number,
                    vehicle_label=vehicle_label,
                    query=query,
                    language=language,
                    previous_evidence=(
                        previous_evidence
                    ),
                    problem_context=problem_context,
                    strategy=strategy,
                    deep=deep_requested,
                )
            )

            if not isinstance(result, dict):
                result = {}

            status = "COMPLETED"
            error_message = ""

        except ParserUnavailableError as exc:
            result = {
                "error": str(exc),
                "links": [],
                "parser_summary": "",
            }

            status = "FAILED"
            error_message = str(exc)

        links = _links_from_result(
            result,
            query=query,
            visual_requested=bool(
                ((problem_context or {}).get("request") or {}).get("visual_requested")
            ),
        )

        links = _deduplicate_links(
            links
        )

        summary = _summary_from_result(
            result
        )
        stage_evidence = _structured_evidence(result)
        accumulated_evidence = _merge_evidence(
            accumulated_evidence,
            stage_evidence,
        )
        stage_links = _deduplicate_links(all_links + links)
        if summary:
            final_summary = summary
        provider_sufficient = provider_sufficient or result.get("sufficient_evidence") is True
        evidence_state = (
            accumulated_evidence_state(
                summary=final_summary,
                evidence=accumulated_evidence,
                links=stage_links,
                provider_sufficient=provider_sufficient,
            )
            if status == "COMPLETED"
            else evidence_state
        )
        sufficient = evidence_state == SUFFICIENT_EVIDENCE
        result["evidence_state"] = evidence_state
        if status != "COMPLETED":
            reason = "Search provider failed."
        elif evidence_state == NO_EVIDENCE:
            reason = "This source group produced no useful evidence."
        elif evidence_state == USEFUL_PRELIMINARY_EVIDENCE:
            reason = "Useful preliminary evidence lacks enough source provenance."
        else:
            reason = ""

        # Supabase V2 stores counts in these columns,
        # not arrays of source objects.
        sources_found_count = len(
            links
        )

        relevant_sources_count = (
            len(links)
            if sufficient
            else 0
        )

        raw = result.get("_raw")

        if not isinstance(raw, dict):
            raw = {}

        meta = raw.get("_meta")

        if not isinstance(meta, dict):
            meta = {}

        run_payload = {
            "stage_number": stage_number,
            "run_type": (
                "parser"
                if stage_number == 1
                else "expanded_parser"
            ),
            "status": status,
            "query": query,
            "input_context": input_context,
            "result_data": result,
            "result_summary": summary,
            "sources_found": (
                sources_found_count
            ),
            "relevant_sources": (
                relevant_sources_count
            ),
            "sufficient_evidence": sufficient,
            "next_stage_reason": reason,
            "provider": get_search_provider(),
            "model": str(
                meta.get("engine")
                or ""
            ),
            "error_message": error_message,
        }

        saved_run = (
            repo.create_search_run(
                user_id=user_id,
                episode_id=episode_id,
                payload=run_payload,
            )
            or run_payload
        )

        runs.append(
            saved_run
        )

        emit_event("SEARCH_STAGE", module="search_stage_service", operation="RESULT", status=status, from_node=get_search_provider(), to_node="Sources", edge_label=f"{sources_found_count} SOURCES", table_name="search_runs", record_id=str(saved_run.get("id") or "") or None, stage_number=stage_number, source_group=strategy["key"], provider=get_search_provider(), model=str(meta.get("engine") or "") or None, duration_ms=int((time.monotonic() - stage_started) * 1000), output_data={"summary": summary[:500], "source_count": sources_found_count, "relevant_sources": relevant_sources_count, "evidence_state": evidence_state, "sufficient": sufficient}, telemetry=meta)
        emit_event("EVIDENCE", module="search_stage_service", operation="EVIDENCE", status="COMPLETED" if evidence_state != NO_EVIDENCE else "WARNING", from_node="Sources", to_node="Evidence", edge_label=evidence_state, stage_number=stage_number, source_group=strategy["key"], output_data={"evidence_state": evidence_state, "sufficient": sufficient})
        emit_event("LLM", module="search_stage_service", operation="RESULT", status=status, from_node="Evidence", to_node="LLM", edge_label="SYNTHESIS", stage_number=stage_number, source_group=strategy["key"], provider=get_search_provider(), model=str(meta.get("engine") or "") or None, telemetry=meta)

        previous_evidence.append(
            {
                "stage_number": stage_number,
                "result_summary": summary,
                "sources_found": (
                    sources_found_count
                ),
                "relevant_sources": (
                    relevant_sources_count
                ),
                "sufficient_evidence": (
                    sufficient
                ),
                "evidence": stage_evidence,
                "source_group": strategy["key"],
                "sources": [
                    {
                        "title": str(item.get("title") or "").strip(),
                        "url": str(item.get("url") or "").strip(),
                        "type": str(item.get("type") or "link").strip(),
                    }
                    for item in links[:6]
                ],
                "unresolved_reason": reason,
            }
        )

        all_links.extend(
            links
        )

        for link in links:
            emit_event("SOURCE", module="search_stage_service", operation="RESULT", from_node=f"Stage {stage_number}", to_node="Sources", edge_label="SOURCE", stage_number=stage_number, source_group=strategy["key"], output_data={"title": link.get("title"), "url": link.get("url"), "domain": link.get("domain"), "type": link.get("type"), "retained": True})
            source = repo.upsert_source(
                link
            )

            source_id = (
                source or {}
            ).get("id")

            if source_id is None:
                continue

            emit_event("SOURCE", module="search_stage_service", operation="VERIFY", from_node="sources", to_node="Evidence", edge_label="RETAINED", table_name="sources", record_id=str(source_id), stage_number=stage_number, source_group=strategy["key"], output_data={"source_id": source_id, "title": link.get("title"), "url": link.get("url"), "retained": True})

            repo.link_problem_source(
                user_id=user_id,
                problem_id=problem_id,
                source_id=source_id,
                search_run_id=(
                    saved_run.get("id")
                ),
                summary=summary,
                relevance=(
                    0.7
                    if sufficient
                    else 0.4
                ),
            )
            emit_event("DATABASE", module="search_stage_service", operation="WRITE", from_node="Sources", to_node="problem_sources", table_name="problem_sources", record_id=str(source_id), related_ids={"problem_id": problem_id, "search_run_id": saved_run.get("id")})

        if status == "FAILED":
            final_status = "FAILED"
            break

        if sufficient:
            final_status = "COMPLETED"
            break

    if evidence_state == USEFUL_PRELIMINARY_EVIDENCE:
        final_status = "COMPLETED"

    all_links = _deduplicate_links(
        all_links
    )

    updated_episode = (
        repo.update_search_episode(
            user_id=user_id,
            episode_id=episode_id,
            payload={
                "status": final_status,
                "final_summary": (
                    final_summary
                ),
            },
        )
    )

    if updated_episode:
        episode = updated_episode
    emit_event("SEARCH_EPISODE", module="search_stage_service", operation="RESULT", status=final_status, from_node="LLM", to_node="ANSWER", edge_label=evidence_state, table_name="search_episodes", record_id=episode_id, output_data={"summary": final_summary[:500], "evidence_state": evidence_state, "stage_count": len(runs)})

    # One research request consumes one credit,
    # regardless of how many internal stages ran.
    subscription = consume_research_credit(
        user_id=user_id
    )

    return ResearchResult(
        episode=episode,
        runs=runs,
        links=all_links,
        summary=final_summary,
        evidence=accumulated_evidence,
        sufficient=sufficient,
        quota=subscription,
    )
