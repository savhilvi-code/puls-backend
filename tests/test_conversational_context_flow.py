import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.schemas.router import RouterDecision
from app.services import decision_engine, openai_service


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
        natural_reply=None,
    ):
        captured = {}
        kb = AsyncMock(return_value=kb_match)
        history = AsyncMock(return_value=history_match)
        parser = AsyncMock(return_value=parser_case or _parser_case())
        provider = Mock(return_value=None)
        route = AsyncMock(return_value=decision or _decision())
        async def fake_natural_chat(**kwargs):
            if natural_reply is not None:
                return natural_reply
            mode = kwargs.get("mode")
            if mode == "GENERAL_CHAT":
                return "\u041d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e, \u044f \u043d\u0430 \u0441\u0432\u044f\u0437\u0438."
            if mode == "META_CHAT":
                vehicle = kwargs.get("active_vehicle") or ""
                return f"\u042f \u043f\u0440\u043e \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043c\u0430\u0448\u0438\u043d\u044b {vehicle}: \u0438\u0441\u0442\u043e\u0440\u0438\u044f \u044d\u0442\u043e\u0433\u043e \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u0430 \u0443 \u043c\u0435\u043d\u044f \u0432 \u0444\u043e\u043d\u0435."
            if mode == "CLARIFICATION":
                return kwargs.get("pending_clarification") or "\u041e\u0434\u0438\u043d \u0432\u043e\u043f\u0440\u043e\u0441?"
            return "\u041e\u0442\u0432\u0435\u0442."

        natural_chat = AsyncMock(side_effect=fake_natural_chat)

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
            patch.object(decision_engine, "generate_natural_chat_reply", new=natural_chat),
            patch.object(decision_engine, "translate_segments", new=fake_translate),
            patch.object(decision_engine, "update_user_after_response", new=fake_update),
            patch.object(decision_engine, "ensure_user_subscription"),
        ):
            response = asyncio.run(
                decision_engine.process_chat_message({"message": message, "language": (decision or _decision()).language}, source="web")
            )
        captured["natural_chat"] = natural_chat
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
        self.assertFalse(captured["update"]["should_decrease_limit"])
        captured["natural_chat"].assert_called_once()
        self.assertEqual(captured["natural_chat"].call_args.kwargs["mode"], "GENERAL_CHAT")

    def test_greeting_uses_natural_chat_without_parser_or_quota(self):
        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u043f\u0440\u0438\u0432\u0435\u0442",
            latest_context=_latest_context(),
            user=_user(),
            decision=_general_decision(""),
        )

        self.assertTrue(response.answer.strip())
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertFalse(captured["update"]["should_decrease_limit"])
        captured["natural_chat"].assert_called_once()
        self.assertEqual(captured["natural_chat"].call_args.kwargs["mode"], "GENERAL_CHAT")

    def test_greeting_with_persisted_nissan_context_does_not_mention_vehicle(self):
        latest = _latest_context(
            active_car="Nissan X-Trail 2003 SR20VET",
            last_user_text="Nissan X-Trail 2003 SR20VET \u0442\u0440\u043e\u0438\u0442",
            last_assistant_text="\u041f\u043e \u043c\u0430\u0448\u0438\u043d\u0435 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043d\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u043b.",
            recent_messages=[
                {"role": "user", "text": "Nissan X-Trail 2003 SR20VET \u0442\u0440\u043e\u0438\u0442"},
                {"role": "assistant", "text": "\u041f\u043e \u043c\u0430\u0448\u0438\u043d\u0435 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043d\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u043b."},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u043f\u0440\u0438\u0432\u0435\u0442",
            latest_context=latest,
            decision=_general_decision(""),
            natural_reply="\u041f\u0440\u0438\u0432\u0435\u0442! \u041a\u0430\u043a \u0434\u0435\u043b\u0430?",
        )

        self.assertIn("\u041f\u0440\u0438\u0432\u0435\u0442", response.answer)
        self.assertNotIn("Nissan", response.answer)
        self.assertNotIn("\u041a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 \u0434\u0438\u0430\u0433\u043d\u043e\u0437", response.answer)
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(captured["update"]["should_decrease_limit"])
        natural_kwargs = captured["natural_chat"].call_args.kwargs
        self.assertEqual(natural_kwargs["mode"], "GENERAL_CHAT")
        self.assertEqual(natural_kwargs["active_vehicle"], "")
        self.assertEqual(natural_kwargs["recent_conversation"], [])
        self.assertFalse(natural_kwargs["context_relevant"])

    def test_general_small_talk_with_persisted_nissan_context_stays_silent_about_vehicle(self):
        latest = _latest_context(
            active_car="Nissan X-Trail 2003 SR20VET",
            last_user_text="Nissan X-Trail 2003 SR20VET \u0442\u0440\u043e\u0438\u0442",
            last_assistant_text="\u041a\u043e\u0433\u0434\u0430 \u044d\u0442\u043e \u043f\u0440\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f?",
            recent_messages=[
                {"role": "user", "text": "Nissan X-Trail 2003 SR20VET \u0442\u0440\u043e\u0438\u0442"},
                {"role": "assistant", "text": "\u041a\u043e\u0433\u0434\u0430 \u044d\u0442\u043e \u043f\u0440\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f?"},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u0447\u0442\u043e \u043d\u043e\u0432\u043e\u0433\u043e?",
            latest_context=latest,
            decision=_general_decision(""),
            natural_reply="\u0412\u0441\u0435 \u0440\u043e\u0432\u043d\u043e. \u0413\u043e\u0442\u043e\u0432 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u0442\u044c, \u043a\u043e\u0433\u0434\u0430 \u0442\u044b \u0437\u0430\u0445\u043e\u0447\u0435\u0448\u044c.",
        )

        self.assertNotIn("Nissan", response.answer)
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["natural_chat"].call_args.kwargs["active_vehicle"], "")
        self.assertFalse(captured["natural_chat"].call_args.kwargs["context_relevant"])

    def test_non_automotive_question_stays_general_even_if_router_is_overeager(self):
        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u0447\u0442\u043e \u043d\u043e\u0432\u043e\u0433\u043e?",
            latest_context=_latest_context(active_car="Nissan X-Trail 2003 SR20VET"),
            user=_user(car_info="Nissan X-Trail 2003 SR20VET"),
            decision=_decision(message_type="new_diagnostic", ready_to_search=True, symptom="\u0447\u0442\u043e \u043d\u043e\u0432\u043e\u0433\u043e?"),
        )

        self.assertTrue(response.answer.strip())
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertFalse(captured["update"]["should_decrease_limit"])
        self.assertEqual(captured["natural_chat"].call_args.kwargs["mode"], "GENERAL_CHAT")

    def test_plain_text_chat_response_strips_markdown_syntax(self):
        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u043f\u0440\u0438\u0432\u0435\u0442",
            latest_context=_latest_context(),
            user=_user(),
            decision=_general_decision(""),
            natural_reply="### **\u041f\u0440\u0438\u0432\u0435\u0442**\n\n- \u042f \u043d\u0430 \u0441\u0432\u044f\u0437\u0438.",
        )

        self.assertNotIn("**", response.answer)
        self.assertNotIn("###", response.answer)
        self.assertFalse(response.answer.lstrip().startswith("- "))
        self.assertFalse(captured["update"]["should_decrease_limit"])

    def test_active_case_meta_context_question_skips_automotive_pipeline(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text="привет",
            last_assistant_text="Нормально, я на связи. По машине контекст не потерял.",
            recent_messages=[
                {"role": "user", "text": f"{nissan} троит на холодную"},
                {"role": "assistant", "text": "Когда проявляется?"},
                {"role": "user", "text": "привет"},
                {"role": "assistant", "text": "Нормально, я на связи. По машине контекст не потерял."},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="ты про какой контекст",
            latest_context=latest,
            decision=_decision(message_type="new_diagnostic", ready_to_search=True),
        )

        self.assertIn("контекст машины", response.answer.lower())
        self.assertIn(nissan, response.answer)
        self.assertNotIn("не помогло", response.answer.lower())
        self.assertNotIn("короткий диагноз", response.answer.lower())
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertEqual(captured["update"]["active_car"], nissan)
        self.assertFalse(captured["update"]["should_decrease_limit"])
        captured["natural_chat"].assert_called_once()
        self.assertEqual(captured["natural_chat"].call_args.kwargs["mode"], "META_CHAT")

    def test_meta_reaction_to_memory_context_stays_lightweight_even_if_router_requests_deep_search(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text="\u043a\u0430\u043a \u0436\u0438\u0437\u043d\u044c",
            last_assistant_text="\u0412\u0441\u0435 \u043d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e. \u041f\u043e \u043c\u0430\u0448\u0438\u043d\u0435 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043d\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u043b.",
            recent_messages=[
                {"role": "user", "text": f"{nissan} \u0442\u0440\u043e\u0438\u0442 \u043d\u0430 \u0445\u043e\u043b\u043e\u0434\u043d\u0443\u044e"},
                {"role": "assistant", "text": "\u041a\u043e\u0433\u0434\u0430 \u043f\u0440\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f?"},
                {"role": "user", "text": "\u043a\u0430\u043a \u0436\u0438\u0437\u043d\u044c"},
                {"role": "assistant", "text": "\u0412\u0441\u0435 \u043d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e. \u041f\u043e \u043c\u0430\u0448\u0438\u043d\u0435 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043d\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u043b."},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u0434\u0430 \u0442\u043e\u0436\u0435 \u043d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e \u0447\u0442\u043e \u0442\u044b \u043f\u043e\u043c\u043d\u0438\u0448\u044c \u043f\u0440\u043e \u043d\u0430\u0448\u0443 \u043f\u0435\u0440\u0435\u043f\u0438\u0441\u043a\u0443",
            latest_context=latest,
            decision=_decision(message_type="followup_deep", ready_to_search=True, deep_search=True, user_says_not_helped=True),
        )

        self.assertTrue(response.answer.strip())
        self.assertNotIn("\u041a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 \u0434\u0438\u0430\u0433\u043d\u043e\u0437", response.answer)
        self.assertNotIn("\u043d\u0435 \u043f\u043e\u043c\u043e\u0433\u043b\u043e", response.answer.lower())
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertFalse(captured["update"]["should_decrease_limit"])
        captured["natural_chat"].assert_called_once()
        self.assertEqual(captured["natural_chat"].call_args.kwargs["mode"], "META_CHAT")

    def test_meta_what_do_you_mean_answers_prior_statement_without_pipeline(self):
        latest = _latest_context(
            active_car="Nissan X-Trail 2003 SR20VET",
            last_user_text="привет",
            last_assistant_text="Нормально, я на связи. По машине контекст не потерял.",
            recent_messages=[
                {"role": "user", "text": "привет"},
                {"role": "assistant", "text": "Нормально, я на связи. По машине контекст не потерял."},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="что ты имеешь в виду?",
            latest_context=latest,
            decision=_decision(message_type="new_diagnostic", ready_to_search=True),
        )

        self.assertIn("история этого разговора", response.answer.lower())
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertFalse(provider.called)
        self.assertFalse(captured["update"]["should_decrease_limit"])
        captured["natural_chat"].assert_called_once()
        self.assertEqual(captured["natural_chat"].call_args.kwargs["mode"], "META_CHAT")

    def test_after_meta_turn_automotive_reply_resumes_context(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text="ты про какой контекст",
            last_assistant_text=f"Я про контекст машины, которую мы обсуждали: {nissan}.",
            recent_messages=[
                {"role": "user", "text": f"{nissan} троит на холодную"},
                {"role": "assistant", "text": "Когда проявляется?"},
                {"role": "user", "text": "ты про какой контекст"},
                {"role": "assistant", "text": f"Я про контекст машины, которую мы обсуждали: {nissan}."},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="ладно, по машине - после прогрева проходит",
            latest_context=latest,
        )

        self.assertFalse(kb.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["active_car"], nissan)
        self.assertIn("после прогрева проходит", captured["update"]["symptom"])
        self.assertEqual(captured["update"]["message_type"], "clarification")
        self.assertFalse(captured["update"]["should_decrease_limit"])

    def test_continue_with_car_may_use_persisted_vehicle_context(self):
        nissan = "Nissan X-Trail 2003 SR20VET"
        latest = _latest_context(
            active_car=nissan,
            last_user_text="\u043a\u0430\u043a \u0436\u0438\u0437\u043d\u044c",
            last_assistant_text="\u041f\u0440\u0438\u0432\u0435\u0442! \u041a\u0430\u043a \u0434\u0435\u043b\u0430?",
            recent_messages=[
                {"role": "user", "text": f"{nissan} \u0442\u0440\u043e\u0438\u0442"},
                {"role": "assistant", "text": "\u041a\u043e\u0433\u0434\u0430 \u044d\u0442\u043e \u043f\u0440\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f?"},
            ],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u0434\u0430\u0432\u0430\u0439 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u043c \u0441 \u043c\u0430\u0448\u0438\u043d\u043e\u0439",
            latest_context=latest,
            decision=_decision(message_type="general", ready_to_search=False),
        )

        self.assertIn(nissan, response.answer)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["active_car"], nissan)
        self.assertEqual(captured["update"]["message_type"], "clarification")
        self.assertTrue(captured["natural_chat"].call_args.kwargs["context_relevant"])
        self.assertEqual(captured["natural_chat"].call_args.kwargs["active_vehicle"], nissan)

    def test_saved_vehicle_question_answers_from_persisted_profile(self):
        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u043a\u0430\u043a\u0430\u044f \u0443 \u043c\u0435\u043d\u044f \u043c\u0430\u0448\u0438\u043d\u0430?",
            latest_context=_latest_context(),
            user=_user(car_info="Nissan X-Trail 2003 SR20VET"),
            decision=_decision(message_type="new_diagnostic", ready_to_search=True),
        )

        self.assertIn("Nissan X-Trail 2003 SR20VET", response.answer)
        self.assertFalse(kb.called)
        self.assertFalse(history.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertFalse(captured["update"]["should_decrease_limit"])
        self.assertEqual(captured["natural_chat"].call_args.kwargs["mode"], "META_CHAT")
        self.assertEqual(captured["natural_chat"].call_args.kwargs["active_vehicle"], "Nissan X-Trail 2003 SR20VET")

    def test_saved_my_car_persistence_question_gets_accurate_natural_answer(self):
        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="\u0435\u0441\u043b\u0438 \u044f \u0434\u043e\u0431\u0430\u0432\u043b\u044e \u043c\u0430\u0448\u0438\u043d\u0443 \u0432 \u0440\u0430\u0437\u0434\u0435\u043b \u043c\u043e\u0439 \u0430\u0432\u0442\u043e\u043c\u043e\u0431\u0438\u043b\u044c \u0442\u044b \u0431\u0443\u0434\u0435\u0448\u044c \u043f\u043e\u043c\u043d\u0438\u0442\u044c?",
            latest_context=_latest_context(),
            decision=_decision(message_type="new_diagnostic", ready_to_search=True),
            natural_reply="\u0414\u0430. \u0415\u0441\u043b\u0438 \u043c\u0430\u0448\u0438\u043d\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430 \u0432 \u0440\u0430\u0437\u0434\u0435\u043b\u0435 \u00ab\u041c\u043e\u0439 \u0430\u0432\u0442\u043e\u043c\u043e\u0431\u0438\u043b\u044c\u00bb, \u044f \u0441\u043c\u043e\u0433\u0443 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c \u0435\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u0432 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0445 \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u0430\u0445.",
        )

        self.assertIn("\u041c\u043e\u0439 \u0430\u0432\u0442\u043e\u043c\u043e\u0431\u0438\u043b\u044c", response.answer)
        self.assertIn("\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0445 \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u0430\u0445", response.answer)
        self.assertNotIn("\u043d\u0435 \u0431\u0443\u0434\u0443 \u043f\u043e\u043c\u043d\u0438\u0442\u044c", response.answer.lower())
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["message_type"], "general")
        self.assertFalse(captured["update"]["should_decrease_limit"])
        self.assertTrue(captured["natural_chat"].call_args.kwargs["context_relevant"])

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
        self.assertFalse(captured["update"]["should_decrease_limit"])

    def test_initial_vibration_asks_clarification_without_parser(self):
        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="машина вибрирует",
            latest_context=_latest_context(),
        )

        self.assertIn("когда проявляется", response.answer.lower())
        self.assertFalse(kb.called)
        self.assertFalse(parser.called)
        self.assertEqual(captured["update"]["message_type"], "clarification")
        self.assertFalse(captured["update"]["should_decrease_limit"])

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
        self.assertFalse(captured["update"]["should_decrease_limit"])

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
        self.assertFalse(captured["update"]["should_decrease_limit"])

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
        self.assertTrue(captured["update"]["should_decrease_limit"])

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
        self.assertTrue(captured["update"]["should_decrease_limit"])

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
        self.assertFalse(captured["update"]["should_decrease_limit"])

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
        self.assertTrue(captured["update"]["should_decrease_limit"])

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
        self.assertFalse(captured["update"]["should_decrease_limit"])

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
        self.assertTrue(captured["update"]["should_decrease_limit"])

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
        self.assertTrue(captured["update"]["should_decrease_limit"])

    def test_parser_episode_with_large_internal_work_still_decrements_once(self):
        parser_case = _parser_case(
            summary="Parser combined several searches",
            links=[{"title": f"Source {index}", "url": f"https://example.com/{index}", "description": "", "type": "link"} for index in range(6)],
            extracted_cases=[{"cause": f"cause {index}", "solution": f"check {index}"} for index in range(6)],
        )

        response, captured, kb, history, parser, provider, route = self._run_chat(
            message="Toyota Corolla 2010 1ZZ вибрирует при разгоне после замены привода P0000",
            latest_context=_latest_context(),
            kb_match=None,
            parser_case=parser_case,
        )

        self.assertEqual(parser.call_count, 1)
        self.assertTrue(captured["update"]["should_decrease_limit"])

    def test_natural_chat_receives_persisted_context_capability_instruction(self):
        captured = {}

        class FakeResponses:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(output_text='{"reply":"\u041f\u043e\u043c\u043d\u044e \u0442\u043e\u043b\u044c\u043a\u043e \u0442\u043e, \u0447\u0442\u043e \u0435\u0441\u0442\u044c \u0432 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0435."}')

        client = SimpleNamespace(responses=FakeResponses())
        recent = [{"role": "assistant", "text": "\u041f\u043e \u043c\u0430\u0448\u0438\u043d\u0435 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043d\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u043b."}]

        with (
            patch.object(openai_service, "is_configured", return_value=True),
            patch.object(openai_service, "get_openai_client", return_value=client),
        ):
            reply = asyncio.run(
                openai_service.generate_natural_chat_reply(
                    mode="META_CHAT",
                    user_text="\u0447\u0442\u043e \u0442\u044b \u043f\u043e\u043c\u043d\u0438\u0448\u044c",
                    language="ru",
                    recent_conversation=recent,
                    active_vehicle="Nissan X-Trail 2003 SR20VET",
                )
            )

        self.assertIn("\u041f\u043e\u043c\u043d\u044e", reply)
        self.assertIn("persisted conversation and vehicle context", captured["instructions"])
        self.assertIn("Do not claim that conversation or vehicle history is unavailable", captured["instructions"])
        self.assertIn("Persisted context is normally silent background", captured["instructions"])
        self.assertIn("For simple greetings or casual small talk, do not mention vehicles", captured["instructions"])
        payload = captured["input"]
        self.assertIn("Nissan X-Trail 2003 SR20VET", payload)
        self.assertIn("\u041f\u043e \u043c\u0430\u0448\u0438\u043d\u0435", payload)

    def test_general_chat_payload_omits_silent_context(self):
        captured = {}

        async def fake_natural_chat(**kwargs):
            captured.update(kwargs)
            return "\u041f\u0440\u0438\u0432\u0435\u0442! \u041a\u0430\u043a \u0434\u0435\u043b\u0430?"

        latest = _latest_context(
            active_car="Nissan X-Trail 2003 SR20VET",
            recent_messages=[{"role": "assistant", "text": "\u041f\u043e \u043c\u0430\u0448\u0438\u043d\u0435 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043d\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u043b."}],
        )
        with (
            patch.object(decision_engine, "get_or_create_user", new=AsyncMock(return_value=_user(car_info="Nissan X-Trail 2003 SR20VET"))),
            patch.object(decision_engine, "route_message", new=AsyncMock(return_value=_general_decision(""))),
            patch.object(decision_engine, "get_latest_conversation_context", return_value=latest),
            patch.object(decision_engine, "generate_natural_chat_reply", new=fake_natural_chat),
            patch.object(decision_engine, "update_user_after_response", new=AsyncMock()),
            patch.object(decision_engine, "ensure_user_subscription"),
            patch.object(decision_engine, "resolve_user_vehicle", side_effect=self._vehicle_resolver),
        ):
            asyncio.run(decision_engine.process_chat_message({"message": "\u043f\u0440\u0438\u0432\u0435\u0442", "language": "ru"}, source="web"))

        self.assertEqual(captured["recent_conversation"], [])
        self.assertEqual(captured["active_vehicle"], "")
        self.assertEqual(captured["automotive_context"], "")
        self.assertEqual(captured["stored_facts"], [])
        self.assertFalse(captured["context_relevant"])

    def test_routing_failure_before_parser_does_not_decrement_quota(self):
        captured = {}

        async def fake_update(*args, **kwargs):
            captured["update"] = kwargs

        async def failing_route(normalized, user):
            raise RuntimeError("router failed before parser")

        with (
            patch.object(decision_engine, "get_or_create_user", new=AsyncMock(return_value=_user())),
            patch.object(decision_engine, "get_latest_conversation_context", return_value=_latest_context()),
            patch.object(decision_engine, "route_message", new=failing_route),
            patch.object(decision_engine, "parse_diagnostic", new=AsyncMock()),
            patch.object(decision_engine, "update_user_after_response", new=fake_update),
        ):
            with self.assertRaises(RuntimeError):
                asyncio.run(decision_engine.process_chat_message({"message": "Toyota vibrates", "language": "en"}, source="web"))

        self.assertEqual(captured, {})


if __name__ == "__main__":
    unittest.main()
