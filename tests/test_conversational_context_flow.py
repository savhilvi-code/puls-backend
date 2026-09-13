import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.schemas.router import RouterDecision
from app.services import decision_engine


def _user(history: str = "", car_info: str = ""):
    return SimpleNamespace(id=1, car_info=car_info, conversation_history=history, requests_left=10)


def _state(**overrides):
    values = {
        "language": "en",
        "active_car": "Context Car 2.0",
        "should_search": True,
        "should_deep_search": False,
        "current_symptom": "engine stalls",
        "previous_symptom": "",
        "is_greeting": False,
        "is_feedback_helped": False,
        "is_feedback_not_helped": False,
        "needs_car_clarification": False,
        "needs_problem_clarification": False,
        "active_service_flow": False,
        "service_target": "",
        "service_subtype": "",
        "message_type": "new_diagnostic",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _decision(**overrides):
    values = {
        "message_type": "new_diagnostic",
        "language": "en",
        "need_car_info": False,
        "need_clarification": False,
        "ready_to_search": True,
        "deep_search": False,
        "user_says_helped": False,
        "user_says_not_helped": False,
        "question": "",
        "car_info": "",
        "active_car": "",
        "symptom": "engine stalls",
        "response": "",
    }
    values.update(overrides)
    return RouterDecision(**values)


def _latest_context(**overrides):
    values = {
        "conversation_id": "11",
        "active_car": "Context Car 2.0",
        "last_user_text": "Context Car 2.0 engine stalls",
        "last_assistant_text": "",
        "latest_service_query": "",
        "recent_messages": [],
    }
    values.update(overrides)
    return values


def _parser_case(summary: str = "Stored diagnostic answer"):
    return {
        "forums_found": ["forum"],
        "links": [{"title": "Forum case", "url": "https://example.com/case", "description": "", "type": "link"}],
        "extracted_cases": [{"cause": "likely cause", "solution": "first check"}],
        "parser_summary": summary,
        "topics_found": [],
        "_raw": {},
    }


class ConversationalContextFlowTests(unittest.TestCase):
    def _run_chat(
        self,
        *,
        message: str,
        state=None,
        user=None,
        decision=None,
        latest_context=None,
        kb_match=None,
        parser_case=None,
        resolved_vehicle=None,
    ):
        captured = {}
        parser = AsyncMock(return_value=parser_case or _parser_case())
        kb = AsyncMock(return_value=kb_match)

        async def fake_update(*args, **kwargs):
            captured["update"] = kwargs

        async def fake_translate(*, segments, target_language):
            return list(segments)

        with (
            patch.object(decision_engine, "get_or_create_user", new=AsyncMock(return_value=user or _user())),
            patch.object(decision_engine, "resolve_user_vehicle", return_value=resolved_vehicle),
            patch.object(decision_engine, "route_message", new=AsyncMock(return_value=decision or _decision())),
            patch.object(decision_engine, "build_dialog_state", return_value=state or _state()),
            patch.object(decision_engine, "get_latest_conversation_context", return_value=latest_context or _latest_context()),
            patch.object(decision_engine, "_looks_like_service_advice_query", return_value=False),
            patch.object(decision_engine, "find_matching_case", new=kb),
            patch.object(decision_engine, "find_matching_history_case", new=AsyncMock(return_value=None)),
            patch.object(decision_engine, "can_run_parser", return_value=(True, {"requests_remaining": 5})),
            patch.object(decision_engine, "parse_diagnostic", new=parser),
            patch.object(decision_engine, "run_diagnostic_provider", return_value=None),
            patch.object(decision_engine, "translate_segments", new=fake_translate),
            patch.object(decision_engine, "update_user_after_response", new=fake_update),
            patch.object(decision_engine, "ensure_user_subscription"),
        ):
            response = asyncio.run(
                decision_engine.process_chat_message(
                    {"message": message, "language": "en"},
                    source="web",
                )
            )
        return response, captured, kb, parser

    def test_incomplete_initial_request_asks_clarification_without_parser(self):
        response, captured, kb, parser = self._run_chat(
            message="Context Car 2.0 stalls",
            latest_context=_latest_context(last_user_text="", active_car=""),
        )

        self.assertIn("single most useful condition", response.answer)
        self.assertFalse(parser.called)
        self.assertFalse(kb.called)
        self.assertEqual(captured["update"]["message_type"], "clarification")

    def test_short_clarification_preserves_vehicle_and_topic(self):
        latest = _latest_context(
            last_user_text="Context Car 2.0 engine stalls",
            last_assistant_text="What is the single most useful condition?",
            recent_messages=[
                {"role": "user", "text": "Context Car 2.0 engine stalls"},
                {"role": "assistant", "text": "What is the single most useful condition?"},
            ],
        )
        response, captured, kb, parser = self._run_chat(
            message="only when cold",
            state=_state(active_car="", current_symptom="only when cold", should_search=False),
            user=_user(car_info="Old History Car 1.0"),
            latest_context=latest,
        )

        self.assertTrue(parser.called)
        parser_payload = parser.call_args.args[0]
        self.assertEqual(parser_payload["active_car"], "Context Car 2.0")
        self.assertIn("Context Car 2.0 engine stalls", parser_payload["symptom"])
        self.assertEqual(captured["update"]["vehicle_id"], None)
        self.assertEqual(captured["update"]["message_type"], "parser")
        self.assertIn("Stored diagnostic answer", response.answer)

    def test_detailed_first_message_skips_unnecessary_clarification(self):
        response, captured, kb, parser = self._run_chat(
            message="Context Car 2.0 stalls when cold at idle after spark plug replacement, no DTC",
            state=_state(current_symptom="Context Car 2.0 stalls when cold at idle after spark plug replacement, no DTC"),
            latest_context=_latest_context(last_user_text="", active_car=""),
        )

        self.assertTrue(parser.called)
        self.assertEqual(captured["update"]["message_type"], "parser")
        self.assertIn("Stored diagnostic answer", response.answer)

    def test_dont_know_proceeds_after_clarification_without_looping(self):
        latest = _latest_context(
            last_user_text="Context Car 2.0 engine stalls",
            last_assistant_text="Are there any DTC/warning lights?",
            recent_messages=[
                {"role": "user", "text": "Context Car 2.0 engine stalls"},
                {"role": "assistant", "text": "What is the single most useful condition?"},
                {"role": "user", "text": "cold"},
                {"role": "assistant", "text": "Are there any DTC/warning lights?"},
            ],
        )
        response, captured, kb, parser = self._run_chat(
            message="I do not know",
            state=_state(active_car="", current_symptom="I do not know", should_search=False),
            latest_context=latest,
        )

        self.assertTrue(parser.called)
        self.assertEqual(captured["update"]["message_type"], "parser")
        self.assertNotIn("Are there any", response.answer)

    def test_internal_knowledge_is_checked_before_parser_and_can_stop_parser(self):
        kb_match = {
            "id": 7,
            "answer": "Internal PULS answer",
            "links": [{"title": "Stored source", "url": "https://example.com/internal", "description": "", "type": "link"}],
            "row": {"source_table": "knowledge_cases"},
        }
        response, captured, kb, parser = self._run_chat(
            message="Context Car 2.0 stalls when hot under load with P0171",
            state=_state(current_symptom="Context Car 2.0 stalls when hot under load with P0171"),
            kb_match=kb_match,
        )

        self.assertTrue(kb.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["message_type"], "kb_match")
        self.assertIn("Internal PULS answer", response.answer)

    def test_parser_runs_when_internal_knowledge_is_insufficient(self):
        response, captured, kb, parser = self._run_chat(
            message="Context Car 2.0 stalls when hot under load with P0171",
            state=_state(current_symptom="Context Car 2.0 stalls when hot under load with P0171"),
            kb_match=None,
        )

        self.assertTrue(kb.called)
        self.assertTrue(parser.called)
        self.assertEqual(captured["update"]["message_type"], "parser")
        self.assertIn("Stored diagnostic answer", response.answer)

    def test_negative_feedback_preserves_current_case_and_existing_evidence_for_deeper_search(self):
        history = (
            "source: web\n"
            "message_type: parser\n"
            "active_car: Context Car 2.0\n"
            "symptom: Context Car 2.0 engine stalls when hot\n"
            "user: Context Car 2.0 engine stalls when hot\n"
            "assistant: Previous answer\n"
            "links:\n"
            "- Forum case: https://example.com/case"
        )
        response, captured, kb, parser = self._run_chat(
            message="not helped",
            state=_state(
                active_car="",
                current_symptom="not helped",
                should_search=True,
                should_deep_search=True,
                is_feedback_not_helped=True,
            ),
            user=_user(history=history, car_info="Old History Car 1.0"),
            latest_context=_latest_context(
                active_car="Context Car 2.0",
                last_user_text="Context Car 2.0 engine stalls when hot",
                last_assistant_text="Previous answer",
            ),
        )

        self.assertTrue(parser.called)
        parser_payload = parser.call_args.args[0]
        self.assertTrue(parser_payload["deep_search"])
        self.assertEqual(parser_payload["active_car"], "Context Car 2.0")
        self.assertIn("Context Car 2.0 engine stalls when hot", parser_payload["symptom"])
        self.assertIn("Previous answer", parser_payload["conversation_history"])
        self.assertEqual(captured["update"]["message_type"], "parser")
        self.assertIn("Stored diagnostic answer", response.answer)

    def test_where_from_uses_stored_evidence_without_search(self):
        history = (
            "source: web\n"
            "message_type: parser\n"
            "active_car: Context Car 2.0\n"
            "symptom: Context Car 2.0 engine stalls\n"
            "user: Context Car 2.0 engine stalls\n"
            "assistant: Previous evidence-based answer\n"
            "links:\n"
            "- Forum case: https://example.com/case"
        )
        response, captured, kb, parser = self._run_chat(
            message="where did this information come from?",
            state=_state(should_search=False, current_symptom="where did this information come from?"),
            user=_user(history=history),
        )

        self.assertFalse(kb.called)
        self.assertFalse(parser.called)
        self.assertIn("current stored case", response.answer)
        self.assertEqual([item.url for item in response.links], ["https://example.com/case"])
        self.assertEqual(captured["update"]["message_type"], "general")

    def test_explicit_vehicle_switch_uses_new_vehicle(self):
        new_vehicle = {"id": 22, "brand": "Switch", "model": "Car", "year": 2020, "engine": "2.0"}
        response, captured, kb, parser = self._run_chat(
            message="Switch Car 2020 2.0 stalls when hot under load with P0171",
            state=_state(
                active_car="Switch Car 2020 2.0",
                current_symptom="Switch Car 2020 2.0 stalls when hot under load with P0171",
            ),
            user=_user(car_info="Old History Car 1.0"),
            latest_context=_latest_context(active_car="Old History Car 1.0"),
            resolved_vehicle=new_vehicle,
        )

        self.assertTrue(parser.called)
        self.assertEqual(parser.call_args.args[0]["active_car"], "Switch Car 2020 2.0")
        self.assertEqual(captured["update"]["vehicle_id"], 22)
        self.assertIn("Stored diagnostic answer", response.answer)


if __name__ == "__main__":
    unittest.main()
