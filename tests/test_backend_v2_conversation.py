import asyncio
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import conversation_orchestrator as core

USER_ID = "11111111-1111-4111-8111-111111111111"
VEHICLE_ID = "22222222-2222-4222-8222-222222222222"
PROBLEM_ID = "33333333-3333-4333-8333-333333333333"
CONVERSATION_ID = "44444444-4444-4444-8444-444444444444"


def _user():
    return SimpleNamespace(id=USER_ID, email="a@example.com", language="en")


def _sub():
    return {"id": "sub-a", "user_id": USER_ID, "quota_limit": 10, "quota_used": 2, "plan": "free"}


def _vehicle(vehicle_id=VEHICLE_ID, brand="Nissan"):
    return {"id": vehicle_id, "user_id": USER_ID, "brand": brand, "model": "X-Trail", "year": 2003, "engine": "SR20VET"}


def _problem(problem_id=PROBLEM_ID):
    return {"id": problem_id, "user_id": USER_ID, "vehicle_id": VEHICLE_ID, "title": "Misfire", "problem_class": "MISFIRE", "status": "OPEN"}


class BackendV2ConversationTests(unittest.TestCase):
    def _run_chat(self, message, *, vehicles=None, latest_problem=None, problem=None, knowledge=None, research=None):
        stack = ExitStack()
        mocks = {
            "profile": stack.enter_context(patch.object(core, "get_or_create_profile", new=AsyncMock(return_value=_user()))),
            "subscription": stack.enter_context(patch.object(core, "ensure_user_subscription", return_value=_sub())),
            "recent": stack.enter_context(patch.object(core.repo, "recent_conversation_messages", return_value=[])),
            "vehicles": stack.enter_context(patch.object(core.repo, "list_user_vehicles", return_value=vehicles if vehicles is not None else [])),
            "latest_problem": stack.enter_context(patch.object(core, "_latest_problem_for_context", return_value=latest_problem)),
            "resolve_problem": stack.enter_context(patch.object(core, "resolve_relevant_problem", return_value=problem)),
            "conversation": stack.enter_context(patch.object(core.repo, "get_or_create_conversation", return_value={"id": CONVERSATION_ID})),
            "save_message": stack.enter_context(patch.object(core.repo, "save_message")),
            "save_problem": stack.enter_context(patch.object(core.repo, "save_problem", return_value=problem or _problem())),
            "event": stack.enter_context(patch.object(core.repo, "create_vehicle_event")),
            "knowledge": stack.enter_context(patch.object(core.repo, "find_relevant_knowledge", return_value=knowledge or [])),
            "natural": stack.enter_context(patch.object(core, "_natural_reply", new=AsyncMock(side_effect=lambda context, **kwargs: context.clarification_question or "Hi, I am here."))),
            "research": stack.enter_context(
                patch.object(
                    core,
                    "run_search_stages",
                    new=AsyncMock(return_value=research or SimpleNamespace(summary="evidence summary", links=[], sufficient=True, quota=_sub())),
                )
            ),
        }
        try:
            response = asyncio.run(core.process_chat_message_v2({"message": message, "language": "en"}))
            return response, mocks
        finally:
            stack.close()

    def test_greeting_does_not_use_stale_vehicle_or_research(self):
        response, mocks = self._run_chat("hello", vehicles=[_vehicle()], latest_problem=_problem())

        self.assertEqual(response.answer, "Hi, I am here.")
        mocks["research"].assert_not_called()
        mocks["event"].assert_not_called()
        saved_messages = mocks["save_message"].call_args_list
        self.assertTrue(saved_messages)
        self.assertIsNone(saved_messages[0].kwargs["vehicle_id"])
        self.assertIsNone(saved_messages[0].kwargs["problem_id"])

    def test_russian_message_overrides_english_ui_locale_and_is_persisted(self):
        response, mocks = self._run_chat(
            "У меня Peugeot XU9J2, горит Check Engine и проблема с АКПП на горячую"
        )

        self.assertEqual(mocks["natural"].call_args.args[0].language, "ru")
        saved_messages = mocks["save_message"].call_args_list
        self.assertEqual(saved_messages[0].kwargs["language"], "ru")
        self.assertEqual(saved_messages[1].kwargs["language"], "ru")

    def test_explicit_response_switch_does_not_change_user_message_language(self):
        response, mocks = self._run_chat("Ответь на английском, пожалуйста.")

        self.assertEqual(mocks["natural"].call_args.args[0].language, "en")
        saved_messages = mocks["save_message"].call_args_list
        self.assertEqual(saved_messages[0].kwargs["language"], "ru")
        self.assertEqual(saved_messages[1].kwargs["language"], "en")

    def test_ambiguous_vehicle_asks_one_question_before_research(self):
        response, mocks = self._run_chat("I hear a strange noise", vehicles=[_vehicle(VEHICLE_ID, "Nissan"), _vehicle("55555555-5555-4555-8555-555555555555", "Toyota")])

        self.assertIn("Which vehicle", response.answer)
        mocks["research"].assert_not_called()
        mocks["event"].assert_not_called()

    def test_clarification_creates_problem_but_not_search_episode(self):
        response, mocks = self._run_chat("Nissan X-Trail makes noise", vehicles=[_vehicle()], problem=None)

        self.assertIn("Where is the noise", response.answer)
        mocks["save_problem"].assert_called_once()
        mocks["event"].assert_called()
        mocks["research"].assert_not_called()

    def test_internal_knowledge_answers_without_external_research(self):
        response, mocks = self._run_chat(
            "Nissan X-Trail P0300 misfires when cold",
            vehicles=[_vehicle()],
            problem=_problem(),
            knowledge=[{"id": 100, "summary": "Known internal cause"}],
        )

        self.assertIn("internal knowledge", response.answer)
        mocks["research"].assert_not_called()

    def test_diagnostic_reuses_existing_problem_and_runs_staged_research(self):
        existing_problem_id = "66666666-6666-4666-8666-666666666666"
        existing = _problem(existing_problem_id)
        response, mocks = self._run_chat("Nissan X-Trail P0300 misfires when cold", vehicles=[_vehicle()], problem=existing)

        self.assertIn("evidence summary", response.answer)
        mocks["research"].assert_called_once()
        self.assertEqual(mocks["research"].call_args.kwargs["problem_id"], existing_problem_id)
        self.assertEqual(mocks["save_problem"].call_args.kwargs["problem_id"], existing_problem_id)


if __name__ == "__main__":
    unittest.main()
