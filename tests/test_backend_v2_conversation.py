import asyncio
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import conversation_orchestrator as core
from app.services import v2_context

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
    def test_reference_request_is_not_a_symptom_event(self):
        self.assertEqual(
            v2_context.extract_technical_events("дай видео как заменить масло"),
            [],
        )

    def test_plain_diagnostic_symptom_stays_in_problem_memory_not_journal(self):
        self.assertEqual(
            v2_context.extract_technical_events(
                "На холодную АКПП едет, после прогрева не трогается"
            ),
            [],
        )

    def test_completed_check_remains_a_vehicle_event(self):
        events = v2_context.extract_technical_events(
            "Проверили давление АТФ: после прогрева оно падает"
        )
        self.assertEqual(events[0]["event_type"], "CHECK")

    def test_transmission_clarification_reuses_single_problem(self):
        transmission = {
            **_problem(),
            "problem_class": "TRANSMISSION",
            "title": "Automatic transmission fault",
        }
        with patch.object(core.repo, "list_problems", return_value=[transmission]):
            resolved = core.resolve_relevant_problem(
                user_id=USER_ID,
                vehicle_id=VEHICLE_ID,
                explicit_problem_id=None,
                problem_class="OTHER",
                symptom="на холодную едет, а на горячую не трогается",
            )
        self.assertEqual(resolved["id"], PROBLEM_ID)
    def test_structured_evidence_and_links_survive_empty_summary(self):
        answer = core._format_research_answer(
            "ru",
            summary="",
            links=[{"title": "Forum case", "url": "https://example.com/case", "type": "link"}],
            evidence={
                "common_causes": [{"cause": "Падение давления ATF"}],
                "solutions": [{"title": "Проверка", "description": "Измерить давление на горячую"}],
            },
            sufficient=False,
        )

        self.assertIn("Падение давления ATF", answer)
        self.assertIn("Измерить давление на горячую", answer)
        self.assertIn("https://example.com/case", answer)
        self.assertNotIn("Я запустил исследование", answer)

    def _run_chat(
        self, message, *, vehicles=None, latest_problem=None, problem=None,
        knowledge=None, research=None, saved_vehicle=True, specs=None, saved_spec=True,
    ):
        stack = ExitStack()
        mocks = {
            "profile": stack.enter_context(patch.object(core, "get_or_create_profile", new=AsyncMock(return_value=_user()))),
            "subscription": stack.enter_context(patch.object(core, "ensure_user_subscription", return_value=_sub())),
            "recent": stack.enter_context(patch.object(core.repo, "recent_conversation_messages", return_value=[])),
            "vehicles": stack.enter_context(patch.object(core.repo, "list_user_vehicles", return_value=vehicles if vehicles is not None else [])),
            "latest_problem": stack.enter_context(patch.object(core, "_latest_problem_for_context", return_value=latest_problem)),
            "resolve_problem": stack.enter_context(patch.object(core, "resolve_relevant_problem", return_value=problem)),
            "conversation": stack.enter_context(patch.object(core.repo, "get_or_create_conversation", return_value={"id": CONVERSATION_ID})),
            "associate": stack.enter_context(patch.object(core.repo, "associate_conversation_problem")),
            "save_message": stack.enter_context(patch.object(core.repo, "save_message", return_value={"id": "message-1"})),
            "save_problem": stack.enter_context(patch.object(core.repo, "save_problem", return_value=problem or _problem())),
            "event": stack.enter_context(patch.object(core.repo, "create_vehicle_event")),
            "save_vehicle": stack.enter_context(patch.object(
                core.repo, "save_vehicle",
                return_value=(_vehicle() if saved_vehicle is True else saved_vehicle),
            )),
            "get_specs": stack.enter_context(patch.object(
                core.repo, "get_vehicle_specs", return_value=specs,
            )),
            "upsert_specs": stack.enter_context(patch.object(
                core.repo, "upsert_vehicle_specs",
                return_value=({"id": "spec-1"} if saved_spec is True else saved_spec),
            )),
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
        mocks["event"].assert_not_called()
        mocks["associate"].assert_called_once()
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

    def test_confirmed_vehicle_parameter_correction_persists(self):
        vehicle = {**_vehicle(), "transmission": "Manual"}
        response, mocks = self._run_chat("Да, исправь на автомат.", vehicles=[vehicle])

        self.assertIn("изменён", response.answer)
        self.assertEqual(mocks["save_vehicle"].call_args.kwargs["payload"], {"transmission": "Automatic"})

    def test_vehicle_correction_does_not_claim_success_when_save_fails(self):
        vehicle = {**_vehicle(), "transmission": "Manual"}
        response, mocks = self._run_chat(
            "Да, исправь на автомат.", vehicles=[vehicle], saved_vehicle=None,
        )

        self.assertIn("Не удалось сохранить", response.answer)
        self.assertNotIn("изменён на", response.answer)

    def test_user_installed_part_is_saved_as_actual(self):
        response, mocks = self._run_chat(
            "У меня установлены свечи NGK BKR6E", vehicles=[_vehicle()],
        )

        payload = mocks["upsert_specs"].call_args.kwargs["payload"]
        self.assertEqual(payload["parameter_key"], "spark_plugs")
        self.assertEqual(payload["actual_value"], "NGK BKR6E")
        self.assertNotIn("recommended_value", payload)
        self.assertIn("фактически", response.answer)

    def test_recommended_part_never_becomes_actual(self):
        response, mocks = self._run_chat(
            "По мануалу рекомендуется масло 5W-40", vehicles=[_vehicle()],
        )

        payload = mocks["upsert_specs"].call_args.kwargs["payload"]
        self.assertEqual(payload["recommended_value"], "5W-40")
        self.assertNotIn("actual_value", payload)
        self.assertIn("рекомендованную", response.answer)

    def test_existing_user_confirmed_value_is_not_overwritten(self):
        existing = {
            "items": [{
                "parameter_key": "engine_oil_viscosity",
                "actual_value": "5W-30",
                "source_type": "USER",
            }]
        }
        response, mocks = self._run_chat(
            "Я использую масло 5W-40", vehicles=[_vehicle()], specs=existing,
        )

        self.assertIn("Подтвердите", response.answer)
        mocks["upsert_specs"].assert_not_called()

    def test_first_detailed_diagnostic_does_not_start_external_search(self):
        response, mocks = self._run_chat(
            "АКПП работает нормально на холодную, но после прогрева не трогается на первой и второй передаче.",
            vehicles=[_vehicle()],
            problem=None,
        )

        mocks["save_problem"].assert_called_once()
        mocks["research"].assert_not_called()
        self.assertTrue(response.answer)

    def test_first_diagnostic_uses_fast_chat_response(self):
        response, mocks = self._run_chat(
            "Двигатель троит на горячую и теряет тягу под нагрузкой.",
            vehicles=[_vehicle()],
            problem=None,
        )

        mocks["natural"].assert_awaited_once()
        self.assertIn("Когда именно", response.answer)
        mocks["research"].assert_not_called()

    def test_explicit_reference_request_still_starts_search(self):
        response, mocks = self._run_chat(
            "Найди в интернете видео как заменить масло.",
            vehicles=[_vehicle()],
            problem=None,
        )

        mocks["research"].assert_awaited_once()
        self.assertEqual(mocks["research"].call_args.kwargs["trigger_type"], "HOWTO")

    def test_later_contextualized_diagnostic_can_start_search(self):
        existing = {**_problem(), "symptoms": ["АКПП не трогается после прогрева"]}
        response, mocks = self._run_chat(
            "После прогрева давление ATF падает, ошибок нет, первая и вторая передачи буксуют.",
            vehicles=[_vehicle()],
            problem=existing,
        )

        mocks["research"].assert_awaited_once()
        self.assertEqual(mocks["research"].call_args.kwargs["trigger_type"], "DIAGNOSTIC")

    def test_search_receives_compact_accumulated_problem_context(self):
        existing = {
            **_problem(),
            "problem_class": "TRANSMISSION",
            "symptoms": ["АКПП нормально работает на холодную, после прогрева не трогается"],
            "confirmed_facts": ["Ошибок на панели нет"],
        }
        clarification = "После прогрева обороты растут, но машина почти не может разгоняться."
        response, mocks = self._run_chat(
            clarification, vehicles=[_vehicle()], problem=existing,
        )

        context = mocks["research"].call_args.kwargs["problem_context"]
        self.assertIn("после прогрева", context["problem"]["symptoms"][0])
        self.assertEqual(context["latest_clarification"], clarification)
        self.assertNotIn("recent_conversation", context)


if __name__ == "__main__":
    unittest.main()
