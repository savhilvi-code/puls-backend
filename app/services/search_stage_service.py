from __future__ import annotations

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
    sufficient: bool = False
    quota: dict[str, Any] | None = None


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

    if summary and links:
        return True

    if (
        stage_number >= 3
        and (
            summary
            or links
            or cases
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
    previous_summary = "\n".join(
        (
            f"Stage {item.get('stage_number')}: "
            f"{item.get('result_summary') or 'no sufficient evidence'}"
        )
        for item in previous_evidence
    )

    return {
        "active_car": vehicle_label,
        "symptom": query,
        "query": query,
        "evidence_context": previous_summary,
        "mode": (
            "expanded"
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

    if not can_run:
        return ResearchResult(
            episode=None,
            quota=subscription,
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
        sufficient=sufficient,
        quota=subscription,
    )
