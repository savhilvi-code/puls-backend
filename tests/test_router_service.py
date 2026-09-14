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
        conversation_history="active_car: Nissan X-Trail GT\nsymptom: old symptom\nassistant: old answer",
        requests_left=10,
    )


def _stale_decision() -> RouterDecision:
    return RouterDecision(
        message_type="new_diagnostic",
        language="ru",
        ready_to_search=True,
        deep_search=False,
        active_car="Nissan X-Trail GT",
        symptom="old symptom",
        response="OLD DIAGNOSTIC",
    )


class RouterStabilizationTests(unittest.TestCase):
    def test_social_text_clears_stale_response(self):
        for text in ("привет", "hello", "добрый день", "как дела"):
            with self.subTest(text=text):
                decision = _stabilize_decision(text, _user_with_history(), _stale_decision())
                self.assertEqual(decision.message_type, "general")
                self.assertFalse(decision.ready_to_search)
                self.assertFalse(decision.deep_search)
                self.assertEqual(decision.response, "")

    def test_greeting_with_diagnostic_content_stays_diagnostic(self):
        decision = _stabilize_decision("привет, Toyota не тянет", _user_with_history(), _stale_decision())
        self.assertEqual(decision.message_type, "new_diagnostic")
        self.assertTrue(decision.ready_to_search)

    def test_negative_feedback_requests_deeper_search(self):
        decision = _stabilize_decision("не помогло", _user_with_history(), _stale_decision())
        self.assertEqual(decision.message_type, "followup_deep")
        self.assertTrue(decision.ready_to_search)
        self.assertTrue(decision.deep_search)
        self.assertTrue(decision.user_says_not_helped)

    def test_small_talk_local_fallback_is_general(self):
        for text in ("как дела", "спасибо", "how are you"):
            with self.subTest(text=text):
                decision = _local_router(text, "ru")
                self.assertEqual(decision.message_type, "general")
                self.assertFalse(decision.ready_to_search)


if __name__ == "__main__":
    unittest.main()
