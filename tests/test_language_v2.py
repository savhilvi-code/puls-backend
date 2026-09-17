import unittest

from app.utils.language import detect_language, requested_response_language


class LanguageDetectionTests(unittest.TestCase):
    def test_russian_prose_stays_russian_with_technical_terms(self):
        messages = (
            "Почему ты перешел на английский?",
            "Дублирую симптомы:",
            "У меня проблема с АКПП на горячую",
            "У меня Peugeot XU9J2, горит Check Engine, проверил VIN и ATF.",
        )

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(detect_language(message, fallback="en"), "ru")

    def test_genuine_english_prose_remains_english(self):
        self.assertEqual(
            detect_language("My Peugeot has a Check Engine light when hot", fallback="ru"),
            "en",
        )

    def test_technical_only_turn_uses_conversation_fallback(self):
        self.assertEqual(detect_language("VIN XU9J2?", fallback="ru"), "ru")
        self.assertEqual(detect_language("VIN XU9J2?", fallback="en"), "en")

    def test_only_explicit_switch_requests_override_response_language(self):
        self.assertIsNone(requested_response_language("Почему ты перешел на английский?"))
        self.assertEqual(requested_response_language("Ответь на английском, пожалуйста."), "en")
        self.assertEqual(requested_response_language("Please reply in Russian."), "ru")


if __name__ == "__main__":
    unittest.main()
