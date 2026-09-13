import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.chat import router as chat_router
from app.schemas.chat import ChatResponse
from app.services import decision_engine, diagnostic_context_service, diagnostic_provider


def _provider_result() -> dict:
    return {
        "most_likely": "A leaking intake hose after the airflow meter is the most likely fault.",
        "why": "Known facts: the symptom is power loss. Evidence-supported inference: unmetered air can lean the mixture.",
        "first_checks": ["Inspect intake hoses after the airflow meter.", "Smoke test the intake tract."],
        "less_likely": ["ECU failure without other symptoms."],
        "what_would_change_diagnosis": ["Fuel pressure data", "Stored DTC codes"],
        "short_conclusion": "Start with intake leak checks before replacing sensors.",
        "confidence": "medium",
        "sources": [{"title": "Forum case", "url": "https://example.com/thread", "description": "Similar symptom", "type": "link"}],
    }


class _FakeResponses:
    def __init__(self, payload: dict):
        self.payload = payload
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(output_text=json.dumps(self.payload))


class _FakeOpenAI:
    responses_instance = None

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.responses = _FakeResponses(_provider_result())
        _FakeOpenAI.responses_instance = self.responses


class DiagnosticProviderPhase2Tests(unittest.TestCase):
    def test_diagnostic_provider_none_keeps_old_formatter_path_available(self):
        with patch.dict(os.environ, {"DIAGNOSTIC_PROVIDER": "none"}, clear=False):
            result = diagnostic_provider.run_diagnostic_provider({"canonical_output_language": "en"})

        self.assertIsNone(result)

    def test_openai_diagnostic_provider_uses_configured_model_without_search_tools(self):
        with (
            patch.dict(
                os.environ,
                {
                    "DIAGNOSTIC_PROVIDER": "openai",
                    "OPENAI_API_KEY": "test",
                    "OPENAI_DIAGNOSTIC_MODEL": "configured-diagnostic-model",
                },
                clear=False,
            ),
            patch.object(diagnostic_provider, "OpenAI", _FakeOpenAI),
        ):
            result = diagnostic_provider.run_diagnostic_provider({"canonical_output_language": "en", "parser_result": {}})

        self.assertEqual(result["short_conclusion"], "Start with intake leak checks before replacing sensors.")
        kwargs = _FakeOpenAI.responses_instance.kwargs
        self.assertEqual(kwargs["model"], "configured-diagnostic-model")
        self.assertNotIn("tools", kwargs)
        self.assertNotIn("web_search", json.dumps(kwargs))

    def test_provider_failure_returns_none_for_formatter_fallback(self):
        with (
            patch.dict(
                os.environ,
                {
                    "DIAGNOSTIC_PROVIDER": "openai",
                    "OPENAI_API_KEY": "test",
                    "OPENAI_DIAGNOSTIC_MODEL": "configured-diagnostic-model",
                },
                clear=False,
            ),
            patch.object(diagnostic_provider, "OpenAI", side_effect=RuntimeError("provider down")),
        ):
            result = diagnostic_provider.run_diagnostic_provider({"canonical_output_language": "en"})

        self.assertIsNone(result)

    def test_malformed_provider_result_returns_none_for_formatter_fallback(self):
        result = diagnostic_provider.normalize_diagnostic_result({"confidence": "high", "sources": []})

        self.assertIsNone(result)

    def test_decision_engine_provider_failure_returns_none_for_existing_fallback_flow(self):
        with patch.object(decision_engine, "run_diagnostic_provider", side_effect=RuntimeError("provider down")):
            result = asyncio.run(
                decision_engine._try_diagnostic_provider_answer(
                    context={"canonical_output_language": "en"},
                    language="ru",
                    fallback_links=[],
                    question_tail="tail",
                )
            )

        self.assertIsNone(result)

    def test_provider_english_result_is_localized_to_user_language_before_response(self):
        captured_context = {}

        def fake_provider(context):
            captured_context.update(context)
            return _provider_result()

        async def fake_localize(*, segments, target_language):
            self.assertEqual(target_language, "ru")
            if segments and segments[0] in {"Forum case", "Similar symptom"}:
                return list(segments)
            self.assertIn("Start with intake leak checks before replacing sensors.", segments[0])
            return [
                "Сначала проверьте подсос воздуха во впуске.",
                "Подсос воздуха после расходомера наиболее вероятен.",
                "Известные факты: есть потеря тяги. Вывод: неучтенный воздух обедняет смесь.",
                "Осмотрите патрубки после расходомера.",
                "Сделайте дым-тест впуска.",
                "Что изменит диагноз: данные давления топлива; сохраненные DTC коды",
                "Отказ ЭБУ без других симптомов.",
            ]

        with (
            patch.object(decision_engine, "run_diagnostic_provider", side_effect=fake_provider),
            patch.object(decision_engine, "translate_segments", new=fake_localize),
        ):
            result = asyncio.run(
                decision_engine._try_diagnostic_provider_answer(
                    context={"canonical_output_language": "en", "parser_result": {"summary": "raw"}},
                    language="ru",
                    fallback_links=[],
                    question_tail="Это помогло?",
                )
            )

        self.assertIsNotNone(result)
        answer_text, links = result
        self.assertEqual(captured_context["canonical_output_language"], "en")
        self.assertIn("Короткий диагноз", answer_text)
        self.assertIn("Сначала проверьте подсос воздуха во впуске.", answer_text)
        self.assertEqual(links[0]["url"], "https://example.com/thread")

    def test_diagnostic_context_uses_only_available_decision_engine_data(self):
        state = SimpleNamespace(language="ru", active_car="Toyota Crown GS131 1G-GZE", should_deep_search=False)
        normalized = SimpleNamespace(language="ru", car_info="", text="расходомер")
        user = SimpleNamespace(car_info="", conversation_history="previous user-language history")

        context = diagnostic_context_service.build_diagnostic_context(
            state=state,
            normalized=normalized,
            user=user,
            resolved_vehicle={"id": 7, "brand": "Toyota", "model": "Crown", "year": 1990, "engine": "1G-GZE"},
            latest_context={"last_user_text": "old", "last_assistant_text": "old answer"},
            effective_symptom="расходомер",
            parser_query="расходомер",
            parser_history="focused history",
            parsed_case={"parser_summary": "summary"},
            diagnosis_text="summary",
            probable_causes=["cause"],
            first_checks=["check"],
            less_likely=["less"],
            response_links=[{"title": "source", "url": "https://example.com/thread"}],
        )

        self.assertEqual(context["canonical_output_language"], "en")
        self.assertEqual(context["user_language"], "ru")
        self.assertEqual(context["vehicle"]["engine"], "1G-GZE")
        self.assertFalse(context["service_logs"]["available_in_current_flow"])
        self.assertFalse(context["dtc"]["available_in_current_flow"])

    def test_diagnostic_context_can_include_internal_knowledge_without_parser_result(self):
        state = SimpleNamespace(language="en", active_car="Nissan X-Trail GT", should_deep_search=False)
        normalized = SimpleNamespace(language="en", car_info="", text="loss of power")
        user = SimpleNamespace(car_info="", conversation_history="personal history")

        context = diagnostic_context_service.build_diagnostic_context(
            state=state,
            normalized=normalized,
            user=user,
            resolved_vehicle={"id": 3, "brand": "Nissan", "model": "X-Trail", "year": 2003, "engine": "SR20VET"},
            latest_context={"last_user_text": "loss of power"},
            effective_symptom="loss of power",
            diagnosis_text="Known solved case answer",
            response_links=[{"title": "case", "url": "https://example.com/case"}],
            internal_match={
                "id": 11,
                "source_type": "history",
                "answer": "Known solved case answer",
                "links": [{"title": "case", "url": "https://example.com/case"}],
                "row": {"message_type": "parser"},
            },
            internal_match_kind="history",
        )

        self.assertTrue(context["internal_knowledge"]["available"])
        self.assertEqual(context["history_match"]["case_id"], 11)
        self.assertIsNone(context["kb_match"])
        self.assertIsNone(context["parser_result"])
        self.assertEqual(context["aggregated_evidence"]["internal_summary"], "Known solved case answer")

    def test_chat_response_contract_is_unchanged(self):
        async def fake_process(payload, source):
            return ChatResponse(answer="ok", links=[], quota={"remaining": 2})

        test_app = FastAPI()
        test_app.include_router(chat_router)
        with patch("app.routers.chat.process_chat_message", new=fake_process):
            response = TestClient(test_app).post("/chat", json={"message": "hello", "language": "en"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json().keys()), {"answer", "links", "quota"})
        self.assertEqual(response.json()["answer"], "ok")


if __name__ == "__main__":
    unittest.main()
