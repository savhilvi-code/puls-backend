import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.schemas.router import RouterDecision
from app.services import decision_engine


def _user(history: str = "", car_info: str = ""):
    return SimpleNamespace(id=1, car_info=car_info, conversation_history=history, requests_left=10)


def _decision(**overrides):
    values = {
        "message_type": "new_diagnostic",
        "language": "ru",
        "need_car_info": False,
        "need_clarification": False,
        "ready_to_search": True,
        "deep_search": False,
        "user_says_helped": False,
        "user_says_not_helped": False,
        "question": "",
        "car_info": "",
        "active_car": "",
        "symptom": "",
        "response": "",
    }
    values.update(overrides)
    return RouterDecision(**values)


def _general_decision(response: str = ""):
    return _decision(message_type="general", ready_to_search=False, deep_search=False, response=response)


def _latest_context(**overrides):
    values = {
        "conversation_id": "11",
        "active_car": "",
        "last_user_text": "",
        "last_assistant_text": "",
        "latest_service_query": "",
        "recent_messages": [],
    }
    values.update(overrides)
    return values


def _parser_case(summary: str = "Stored diagnostic answer", *, links=None, extracted_cases=None):
    return {
        "forums_found": ["forum"],
        "links": links if links is not None else [{"title": "Forum case", "url": "https://example.com/case", "description": "", "type": "link"}],
        "extracted_cases": extracted_cases
        if extracted_cases is not None
        else [{"cause": "likely cause", "solution": "first check"}],
        "parser_summary": summary,
        "topics_found": [],
        "_raw": {},
    }


class FastChatCoreAcceptanceTests(unittest.TestCase):
    def _vehicle_resolver(self, *, user_id=None, car_text=""):
        text = str(car_text or "").lower()
        if "toyota" in text:
            return {"id": 10, "brand": "Toyota", "model": "Corolla", "year": 2010, "engine": "1ZZ"}
        if "nissan" in text or "x-trail" in text or "xtrail" in text:
            return {"id": 20, "brand": "Nissan", "model": "X-Trail", "year": 2003, "engine": "SR20VET"}
        return None

    def _run_chat(
        self,
        *,
        message,
        latest_context=None,
        user=None,
        decision=None,
        kb_match=None,
        history_match=None,
        parser_case=None,
    ):
        captured = {}
        kb = AsyncMock(return_value=kb_match)
        history = AsyncMock(return_value=history_match)
        parser = AsyncMock(return_value=parser_case or _parser_case())
        provider = Mock(return_value=None)
        route = AsyncMock(return_value=decision or _decision())

        async def fake_update(*args, **kwargs):
            captured["update"] = kwargs

        async def fake_translate(*, segments, target_language):
            return list(segments)

        with (
            patch.object(decision_engine, "get_or_create_user", new=AsyncMock(return_value=user or _user())),
            patch.object(decision_engine, "resolve_user_vehicle", side_effect=self._vehicle_resolver),
            patch.object(decision_engine, "route_message", new=route),
            patch.object(decision_engine, "get_latest_conversation_context", return_value=latest_context or _latest_context()),
            patch.object(decision_engine, "find_matching_case", new=kb),
            patch.object(decision_engine, "find_matching_history_case", new=history),
            patch.object(decision_engine, "find_latest_case_for_feedback", new=AsyncMock(return_value=None)),
            patch.object(decision_engine, "increment_case_success", new=AsyncMock()),
            patch.object(decision_engine, "can_run_parser", return_value=(True, {"requests_remaining": 5})),
            patch.object(decision_engine, "parse_diagnostic", new=parser),
            patch.object(decision_engine, "run_diagnostic_provider", new=provider),
            patch.object(decision_engine, "translate_segments", new=fake_translate),
            patch.object(decision_engine, "update_user_after_response", new=fake_update),
            patch.object(decision_engine, "ensure_user_subscription"),
        ):
            response = asyncio.run(
                decision_engine.process_chat_message({"message": message, "language": (decision or _decision()).language}, source="web")
            )
        return response, captured, kb, history, parser, provider, route

    def test_active_case_social_turn_skips_heavy_work_and_preserves_nissan(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text=f"{nissan} троит на холодную",
            last_assistant_text="Когда проявляется?",
            recent_messages=[
                {"role": "user", "text": f"{nissan} троит на холодную"},
                {"role": "assistant", "text": "Когда проявляется?"},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="как жизнь?",
            latest_context=latest,
            decision=_general_decision("Нормально, я на связи."),
        )

        self.assertIn("на связи", response.answer)
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertEqual(captured["update"]["active_car"], nissan)
        self.assertEqual(captured["update"]["vehicle_id"], 20)

    def test_after_social_turn_short_automotive_reply_resumes_nissan_without_parser(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text="как жизнь?",
            last_assistant_text="Нормально, я на связи.",
            recent_messages=[
                {"role": "user", "text": f"{nissan} троит на холодную"},
                {"role": "assistant", "text": "Когда проявляется?"},
                {"role": "user", "text": "как жизнь?"},
                {"role": "assistant", "text": "Нормально, я на связи."},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="после прогрева проходит",
            latest_context=latest,
        )

        self.assertFalse(parser.called)
        self.assertFalse(kb.called)
        self.assertEqual(captured["update"]["active_car"], nissan)
        self.assertEqual(captured["update"]["vehicle_id"], 20)
        self.assertEqual(captured["update"]["message_type"], "clarification")
        self.assertIn("после прогрева проходит", captured["update"]["symptom"])
        self.assertIn(nissan, response.answer)

    def test_no_active_case_social_turn_is_plain_conversation(self):
        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="как дела?",
            latest_context=_latest_context(),
            user=_user(),
            decision=_general_decision("Нормально, я на связи."),
        )

        self.assertIn("на связи", response.answer)
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["active_car"], "")
        self.assertEqual(captured["update"]["message_type"], "general")

    def test_initial_vibration_asks_clarification_without_parser(self):
        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="машина вибрирует",
            latest_context=_latest_context(),
        )

        self.assertIn("когда проявляется", response.answer.lower())
        self.assertFalse(kb.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["message_type"], "clarification")

    def test_short_acceleration_detail_keeps_case_without_parser(self):
        latest = _latest_context(
            last_user_text="машина вибрирует",
            last_assistant_text="когда проявляется?",
            recent_messages=[
                {"role": "user", "text": "машина вибрирует"},
                {"role": "assistant", "text": "когда проявляется?"},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="только при разгоне",
            latest_context=latest,
        )

        self.assertFalse(kb.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["message_type"], "clarification")
        self.assertIn("машина вибрирует", captured["update"]["symptom"])
        self.assertIn("только при разгоне", captured["update"]["symptom"])

    def test_sufficient_context_with_internal_kb_hit_stops_before_parser(self):
        toyota = "Toyota Corolla 2010 1ZZ"
        latest = _latest_context(
            active_car=toyota,
            last_user_text="только при разгоне",
            last_assistant_text="Есть ли ошибки/DTC или что-то меняли?",
            recent_messages=[
                {"role": "user", "text": f"{toyota} вибрирует"},
                {"role": "assistant", "text": "когда проявляется?"},
                {"role": "user", "text": "только при разгоне"},
                {"role": "assistant", "text": "Есть ли ошибки/DTC или что-то меняли?"},
            ],
        )
        kb_match = {"id": 7, "answer": "Internal PULS answer", "links": [], "row": {"source_table": "knowledge_cases"}}

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="началось после замены правого привода",
            latest_context=latest,
            kb_match=kb_match,
        )

        self.assertTrue(kb.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["message_type"], "kb_match")
        self.assertIn("Internal PULS answer", response.answer)

    def test_sufficient_context_with_internal_kb_miss_runs_parser_once(self):
        toyota = "Toyota Corolla 2010 1ZZ"
        latest = _latest_context(
            active_car=toyota,
            last_user_text="только при разгоне",
            last_assistant_text="Есть ли ошибки/DTC или что-то меняли?",
            recent_messages=[
                {"role": "user", "text": f"{toyota} вибрирует"},
                {"role": "assistant", "text": "когда проявляется?"},
                {"role": "user", "text": "только при разгоне"},
                {"role": "assistant", "text": "Есть ли ошибки/DTC или что-то меняли?"},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="началось после замены правого привода",
            latest_context=latest,
            kb_match=None,
        )

        self.assertTrue(kb.called)
        self.assertTrue(parser.called)
        self.assertEqual(parser.call_count, 1)
        self.assertEqual(captured["update"]["message_type"], "parser")
        self.assertIn("Stored diagnostic answer", response.answer)

    def test_parser_evidence_does_not_become_user_fact(self):
        parser_case = _parser_case(
            summary="Forum evidence says hot failures can be caused by coils",
            extracted_cases=[{"cause": "hot coil failure", "solution": "scope ignition"}],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="Toyota Corolla 2010 1ZZ вибрирует при разгоне после замены привода",
            latest_context=_latest_context(),
            kb_match=None,
            parser_case=parser_case,
        )

        self.assertTrue(parser.called)
        self.assertNotIn("hot", captured["update"]["symptom"].lower())
        self.assertIn("hot", captured["update"]["parsed_case"]["parser_summary"].lower())

    def test_old_nissan_history_does_not_override_current_toyota(self):
        old_history = (
            "source: web\nmessage_type: parser\nactive_car: Nissan X-Trail 2003 SR20VET\n"
            "symptom: Nissan old problem\nuser: Nissan old problem\nassistant: old answer"
        )
        toyota = "Toyota Corolla 2010 1ZZ"
        latest = _latest_context(
            active_car=toyota,
            last_user_text=f"{toyota} вибрирует",
            last_assistant_text="когда проявляется?",
            recent_messages=[
                {"role": "user", "text": f"{toyota} вибрирует"},
                {"role": "assistant", "text": "когда проявляется?"},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="на холодную",
            latest_context=latest,
            user=_user(history=old_history, car_info="Nissan X-Trail 2003 SR20VET"),
        )

        self.assertEqual(captured["update"]["active_car"], toyota)
        self.assertEqual(captured["update"]["vehicle_id"], 10)
        self.assertFalse(parser.called)

    def test_explicit_vehicle_switch_becomes_active_vehicle(self):
        latest = _latest_context(active_car="Toyota Corolla 2010 1ZZ", last_user_text="Toyota vibration")

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="Nissan X-Trail 2003 SR20VET троит на горячую после замены свечей P0301",
            latest_context=latest,
            kb_match=None,
        )

        self.assertEqual(captured["update"]["active_car"], "Nissan X-Trail 2003 SR20VET")
        self.assertEqual(captured["update"]["vehicle_id"], 20)
        self.assertTrue(parser.called)
        self.assertEqual(parser.call_args.args[0]["active_car"], "Nissan X-Trail 2003 SR20VET")

    def test_source_followup_uses_stored_evidence_without_parser(self):
        history_text = (
            "source: web\nmessage_type: parser\nactive_car: Toyota Corolla 2010 1ZZ\n"
            "symptom: vibration under acceleration\nuser: vibration under acceleration\n"
            "assistant: Check inner CV joint.\nlinks:\n- Stored forum: https://example.com/stored"
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="откуда это?",
            latest_context=_latest_context(active_car="Toyota Corolla 2010 1ZZ"),
            user=_user(history=history_text),
            decision=_decision(message_type="general", ready_to_search=False),
        )

        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertEqual([item.url for item in response.links], ["https://example.com/stored"])
        self.assertEqual(captured["update"]["message_type"], "general")

    def test_negative_feedback_preserves_case_and_runs_deeper_search(self):
        toyota = "Toyota Corolla 2010 1ZZ"
        history_text = (
            f"source: web\nmessage_type: parser\nactive_car: {toyota}\n"
            "symptom: vibration under acceleration after axle replacement\n"
            "user: vibration under acceleration after axle replacement\nassistant: Previous answer\n"
            "links:\n- Forum case: https://example.com/case"
        )
        latest = _latest_context(
            active_car=toyota,
            last_user_text="after axle replacement",
            last_assistant_text="Previous answer",
            recent_messages=[
                {"role": "user", "text": f"{toyota} vibrates"},
                {"role": "assistant", "text": "when does it happen?"},
                {"role": "user", "text": "under acceleration after axle replacement"},
                {"role": "assistant", "text": "Previous answer"},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="не помогло",
            latest_context=latest,
            user=_user(history=history_text),
            decision=_decision(message_type="followup_deep", user_says_not_helped=True, deep_search=True),
        )

        self.assertFalse(kb.called)
        self.assertTrue(parser.called)
        self.assertTrue(parser.call_args.args[0]["deep_search"])
        self.assertEqual(parser.call_args.args[0]["active_car"], toyota)
        self.assertIn("after axle replacement", parser.call_args.args[0]["symptom"])
        self.assertIn("Previous answer", parser.call_args.args[0]["conversation_history"])
        self.assertEqual(captured["update"]["message_type"], "parser")

    def test_large_parser_evidence_stays_concise_but_is_preserved(self):
        cases = [{"cause": f"cause {index}", "solution": f"check {index}"} for index in range(8)]
        parser_case = _parser_case(summary="Short parser summary", extracted_cases=cases)

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="Toyota Corolla 2010 1ZZ вибрирует при разгоне после замены привода",
            latest_context=_latest_context(),
            kb_match=None,
            parser_case=parser_case,
        )

        self.assertTrue(parser.called)
        self.assertLess(len(response.answer), 1200)
        self.assertEqual(len(captured["update"]["parsed_case"]["extracted_cases"]), 8)


if __name__ == "__main__":
    unittest.main()
