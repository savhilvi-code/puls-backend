import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.chat import router as chat_router
from app.schemas.chat import ChatResponse
from app.schemas.parser import DiagnosticRequest
from app.services import parser_engine, parser_service, search_provider
from app.services.kb_service import find_matching_history_case


def _request(mode: str = "normal") -> DiagnosticRequest:
    return DiagnosticRequest(
        query="Toyota Crown 1G-GZE расходомер настройка",
        lang="ru",
        car_info="Toyota Crown GS131 1G-GZE",
        conversation_history="",
        mode=mode,
    )


def _parser_payload(summary: str = "diagnosis") -> dict:
    return {
        "summary": summary,
        "common_causes": [{"cause": "cause", "frequency": "high", "source_langs": ["ru"]}],
        "solutions": [{"title": "check", "description": "solution", "priority": "high", "cost": "free", "source_langs": ["ru"]}],
        "unlikely_causes": [],
        "regional_insights": {},
        "links": [{"title": "source", "url": "https://example.com/thread", "description": "details", "type": "link"}],
        "topics_found": [],
        "total_topics": 1,
        "confidence": "medium",
        "recommendation": "start here",
        "need_more_info": False,
        "clarifying_question": "",
    }


def _claude_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _openai_response(text: str):
    return SimpleNamespace(output_text=text)


class SearchProviderPhase1Tests(unittest.TestCase):
    def test_claude_provider_calls_claude_implementation(self):
        with (
            patch.dict(os.environ, {"SEARCH_PROVIDER": "claude", "ANTHROPIC_API_KEY": "test", "OPENAI_API_KEY": "test"}, clear=False),
            patch.object(search_provider, "anthropic", SimpleNamespace(Anthropic=lambda api_key: object())),
            patch.object(search_provider, "run_claude_search", return_value=_claude_response('{"summary":"claude ok"}')) as claude_call,
            patch.object(search_provider, "run_openai_search") as openai_call,
        ):
            result = search_provider.run_search_provider(
                data=_request(),
                user_message="message",
                allowed_domains=["drive2.ru"],
                fallback_domains=["drom.ru"],
                system_prompt="prompt",
                search_hints=[],
                extract_json=parser_engine.extract_json,
                result_matches_request=lambda result, data: True,
            )

        self.assertEqual(result["summary"], "claude ok")
        claude_call.assert_called_once()
        openai_call.assert_not_called()

    def test_openai_provider_calls_openai_implementation(self):
        with (
            patch.dict(os.environ, {"SEARCH_PROVIDER": "openai", "OPENAI_API_KEY": "test", "ANTHROPIC_API_KEY": "test"}, clear=False),
            patch.object(search_provider, "OpenAI", return_value=object()),
            patch.object(search_provider, "run_openai_search", return_value=_openai_response('{"summary":"openai ok"}')) as openai_call,
            patch.object(search_provider, "run_claude_search") as claude_call,
        ):
            result = search_provider.run_search_provider(
                data=_request(),
                user_message="message",
                allowed_domains=["drive2.ru"],
                fallback_domains=["drom.ru"],
                system_prompt="prompt",
                search_hints=[],
                extract_json=parser_engine.extract_json,
                result_matches_request=lambda result, data: True,
            )

        self.assertEqual(result["summary"], "openai ok")
        openai_call.assert_called_once()
        claude_call.assert_not_called()

    def test_claude_failure_does_not_call_openai(self):
        with (
            patch.dict(os.environ, {"SEARCH_PROVIDER": "claude", "ANTHROPIC_API_KEY": "test", "OPENAI_API_KEY": "test"}, clear=False),
            patch.object(search_provider, "anthropic", SimpleNamespace(Anthropic=lambda api_key: object())),
            patch.object(search_provider, "run_claude_search", side_effect=RuntimeError("claude down")),
            patch.object(search_provider, "run_openai_search") as openai_call,
        ):
            result = search_provider.run_search_provider(
                data=_request(),
                user_message="message",
                allowed_domains=["drive2.ru"],
                fallback_domains=["drom.ru"],
                system_prompt="prompt",
                search_hints=[],
                extract_json=parser_engine.extract_json,
                result_matches_request=lambda result, data: True,
            )

        self.assertIn("claude down", result["error"])
        openai_call.assert_not_called()

    def test_openai_failure_does_not_call_claude(self):
        with (
            patch.dict(os.environ, {"SEARCH_PROVIDER": "openai", "OPENAI_API_KEY": "test", "ANTHROPIC_API_KEY": "test"}, clear=False),
            patch.object(search_provider, "OpenAI", return_value=object()),
            patch.object(search_provider, "run_openai_search", side_effect=RuntimeError("openai down")),
            patch.object(search_provider, "run_claude_search") as claude_call,
        ):
            result = search_provider.run_search_provider(
                data=_request(),
                user_message="message",
                allowed_domains=["drive2.ru"],
                fallback_domains=["drom.ru"],
                system_prompt="prompt",
                search_hints=[],
                extract_json=parser_engine.extract_json,
                result_matches_request=lambda result, data: True,
            )

        self.assertIn("openai down", result["error"])
        claude_call.assert_not_called()

    def test_remote_parser_success_skips_local_search_provider(self):
        with (
            patch.object(parser_engine, "_remote_parser_url", return_value="https://remote.example/search"),
            patch.object(parser_engine, "_call_remote_parser", new=AsyncMock(return_value=_parser_payload("remote ok"))),
            patch.object(parser_engine, "run_search_provider") as provider_call,
        ):
            result = asyncio.run(parser_engine.diagnose(_request()))

        self.assertEqual(result["summary"], "remote ok")
        self.assertEqual(result["_meta"]["engine"], "remote parser api")
        provider_call.assert_not_called()

    def test_remote_parser_failure_uses_selected_local_provider(self):
        with (
            patch.object(parser_engine, "_remote_parser_url", return_value="https://remote.example/search"),
            patch.object(parser_engine, "_call_remote_parser", new=AsyncMock(side_effect=RuntimeError("remote down"))),
            patch.object(parser_engine, "_legacy_1g_gze_airflow_result", return_value=None),
            patch.object(parser_engine.logger, "exception"),
            patch.object(parser_engine, "run_search_provider", return_value=_parser_payload("local ok")) as provider_call,
        ):
            result = asyncio.run(parser_engine.diagnose(_request()))

        self.assertEqual(result["summary"], "local ok")
        provider_call.assert_called_once()

    def test_normal_parser_response_contract_is_preserved(self):
        with patch.object(parser_service, "diagnose", new=AsyncMock(return_value=_parser_payload("contract ok"))):
            result = asyncio.run(
                parser_service.parse_diagnostic(
                    {
                        "active_car": "Toyota Crown GS131 1G-GZE",
                        "symptom": "не заводится",
                        "query": "не заводится",
                        "conversation_history": "",
                        "deep_search": False,
                        "language": "ru",
                    }
                )
            )

        self.assertEqual(
            set(result.keys()),
            {"forums_found", "links", "extracted_cases", "parser_summary", "topics_found", "_raw"},
        )
        self.assertEqual(result["parser_summary"], "contract ok")
        self.assertEqual(result["links"][0]["url"], "https://example.com/thread")

    def test_chat_route_contract_is_still_connected(self):
        async def fake_process(payload, source):
            return ChatResponse(answer=f"{source}: ok", links=[], quota={"remaining": 1})

        test_app = FastAPI()
        test_app.include_router(chat_router)
        with patch("app.routers.chat.process_chat_message", new=fake_process):
            response = TestClient(test_app).post("/chat", json={"message": "hello", "language": "en"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "web: ok")
        self.assertEqual(response.json()["quota"]["remaining"], 1)

    def test_deep_mode_uses_selected_provider_without_cross_vendor_fallback(self):
        with (
            patch.dict(os.environ, {"SEARCH_PROVIDER": "claude", "ANTHROPIC_API_KEY": "test", "OPENAI_API_KEY": "test"}, clear=False),
            patch.object(search_provider, "anthropic", SimpleNamespace(Anthropic=lambda api_key: object())),
            patch.object(search_provider, "run_claude_search", return_value=_claude_response('{"summary":"deep ok"}')) as claude_call,
            patch.object(search_provider, "run_openai_search") as openai_call,
        ):
            result = search_provider.run_search_provider(
                data=_request(mode="deep"),
                user_message="message",
                allowed_domains=["drive2.ru"],
                fallback_domains=["drom.ru"],
                system_prompt="prompt",
                search_hints=[],
                extract_json=parser_engine.extract_json,
                result_matches_request=lambda result, data: True,
            )

        self.assertEqual(result["summary"], "deep ok")
        self.assertEqual(claude_call.call_args.args[1].mode, "deep")
        openai_call.assert_not_called()

    def test_history_match_preserves_user_language_answer(self):
        history = (
            "source: web\n"
            "message_type: parser\n"
            "active_car: Toyota Crown GS131 1G-GZE\n"
            "symptom: расходомер настройка\n"
            "user: расходомер настройка\n"
            "assistant: Оригинальный русский ответ пользователя"
        )

        result = asyncio.run(
            find_matching_history_case(
                history=history,
                active_car="Toyota Crown GS131 1G-GZE",
                symptom="расходомер настройка",
                language="ru",
            )
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["answer"], "Оригинальный русский ответ пользователя")


if __name__ == "__main__":
    unittest.main()
