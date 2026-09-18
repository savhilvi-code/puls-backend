import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.schemas.parser import DiagnosticRequest
from app.services import parser_engine, parser_service, search_provider


def _request(mode: str = "normal") -> DiagnosticRequest:
    return DiagnosticRequest(
        query="Toyota Crown 1G-GZE airflow meter setup",
        lang="en",
        car_info="Toyota Crown GS131 1G-GZE",
        evidence_context="Stage 1 found airflow references.",
        mode=mode,
    )


def _parser_payload(summary: str = "diagnosis") -> dict:
    return {
        "summary": summary,
        "common_causes": [{"cause": "cause"}],
        "solutions": [{"title": "check", "description": "solution"}],
        "links": [{"title": "source", "url": "https://example.com/thread", "description": "details", "type": "link"}],
        "topics_found": [],
        "recommendation": "start here",
        "need_more_info": False,
    }


class ParserProviderV2Tests(unittest.TestCase):
    def test_openai_provider_uses_deep_context_size_for_deep_stage(self):
        captured = {}

        def fake_openai_search(client, data, user_message, domains, *, system_prompt):
            captured["mode"] = data.mode
            return SimpleNamespace(output_text='{"summary":"openai ok"}')

        with (
            patch.dict(os.environ, {"SEARCH_PROVIDER": "openai", "OPENAI_API_KEY": "test"}, clear=False),
            patch.object(search_provider, "OpenAI", return_value=object()),
            patch.object(search_provider, "run_openai_search", side_effect=fake_openai_search) as openai_call,
            patch.object(search_provider, "run_claude_search") as claude_call,
        ):
            result = search_provider.run_search_provider(
                data=_request(mode="deep"),
                user_message="message",
                allowed_domains=["example.com"],
                fallback_domains=[],
                system_prompt="prompt",
                search_hints=[],
                extract_json=parser_engine.extract_json,
                result_matches_request=lambda result, data: True,
            )

        self.assertEqual(result["summary"], "openai ok")
        self.assertEqual(captured["mode"], "deep")
        openai_call.assert_called_once()
        claude_call.assert_not_called()

    def test_parser_response_contract_is_preserved_inside_stage_tool(self):
        with patch.object(parser_service, "diagnose", new=AsyncMock(return_value=_parser_payload("contract ok"))):
            result = asyncio.run(
                parser_service.parse_diagnostic(
                    {
                        "active_car": "Toyota Crown GS131 1G-GZE",
                        "symptom": "airflow meter setup",
                        "query": "airflow meter setup",
                        "evidence_context": "previous stage",
                        "mode": "normal",
                        "language": "en",
                    }
                )
            )

        self.assertEqual(
            set(result.keys()),
            {
                "forums_found", "links", "extracted_cases", "parser_summary", "topics_found",
                "common_causes", "solutions", "unlikely_causes", "regional_insights",
                "recommendation", "need_more_info", "clarifying_question", "sufficient_evidence", "_raw",
            },
        )
        self.assertEqual(result["parser_summary"], "contract ok")
        self.assertEqual(result["links"][0]["url"], "https://example.com/thread")

    def test_sufficient_evidence_contract_is_explicit_and_preserved(self):
        payload = _parser_payload("contract ok")
        payload["sufficient_evidence"] = True
        with patch.object(parser_service, "diagnose", new=AsyncMock(return_value=payload)):
            result = asyncio.run(parser_service.parse_diagnostic({"query": "gearbox hot"}))

        self.assertTrue(result["sufficient_evidence"])
        self.assertIn('"sufficient_evidence"', parser_engine.SYSTEM_PROMPT)

    def test_remote_parser_payload_uses_evidence_context_not_chat_history(self):
        captured = {}

        async def fake_remote(data, url):
            captured.update(data.model_dump())
            return _parser_payload("remote ok")

        with (
            patch.object(parser_engine, "_remote_parser_url", return_value="https://remote.example/search"),
            patch.object(parser_engine, "_call_remote_parser", new=fake_remote),
            patch.object(parser_engine, "run_search_provider") as provider_call,
        ):
            result = asyncio.run(parser_engine.diagnose(_request()))

        self.assertEqual(result["summary"], "remote ok")
        self.assertIn("evidence_context", captured)
        self.assertNotIn("conversation" + "_history", captured)
        provider_call.assert_not_called()

    def test_partial_remote_evidence_does_not_trigger_second_provider_call(self):
        partial = _parser_payload("")
        partial["error"] = "remote response was incomplete"

        with (
            patch.object(parser_engine, "_remote_parser_url", return_value="https://remote.example/search"),
            patch.object(parser_engine, "_call_remote_parser", new=AsyncMock(return_value=partial)),
            patch.object(parser_engine, "run_search_provider") as provider_call,
        ):
            result = asyncio.run(parser_engine.diagnose(_request()))

        self.assertNotIn("error", result)
        self.assertTrue(result["_meta"]["partial_result_recovered"])
        provider_call.assert_not_called()

    def test_unusable_remote_result_falls_back_once(self):
        local_result = _parser_payload("local fallback")
        with (
            patch.object(parser_engine, "_remote_parser_url", return_value="https://remote.example/search"),
            patch.object(parser_engine, "_call_remote_parser", new=AsyncMock(return_value={})),
            patch.object(parser_engine, "run_search_provider", return_value=local_result) as provider_call,
        ):
            result = asyncio.run(parser_engine.diagnose(_request()))

        self.assertEqual(result["summary"], "local fallback")
        provider_call.assert_called_once()

    def test_ordinary_and_deep_provider_limits_are_bounded(self):
        client = SimpleNamespace(messages=SimpleNamespace(create=Mock(return_value=SimpleNamespace(content=[]))))
        search_provider.run_claude_search(client, _request("normal"), "message", ["example.com"], system_prompt="prompt")
        normal = client.messages.create.call_args.kwargs
        search_provider.run_claude_search(client, _request("deep"), "message", ["example.com"], system_prompt="prompt")
        deep = client.messages.create.call_args.kwargs

        self.assertEqual(normal["max_tokens"], 1400)
        self.assertEqual(normal["tools"][0]["max_uses"], 2)
        self.assertEqual(deep["max_tokens"], 2500)
        self.assertEqual(deep["tools"][0]["max_uses"], 4)

    def test_video_and_image_hints_are_intent_driven(self):
        ordinary = parser_engine._build_search_hints(_request())
        video = parser_engine._build_search_hints(
            DiagnosticRequest(query="Покажи видео как заменить соленоид", lang="ru")
        )
        image = parser_engine._build_search_hints(
            DiagnosticRequest(query="Покажи схему расположения соленоида", lang="ru")
        )

        self.assertFalse(any("YouTube" in hint for hint in ordinary))
        self.assertTrue(any("YouTube" in hint for hint in video))
        self.assertTrue(any("visual material" in hint for hint in image))

    def test_stage_source_groups_use_distinct_domain_sets(self):
        groups = {}
        for source_group in ("model_owner", "general_technical", "regional_owner"):
            request = DiagnosticRequest(
                query="hot transmission slip",
                car_info="Peugeot 307",
                source_group=source_group,
            )
            groups[source_group] = set(parser_engine.build_allowed_domains(request))

        self.assertTrue(all(groups.values()))
        self.assertTrue(groups["model_owner"].isdisjoint(groups["general_technical"]))
        self.assertTrue(groups["general_technical"].isdisjoint(groups["regional_owner"]))
        self.assertTrue(groups["model_owner"].isdisjoint(groups["regional_owner"]))

    def test_explicit_media_request_uses_single_local_provider_path(self):
        request = DiagnosticRequest(
            query="Покажи видео как заменить соленоид",
            lang="ru",
        )
        local_result = _parser_payload("Video result")
        with (
            patch.object(parser_engine, "_remote_parser_url", return_value="https://remote.example/search"),
            patch.object(parser_engine, "_call_remote_parser", new=AsyncMock()) as remote_call,
            patch.object(parser_engine, "run_search_provider", return_value=local_result) as provider_call,
        ):
            result = asyncio.run(parser_engine.diagnose(request))

        self.assertEqual(result["summary"], "Video result")
        remote_call.assert_not_called()
        provider_call.assert_called_once()
        self.assertIn("youtube.com", provider_call.call_args.kwargs["allowed_domains"])

    def test_malformed_embedded_json_recovers_literal_summary_and_link(self):
        raw = (
            'Search completed. {"summary":"Hot ATF pressure loss is reported",'
            '"links":[{"url":"https://example.com/forum/thread-42'
        )
        with patch.object(
            parser_service,
            "diagnose",
            new=AsyncMock(return_value={"summary": raw}),
        ):
            result = asyncio.run(parser_service.parse_diagnostic({"query": "gearbox hot"}))

        self.assertEqual(result["parser_summary"], "Hot ATF pressure loss is reported")
        self.assertEqual(result["links"][0]["url"], "https://example.com/forum/thread-42")
        self.assertTrue(result["_raw"]["_malformed_payload_recovered"])


if __name__ == "__main__":
    unittest.main()
