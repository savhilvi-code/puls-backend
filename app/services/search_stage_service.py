from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.services import v2_repository as repo
from app.services.parser_service import (
    ParserUnavailableError,
    parse_diagnostic,
)
from app.services.provider_config import get_search_provider
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
            evidence[key] = value[:6]

    regional = result.get("regional_insights")
    if not isinstance(regional, dict):
        regional = raw.get("regional_insights")
    if isinstance(regional, dict) and regional:
        evidence["regional_insights"] = dict(list(regional.items())[:6])

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
            evidence[key] = value[:900]

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

    if result.get("sufficient_evidence") is True:
        return True

    if (summary or _has_useful_evidence(result)) and links:
        return True

    if (
        stage_number >= 3
        and (
            summary
            or links
            or cases
            or _has_useful_evidence(result)
        )
    ):
        return True

    return False


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
) -> list[dict[str, Any]]:
    links = result.get("links")

    if not isinstance(links, list):
        return []

    return [
        item
        for item in links
        if isinstance(item, dict)
    ]


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
) -> dict[str, Any]:
    previous_summary = json.dumps(
        previous_evidence,
        ensure_ascii=False,
        separators=(",", ":"),
    ) if previous_evidence else ""

    return {
        "active_car": vehicle_label,
        "symptom": query,
        "query": query,
        "evidence_context": previous_summary,
        "mode": (
            "deep"
            if stage_number > 1
            else "normal"
        ),
        "language": language,
    }


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


def _is_persisted_continuation(
    query: str,
    state: dict[str, Any],
) -> bool:
    episode = state.get("episode")
    episode = episode if isinstance(episode, dict) else {}
    context = episode.get("search_context")
    context = context if isinstance(context, dict) else {}
    previous_query = str(context.get("reason") or "").strip()
    if not previous_query:
        return True
    new_terms = _query_terms(query)
    previous_terms = _query_terms(previous_query)
    if not new_terms or not previous_terms:
        return True
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
            }
        )
    return _deduplicate_links(links)


def _result_from_persisted_research(
    state: dict[str, Any],
    *,
    quota: dict[str, Any] | None,
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
        links=_links_from_persisted_sources(state.get("sources")),
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
    max_stages: int = 3,
    runner: StageRunner = parse_diagnostic,
) -> ResearchResult:
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

    if not _explicit_new_research_objective(query):
        persisted = repo.get_latest_problem_research(
            user_id=user_id,
            problem_id=problem_id,
        )
        if (
            isinstance(persisted, dict)
            and persisted.get("episode")
            and _is_persisted_continuation(query, persisted)
        ):
            return _result_from_persisted_research(
                persisted,
                quota=subscription,
            )

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
    )

    episode_id = (
        episode or {}
    ).get("id")

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
    final_status = "INSUFFICIENT_EVIDENCE"

    total_stages = max(
        int(max_stages or 1),
        1,
    )

    for stage_number in range(
        1,
        total_stages + 1,
    ):
        input_context = {
            "vehicle": vehicle_label,
            "query": query,
            "previous_stages": previous_evidence,
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
            result
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

        sufficient = (
            evidence_is_sufficient(
                result,
                stage_number=stage_number,
            )
            if status == "COMPLETED"
            else False
        )

        reason = (
            next_stage_reason(
                result,
                stage_number=stage_number,
            )
            if status == "COMPLETED"
            else "Search provider failed."
        )

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

        if summary:
            final_summary = summary

        for link in links:
            source = repo.upsert_source(
                link
            )

            source_id = (
                source or {}
            ).get("id")

            if source_id is None:
                continue

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

        if status == "FAILED":
            final_status = "FAILED"
            break

        if sufficient:
            final_status = "COMPLETED"
            break

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
