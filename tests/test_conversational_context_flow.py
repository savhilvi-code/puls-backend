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

        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["active_car"], "Context Car 2.0")
        self.assertIn("Context Car 2.0 engine stalls", captured["update"]["symptom"])
        self.assertEqual(captured["update"]["vehicle_id"], None)
        self.assertEqual(captured["update"]["message_type"], "clarification")
        self.assertIn("Context Car 2.0", response.answer)

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


class RealContextPrecedenceTests(unittest.TestCase):
    def _vehicle_resolver(self, *, user_id=None, car_text=""):
        text = str(car_text or "").lower()
        if "toyota" in text:
            return {"id": 10, "brand": "Toyota", "model": "Corolla", "year": 2010, "engine": "1ZZ"}
        if "nissan" in text or "x-trail" in text or "xtrail" in text:
            return {"id": 20, "brand": "Nissan", "model": "X-Trail", "year": 2003, "engine": "SR20VET"}
        return None

    def _run_real_state_chat(
        self,
        *,
        message,
        latest_context,
        user=None,
        decision=None,
        kb_match=None,
        history_match=None,
        parser_case=None,
    ):
        captured = {}
        parser = AsyncMock(return_value=parser_case or _parser_case())
        kb = AsyncMock(return_value=kb_match)
        history = AsyncMock(return_value=history_match)

        async def fake_update(*args, **kwargs):
            captured["update"] = kwargs

        async def fake_translate(*, segments, target_language):
            return list(segments)

        with (
            patch.object(decision_engine, "get_or_create_user", new=AsyncMock(return_value=user or _user())),
            patch.object(decision_engine, "resolve_user_vehicle", side_effect=self._vehicle_resolver),
            patch.object(decision_engine, "route_message", new=AsyncMock(return_value=decision or _decision(language="ru"))),
            patch.object(decision_engine, "get_latest_conversation_context", return_value=latest_context),
            patch.object(decision_engine, "find_matching_case", new=kb),
            patch.object(decision_engine, "find_matching_history_case", new=history),
            patch.object(decision_engine, "can_run_parser", return_value=(True, {"requests_remaining": 5})),
            patch.object(decision_engine, "parse_diagnostic", new=parser),
            patch.object(decision_engine, "run_diagnostic_provider", return_value=None),
            patch.object(decision_engine, "translate_segments", new=fake_translate),
            patch.object(decision_engine, "update_user_after_response", new=fake_update),
            patch.object(decision_engine, "ensure_user_subscription"),
        ):
            response = asyncio.run(
                decision_engine.process_chat_message(
                    {"message": message, "language": (decision or _decision(language="ru")).language},
                    source="web",
                )
            )
        return response, captured, kb, history, parser

    def test_recent_conversation_vehicle_beats_old_history_for_short_reply(self):
        old_history = (
            "source: web\n"
            "message_type: parser\n"
            "active_car: Nissan X-Trail 2003 SR20VET\n"
            "symptom: Nissan old problem\n"
            "user: Nissan old problem\n"
            "assistant: old answer"
        )
        latest = _latest_context(
            active_car="Toyota Corolla 2010 1ZZ",
            last_user_text="Toyota Corolla 2010 1ZZ vibrates",
            last_assistant_text="What is the single most useful condition?",
            recent_messages=[
                {"role": "user", "text": "Toyota Corolla 2010 1ZZ vibrates"},
                {"role": "assistant", "text": "What is the single most useful condition?"},
            ],
        )

        response, captured, kb, history, parser = self._run_real_state_chat(
            message="на холодную",
            user=_user(history=old_history, car_info="Nissan X-Trail 2003 SR20VET"),
            latest_context=latest,
            decision=_decision(language="ru", ready_to_search=False, symptom="на холодную"),
        )

        self.assertEqual(captured["update"]["active_car"], "Toyota Corolla 2010 1ZZ")
        self.assertEqual(captured["update"]["vehicle_id"], 10)
        self.assertFalse(parser.called)
        self.assertIn("Toyota Corolla 2010 1ZZ", response.answer)

    def test_explicit_current_vehicle_switch_beats_recent_conversation(self):
        latest = _latest_context(
            active_car="Toyota Corolla 2010 1ZZ",
            last_user_text="Toyota Corolla 2010 1ZZ vibrates",
            last_assistant_text="What is the single most useful condition?",
            recent_messages=[
                {"role": "user", "text": "Toyota Corolla 2010 1ZZ vibrates"},
                {"role": "assistant", "text": "What is the single most useful condition?"},
            ],
        )

        response, captured, kb, history, parser = self._run_real_state_chat(
            message="теперь Nissan X-Trail 2003 SR20VET на холодную",
            user=_user(car_info="Toyota Corolla 2010 1ZZ"),
            latest_context=latest,
            decision=_decision(language="ru", ready_to_search=False, symptom="на холодную"),
        )

        self.assertEqual(captured["update"]["active_car"], "Nissan X-Trail 2003 SR20VET")
        self.assertEqual(captured["update"]["vehicle_id"], 20)
        self.assertTrue(parser.called)
        self.assertEqual(parser.call_args.args[0]["active_car"], "Nissan X-Trail 2003 SR20VET")

    def test_clarification_turns_suppress_parser_until_context_is_sufficient_then_check_kb(self):
        toyota = "Toyota Corolla 2010 1ZZ"
        decision = _decision(language="en", ready_to_search=True, symptom="vibration")

        first = self._run_real_state_chat(
            message=f"{toyota} vibrates",
            latest_context=_latest_context(active_car="", last_user_text="", last_assistant_text="", recent_messages=[]),
            decision=decision,
        )
        self.assertFalse(first[4].called)
        self.assertFalse(first[2].called)
        self.assertEqual(first[1]["update"]["message_type"], "clarification")

        second_latest = _latest_context(
            active_car=toyota,
            last_user_text=f"{toyota} vibrates",
            last_assistant_text="What is the single most useful condition?",
            recent_messages=[
                {"role": "user", "text": f"{toyota} vibrates"},
                {"role": "assistant", "text": "What is the single most useful condition?"},
            ],
        )
        second = self._run_real_state_chat(
            message="only under acceleration",
            latest_context=second_latest,
            decision=decision,
        )
        self.assertFalse(second[4].called)
        self.assertFalse(second[2].called)
        self.assertEqual(second[1]["update"]["active_car"], toyota)

        kb_match = {
            "id": 33,
            "answer": "Internal vibration case",
            "links": [],
            "row": {"source_table": "knowledge_cases"},
        }
        third_latest = _latest_context(
            active_car=toyota,
            last_user_text="only under acceleration",
            last_assistant_text="Are there any DTC/warning lights, or did anything get repaired or replaced before it started?",
            recent_messages=[
                {"role": "user", "text": f"{toyota} vibrates"},
                {"role": "assistant", "text": "What is the single most useful condition?"},
                {"role": "user", "text": "only under acceleration"},
                {"role": "assistant", "text": "Are there any DTC/warning lights, or did anything get repaired or replaced before it started?"},
            ],
        )
        third = self._run_real_state_chat(
            message="after right axle replacement",
            latest_context=third_latest,
            decision=decision,
            kb_match=kb_match,
        )
        self.assertTrue(third[2].called)
        self.assertFalse(third[4].called)
        self.assertEqual(third[1]["update"]["message_type"], "kb_match")

        fourth = self._run_real_state_chat(
            message="after right axle replacement",
            latest_context=third_latest,
            decision=decision,
            kb_match=None,
        )
        self.assertTrue(fourth[2].called)
        self.assertTrue(fourth[4].called)
        self.assertEqual(fourth[1]["update"]["message_type"], "parser")

    def test_ordinary_followup_can_reuse_history_evidence_without_parser(self):
        toyota = "Toyota Corolla 2010 1ZZ"
        history_text = (
            "source: web\n"
            "message_type: parser\n"
            f"active_car: {toyota}\n"
            "symptom: vibration under acceleration after axle replacement\n"
            "user: vibration under acceleration after axle replacement\n"
            "assistant: Check inner CV joint, axle seating, engine mounts.\n"
            "links:\n"
            "- Stored forum: https://example.com/stored"
        )
        latest = _latest_context(
            active_car=toyota,
            last_user_text="after right axle replacement",
            last_assistant_text="Check inner CV joint, axle seating, engine mounts.",
            recent_messages=[
                {"role": "user", "text": f"{toyota} vibrates"},
                {"role": "assistant", "text": "What is the single most useful condition?"},
                {"role": "user", "text": "only under acceleration"},
                {"role": "assistant", "text": "Are there any DTC/warning lights?"},
                {"role": "user", "text": "after right axle replacement"},
                {"role": "assistant", "text": "Check inner CV joint, axle seating, engine mounts."},
            ],
        )
        history_match = {
            "id": "history",
            "answer": "Check inner CV joint, axle seating, engine mounts.",
            "links": [{"title": "Stored forum", "url": "https://example.com/stored", "description": "", "type": "link"}],
            "row": {"message_type": "parser"},
            "source_type": "history",
        }

        response, captured, kb, history, parser = self._run_real_state_chat(
            message="what should I check first?",
            user=_user(history=history_text),
            latest_context=latest,
            decision=_decision(language="en", ready_to_search=True, symptom="what should I check first?"),
            kb_match=None,
            history_match=history_match,
        )

        self.assertTrue(kb.called)
        self.assertTrue(history.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["message_type"], "kb_match")
        self.assertIn("CV joint", response.answer)


class SocialConversationRoutingTests(unittest.TestCase):
    def _vehicle_resolver(self, *, user_id=None, car_text=""):
        text = str(car_text or "").lower()
        if "toyota" in text:
            return {"id": 10, "brand": "Toyota", "model": "Corolla", "year": 2010, "engine": "1ZZ"}
        if "nissan" in text or "x-trail" in text or "xtrail" in text:
            return {"id": 20, "brand": "Nissan", "model": "X-Trail", "year": 2003, "engine": "SR20VET"}
        return None

    def _run_real_state_chat(
        self,
        *,
        message,
        latest_context,
        user=None,
        decision=None,
        kb_match=None,
        parser_case=None,
    ):
        captured = {}
        parser = AsyncMock(return_value=parser_case or _parser_case())
        kb = AsyncMock(return_value=kb_match)
        history = AsyncMock(return_value=None)
        provider = Mock(return_value=None)
        route = AsyncMock(return_value=decision or _decision(language="ru"))

        async def fake_update(*args, **kwargs):
            captured["update"] = kwargs

        async def fake_translate(*, segments, target_language):
            return list(segments)

        with (
            patch.object(decision_engine, "get_or_create_user", new=AsyncMock(return_value=user or _user())),
            patch.object(decision_engine, "resolve_user_vehicle", side_effect=self._vehicle_resolver),
            patch.object(decision_engine, "route_message", new=route),
            patch.object(decision_engine, "get_latest_conversation_context", return_value=latest_context),
            patch.object(decision_engine, "find_matching_case", new=kb),
            patch.object(decision_engine, "find_matching_history_case", new=history),
            patch.object(decision_engine, "can_run_parser", return_value=(True, {"requests_remaining": 5})),
            patch.object(decision_engine, "parse_diagnostic", new=parser),
            patch.object(decision_engine, "run_diagnostic_provider", new=provider),
            patch.object(decision_engine, "translate_segments", new=fake_translate),
            patch.object(decision_engine, "update_user_after_response", new=fake_update),
            patch.object(decision_engine, "ensure_user_subscription"),
        ):
            response = asyncio.run(
                decision_engine.process_chat_message(
                    {"message": message, "language": (decision or _decision(language="ru")).language},
                    source="web",
                )
            )
        return response, captured, kb, history, parser, provider, route

    def _general_decision(self, response=""):
        return _decision(
            message_type="general",
            language="ru",
            ready_to_search=False,
            deep_search=False,
            symptom="",
            response=response,
        )

    def test_active_case_social_how_are_you_skips_diagnostic_paths_and_preserves_context(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text=f"{nissan} троит на холодную",
            last_assistant_text="Уточните один самый важный момент.",
            recent_messages=[
                {"role": "user", "text": f"{nissan} троит на холодную"},
                {"role": "assistant", "text": "Уточните один самый важный момент."},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_real_state_chat(
            message="как дела",
            latest_context=latest,
            decision=self._general_decision("Нормально, я на связи."),
        )

        self.assertIn("на связи", response.answer)
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertEqual(captured["update"]["active_car"], nissan)
        self.assertEqual(captured["update"]["vehicle_id"], 20)
        self.assertIn(f"{nissan} троит", captured["update"]["symptom"])
        self.assertEqual(route.call_args.args[0].car_info, "")

    def test_after_social_turn_short_automotive_reply_resumes_previous_nissan_case(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text="как дела",
            last_assistant_text="Нормально, я на связи.",
            recent_messages=[
                {"role": "user", "text": f"{nissan} троит на холодную"},
                {"role": "assistant", "text": "После прогрева троение полностью исчезает?"},
                {"role": "user", "text": "как дела"},
                {"role": "assistant", "text": "Нормально, я на связи."},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_real_state_chat(
            message="после прогрева проходит",
            latest_context=latest,
            decision=_decision(language="ru", symptom="после прогрева проходит", ready_to_search=True),
        )

        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["active_car"], nissan)
        self.assertEqual(captured["update"]["vehicle_id"], 20)
        self.assertEqual(captured["update"]["message_type"], "clarification")
        self.assertIn(f"{nissan} троит", captured["update"]["symptom"])
        self.assertNotIn("как дела", captured["update"]["symptom"])
        self.assertIn(nissan, response.answer)
        self.assertEqual(route.call_args.args[0].car_info, "")

    def test_active_case_thanks_is_general_without_parser_or_provider(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text=f"{nissan} троит на холодную",
            last_assistant_text="После прогрева троение полностью исчезает?",
            recent_messages=[
                {"role": "user", "text": f"{nissan} троит на холодную"},
                {"role": "assistant", "text": "После прогрева троение полностью исчезает?"},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_real_state_chat(
            message="спасибо",
            latest_context=latest,
            decision=self._general_decision("Пожалуйста."),
        )

        self.assertIn("Пожалуйста", response.answer)
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertEqual(captured["update"]["active_car"], nissan)

    def test_no_active_case_social_message_does_not_force_vehicle_clarification(self):
        latest = _latest_context(
            active_car="",
            last_user_text="",
            last_assistant_text="",
            recent_messages=[],
        )

        response, captured, kb, history, parser, provider, route = self._run_real_state_chat(
            message="как дела",
            latest_context=latest,
            user=_user(),
            decision=self._general_decision("Нормально, я на связи."),
        )

        self.assertIn("на связи", response.answer)
        self.assertNotIn("Укажите", response.answer)
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertEqual(captured["update"]["active_car"], "")
        self.assertIsNone(captured["update"]["vehicle_id"])

    def test_greeting_does_not_erase_toyota_and_next_short_reply_resumes_case(self):
        toyota = "Toyota Corolla 2010 1ZZ"
        greeting_latest = _latest_context(
            active_car=toyota,
            last_user_text=f"{toyota} троит",
            last_assistant_text="Когда проявляется?",
            recent_messages=[
                {"role": "user", "text": f"{toyota} троит"},
                {"role": "assistant", "text": "Когда проявляется?"},
            ],
        )
        greeting = self._run_real_state_chat(
            message="привет",
            latest_context=greeting_latest,
            decision=self._general_decision("Привет! Я на связи."),
        )
        self.assertFalse(greeting[4].called)
        self.assertEqual(greeting[1]["update"]["active_car"], toyota)
        self.assertEqual(greeting[1]["update"]["vehicle_id"], 10)

        followup_latest = _latest_context(
            active_car=toyota,
            last_user_text="привет",
            last_assistant_text="Привет! Я на связи.",
            recent_messages=[
                {"role": "user", "text": f"{toyota} троит"},
                {"role": "assistant", "text": "Когда проявляется?"},
                {"role": "user", "text": "привет"},
                {"role": "assistant", "text": "Привет! Я на связи."},
            ],
        )
        followup = self._run_real_state_chat(
            message="на холодную",
            latest_context=followup_latest,
            decision=_decision(language="ru", symptom="на холодную", ready_to_search=False),
        )
        self.assertEqual(followup[1]["update"]["active_car"], toyota)
        self.assertEqual(followup[1]["update"]["vehicle_id"], 10)
        self.assertIn(f"{toyota} троит", followup[1]["update"]["symptom"])
        self.assertNotIn("привет", followup[1]["update"]["symptom"])


if __name__ == "__main__":
    unittest.main()
