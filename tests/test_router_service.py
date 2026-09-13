import unittest

from app.schemas.router import RouterDecision
from app.schemas.user import UserRecord
from app.services.router_service import _local_router, _stabilize_decision


def _user_with_history() -> UserRecord:
    return UserRecord(
        id=1,
        auth_user_id="test-auth",
        email="test@example.invalid",
        username="test",
        first_name="Test",
        car_info="Nissan X-Trail GT",
        language="ru",
        conversation_history=(
            "source: web\n"
            "message_type: parser\n"
            "active_car: Nissan X-Trail GT\n"
            "symptom: old symptom\n"
            "assistant: OLD X-TRAIL DIAGNOSTIC"
        ),
        requests_left=10,
    )


def _stale_decision() -> RouterDecision:
    return RouterDecision(
        message_type="new_diagnostic",
        language="ru",
        need_car_info=False,
        need_clarification=False,
        ready_to_search=True,
        deep_search=False,
        user_says_helped=False,
        user_says_not_helped=False,
        question="old question",
        car_info="old car",
        active_car="Nissan X-Trail GT",
        symptom="old symptom",
        response="OLD X-TRAIL DIAGNOSTIC",
    )


class RouterGreetingStabilizationTests(unittest.TestCase):
    def test_pure_greetings_clear_stale_response(self):
        user = _user_with_history()
        for text in ("привет", "hello", "добрый день"):
            with self.subTest(text=text):
                decision = _stabilize_decision(text, user, _stale_decision())
                self.assertEqual(decision.message_type, "general")
                self.assertFalse(decision.ready_to_search)
                self.assertFalse(decision.deep_search)
                self.assertEqual(decision.response, "")

    def test_greeting_with_diagnostic_intent_stays_diagnostic(self):
        decision = _stabilize_decision("привет, Toyota не тянет", _user_with_history(), _stale_decision())
        self.assertEqual(decision.message_type, "new_diagnostic")
        self.assertTrue(decision.ready_to_search)
        self.assertFalse(decision.deep_search)

    def test_followup_deep_behavior_is_unchanged(self):
        decision = _stabilize_decision("не помогло", _user_with_history(), _stale_decision())
        self.assertEqual(decision.message_type, "followup_deep")
        self.assertTrue(decision.ready_to_search)
        self.assertTrue(decision.deep_search)

    def test_small_talk_fallback_stays_general(self):
        for text in ("как дела", "спасибо", "понятно", "how are you"):
            with self.subTest(text=text):
                decision = _local_router(text, "ru")
                self.assertEqual(decision.message_type, "general")
                self.assertFalse(decision.ready_to_search)
                self.assertFalse(decision.deep_search)


if __name__ == "__main__":
    unittest.main()
