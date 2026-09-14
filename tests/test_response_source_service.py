import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.router import RouterDecision
from app.services import decision_engine
from app.services.response_source_service import filter_response_sources


def _toyota_oil_links() -> list[dict]:
    return [
        {
            "title": "Engine oil change for Toyota Crown 1G-GZE",
            "url": "https://example.com/engine-oil",
            "description": "Owners discuss 5W-30 and 5W-40 engine oil.",
            "type": "link",
        },
        {
            "title": "Drive belts for Toyota Crown",
            "url": "https://example.com/belts",
            "description": "Belts and pulley replacement notes.",
            "type": "link",
        },
        {
            "title": "Valve stem seals on 1G-GZE",
            "url": "https://example.com/valve-seals",
            "description": "Oil consumption and cylinder head work.",
            "type": "link",
        },
        {
            "title": "Automatic transmission fluid replacement",
            "url": "https://example.com/atf",
            "description": "ATF service and transmission mounts.",
            "type": "link",
        },
    ]


class ResponseSourceServiceTests(unittest.TestCase):
    def test_engine_oil_keeps_engine_oil_link(self):
        result = filter_response_sources(
            current_query="Toyota Crown 1G-GZE what engine oil to use",
            effective_symptom="what engine oil to use",
            answer_context="Use 5W-30 or 5W-40 engine oil.",
            links=_toyota_oil_links(),
            extracted_cases=[],
        )

        self.assertEqual([item["url"] for item in result], ["https://example.com/engine-oil"])

    def test_engine_oil_removes_transmission_atf_link(self):
        result = filter_response_sources(
            current_query="what engine oil to use",
            effective_symptom="what engine oil to use",
            answer_context="Use 5W-30 engine oil.",
            links=_toyota_oil_links(),
            extracted_cases=[],
        )

        self.assertNotIn("https://example.com/atf", [item["url"] for item in result])

    def test_engine_oil_removes_belt_link(self):
        result = filter_response_sources(
            current_query="what engine oil to use",
            effective_symptom="what engine oil to use",
            answer_context="Use 5W-30 engine oil.",
            links=_toyota_oil_links(),
            extracted_cases=[],
        )

        self.assertNotIn("https://example.com/belts", [item["url"] for item in result])

    def test_valve_seal_link_depends_on_oil_consumption_context(self):
        no_consumption = filter_response_sources(
            current_query="what engine oil to use",
            effective_symptom="what engine oil to use",
            answer_context="Use 5W-30 engine oil.",
            links=_toyota_oil_links(),
            extracted_cases=[],
        )
        with_consumption = filter_response_sources(
            current_query="what engine oil to use",
            effective_symptom="what engine oil to use",
            answer_context="The engine may have increased oil consumption.",
            links=_toyota_oil_links(),
            extracted_cases=[],
        )

        self.assertNotIn("https://example.com/valve-seals", [item["url"] for item in no_consumption])
        self.assertIn("https://example.com/valve-seals", [item["url"] for item in with_consumption])

    def test_unknown_topic_keeps_links_unchanged(self):
        links = _toyota_oil_links()

        result = filter_response_sources(
            current_query="Toyota Crown stalls hot",
            effective_symptom="stalls hot",
            answer_context="Check spark and fuel pressure.",
            links=links,
            extracted_cases=[],
        )

        self.assertEqual(result, links)

    def test_filter_does_not_mutate_discovered_sources(self):
        links = _toyota_oil_links()
        original_urls = [item["url"] for item in links]

        result = filter_response_sources(
            current_query="what engine oil to use",
            effective_symptom="what engine oil to use",
            answer_context="Use 5W-30 engine oil.",
            links=links,
            extracted_cases=[],
        )

        self.assertEqual([item["url"] for item in links], original_urls)
        self.assertEqual([item["url"] for item in result], ["https://example.com/engine-oil"])


class ResponseSourceChatFlowTests(unittest.TestCase):
    def test_chat_response_links_use_filtered_sources_and_preserve_parser_evidence(self):
        parsed_case = {
            "forums_found": ["drive2.ru"],
            "links": _toyota_oil_links(),
            "extracted_cases": [
                {
                    "cause": "Owners use 5W-30 or 5W-40 engine oil in 1G-GZE.",
                    "solution": "Choose quality engine oil and replace the filter.",
                }
            ],
            "parser_summary": "For Toyota Crown GS131 1G-GZE, owners commonly use 5W-30 or 5W-40 engine oil.",
            "topics_found": [],
            "_raw": {"links": _toyota_oil_links()},
        }
        captured = {}

        async def fake_update_user_after_response(*args, **kwargs):
            captured["kwargs"] = kwargs

        async def fake_translate(*, segments, target_language):
            return list(segments)

        with (
            patch.object(decision_engine, "get_or_create_user", new=AsyncMock(return_value=SimpleNamespace(id=1, car_info="", conversation_history=""))),
            patch.object(decision_engine, "resolve_user_vehicle", return_value=None),
            patch.object(
                decision_engine,
                "route_message",
                new=AsyncMock(
                    return_value=RouterDecision(
                        message_type="new_diagnostic",
                        language="en",
                        ready_to_search=True,
                    )
                ),
            ),
            patch.object(decision_engine, "get_latest_conversation_context", return_value={}),
            patch.object(decision_engine, "find_matching_case", new=AsyncMock(return_value=None)),
            patch.object(decision_engine, "find_matching_history_case", new=AsyncMock(return_value=None)),
            patch.object(decision_engine, "can_run_parser", return_value=(True, {"requests_remaining": 5})),
            patch.object(decision_engine, "parse_diagnostic", new=AsyncMock(return_value=parsed_case)),
            patch.object(decision_engine, "run_diagnostic_provider", return_value=None),
            patch.object(decision_engine, "translate_segments", new=fake_translate),
            patch.object(decision_engine, "update_user_after_response", new=fake_update_user_after_response),
            patch.object(decision_engine, "ensure_user_subscription"),
        ):
            response = asyncio.run(
                decision_engine.process_chat_message(
                    {
                        "message": "Toyota Crown GS131 1G-GZE what engine oil to use P0000",
                        "language": "en",
                    },
                    source="web",
                )
            )

        self.assertEqual([item.url for item in response.links], ["https://example.com/engine-oil"])
        self.assertEqual([item["url"] for item in captured["kwargs"]["links"]], ["https://example.com/engine-oil"])
        self.assertEqual(len(captured["kwargs"]["parsed_case"]["links"]), 4)
        self.assertEqual(len(captured["kwargs"]["parsed_case"]["_raw"]["links"]), 4)

    def test_chat_response_contract_remains_unchanged(self):
        response = decision_engine.ChatResponse(answer="ok", links=[], quota={"remaining": 1})

        self.assertEqual(set(response.model_dump().keys()), {"answer", "links", "quota"})


if __name__ == "__main__":
    unittest.main()
