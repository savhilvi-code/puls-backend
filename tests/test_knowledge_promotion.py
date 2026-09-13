import asyncio
import unittest
from unittest.mock import Mock, patch

from app.services import kb_service


class KnowledgePromotionTests(unittest.TestCase):
    def test_confirmed_case_is_promoted_as_canonical_english_knowledge(self):
        created_payload = {}

        async def fake_translate(*, segments, target_language):
            self.assertEqual(target_language, "en")
            self.assertEqual(len(segments), 2)
            return [
                "Engine loses power after warm-up",
                "Check the airflow meter and intake leaks first.",
            ]

        def fake_create(payload):
            created_payload.update(payload)
            return {"id": 10, **payload}

        diagnostic_request = {
            "raw_question": "РїРѕСЃР»Рµ РїСЂРѕРіСЂРµРІР° РїСЂРѕРїР°РґР°РµС‚ С‚СЏРіР°",
            "answer": "РЎРЅР°С‡Р°Р»Р° РїСЂРѕРІРµСЂСЊС‚Рµ СЂР°СЃС…РѕРґРѕРјРµСЂ Рё РїРѕРґСЃРѕСЃ РІРѕР·РґСѓС…Р°.",
            "sources": [{"title": "source", "url": "https://example.com/thread"}],
            "brand": "Nissan",
            "model": "X-Trail",
            "year": 2003,
            "engine": "SR20VET",
        }

        with (
            patch.object(kb_service, "translate_segments", new=fake_translate),
            patch.object(kb_service, "get_supabase_client", return_value=object()),
            patch.object(kb_service, "_knowledge_case_rows", return_value=[]),
            patch.object(kb_service, "create_knowledge_case", side_effect=fake_create),
            patch.object(kb_service, "create_knowledge_event", Mock()),
        ):
            result = asyncio.run(
                kb_service.save_confirmed_case_to_knowledge(
                    diagnostic_request=diagnostic_request,
                    active_car="Nissan X-Trail 2003 SR20VET",
                    language="ru",
                )
            )

        self.assertEqual(result["id"], 10)
        self.assertEqual(created_payload["country"], "en")
        self.assertEqual(created_payload["symptom_description"], "Engine loses power after warm-up")
        self.assertEqual(created_payload["recommended_action"], "Check the airflow meter and intake leaks first.")
        self.assertEqual(created_payload["raw_payload"]["_puls_knowledge"]["source_language"], "ru")


if __name__ == "__main__":
    unittest.main()
