import unittest
from unittest.mock import patch

from app.services import media_service, puls_data_service


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or []


class FakeQuery:
    def __init__(self, db, table, action="select", payload=None):
        self.db = db
        self.table = table
        self.action = action
        self.payload = payload
        self.filters = []
        self.limit_value = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def insert(self, payload):
        return FakeQuery(self.db, self.table, "insert", payload)

    def update(self, payload):
        return FakeQuery(self.db, self.table, "update", payload)

    def execute(self):
        rows = self.db.setdefault(self.table, [])
        if self.action == "insert":
            row = {"id": len(rows) + 1, **self.payload}
            rows.append(row)
            return FakeResponse([row])
        if self.action == "update":
            matched = self._filtered(rows)
            for row in matched:
                row.update(self.payload)
            return FakeResponse(matched)
        selected = self._filtered(rows)
        if self.limit_value is not None:
            selected = selected[: self.limit_value]
        return FakeResponse(selected)

    def _filtered(self, rows):
        selected = list(rows)
        for key, value in self.filters:
            selected = [row for row in selected if row.get(key) == value]
        return selected


class FakeClient:
    def __init__(self):
        self.db = {
            "reference_media": [],
            "media_files": [],
            "video_library": [],
        }

    def table(self, name):
        return FakeQuery(self.db, name)


class ReferenceMediaStorageTests(unittest.TestCase):
    def test_external_image_persists_as_photo_in_user_media_files(self):
        client = FakeClient()
        with patch.object(media_service, "get_supabase_client", return_value=client):
            media_service.save_media_files(
                user_id=1,
                vehicle_id=10,
                diagnostic_request_id=20,
                links=[{"title": "Image", "url": "https://example.com/image.jpg", "type": "image"}],
            )

        self.assertEqual(client.db["media_files"][0]["media_type"], "photo")

    def test_user_a_reference_media_can_be_reused_by_user_b(self):
        client = FakeClient()
        links = [{"title": "Engine number image", "url": "https://example.com/engine-number.jpg", "description": "engine number location", "type": "image"}]
        with (
            patch.object(puls_data_service, "is_supabase_configured", return_value=True),
            patch.object(puls_data_service, "get_supabase_client", return_value=client),
        ):
            puls_data_service.upsert_reference_media(
                user_id=1,
                vehicle={"brand": "BrandA", "model": "ModelB", "year": 2012, "engine": "EngineD"},
                links=links,
                subject="ENGINE_NUMBER_LOCATION",
                reference_target="ENGINE_NUMBER_LOCATION",
                language="en",
            )
            reused = puls_data_service.find_reusable_media(
                user_id=2,
                vehicle_id=None,
                subject="BrandA ModelB EngineD ENGINE_NUMBER_LOCATION",
                intent="IMAGE_REFERENCE",
            )

        self.assertEqual(len(client.db["reference_media"]), 1)
        self.assertEqual(client.db["reference_media"][0]["discovered_by_user_id"], 1)
        self.assertEqual(reused[0]["url"], "https://example.com/engine-number.jpg")

    def test_private_media_does_not_leak_between_users(self):
        client = FakeClient()
        client.db["media_files"].append(
            {
                "id": 1,
                "user_id": 1,
                "vehicle_id": 10,
                "media_type": "photo",
                "file_url": "https://private.example.com/user-a.jpg",
                "description": "engine number",
            }
        )
        with (
            patch.object(puls_data_service, "is_supabase_configured", return_value=True),
            patch.object(puls_data_service, "get_supabase_client", return_value=client),
        ):
            reused = puls_data_service.find_reusable_media(
                user_id=2,
                vehicle_id=None,
                subject="engine number",
                intent="IMAGE_REFERENCE",
            )

        self.assertEqual(reused, [])

    def test_duplicate_canonical_url_updates_instead_of_inserting(self):
        client = FakeClient()
        with (
            patch.object(puls_data_service, "is_supabase_configured", return_value=True),
            patch.object(puls_data_service, "get_supabase_client", return_value=client),
        ):
            puls_data_service.upsert_reference_media(
                user_id=1,
                vehicle={},
                links=[{"title": "First", "url": "https://example.com/page/", "description": "engine number", "type": "link"}],
                subject="engine number",
                reference_target="ENGINE_NUMBER_LOCATION",
                language="en",
            )
            puls_data_service.upsert_reference_media(
                user_id=2,
                vehicle={},
                links=[{"title": "Updated", "url": "https://example.com/page", "description": "engine number updated", "type": "link"}],
                subject="engine number",
                reference_target="ENGINE_NUMBER_LOCATION",
                language="en",
            )

        self.assertEqual(len(client.db["reference_media"]), 1)
        self.assertEqual(client.db["reference_media"][0]["title"], "Updated")

    def test_equivalent_youtube_urls_do_not_duplicate(self):
        client = FakeClient()
        with (
            patch.object(puls_data_service, "is_supabase_configured", return_value=True),
            patch.object(puls_data_service, "get_supabase_client", return_value=client),
        ):
            puls_data_service.upsert_reference_media(
                user_id=1,
                vehicle={},
                links=[{"title": "Watch", "url": "https://youtu.be/ABC123", "description": "engine number", "type": "video"}],
                subject="engine number",
                reference_target="ENGINE_NUMBER_LOCATION",
                language="en",
            )
            puls_data_service.upsert_reference_media(
                user_id=2,
                vehicle={},
                links=[{"title": "Shorts", "url": "https://www.youtube.com/shorts/ABC123", "description": "engine number", "type": "video"}],
                subject="engine number",
                reference_target="ENGINE_NUMBER_LOCATION",
                language="en",
            )

        self.assertEqual(len(client.db["reference_media"]), 1)
        self.assertEqual(client.db["reference_media"][0]["canonical_url"], "https://www.youtube.com/watch?v=ABC123")
        self.assertEqual(client.db["reference_media"][0]["external_id"], "ABC123")

    def test_irrelevant_result_is_not_promoted(self):
        client = FakeClient()
        with (
            patch.object(puls_data_service, "is_supabase_configured", return_value=True),
            patch.object(puls_data_service, "get_supabase_client", return_value=client),
        ):
            saved = puls_data_service.upsert_reference_media(
                user_id=1,
                vehicle={},
                links=[{"title": "Unrelated cooking page", "url": "https://example.com/cooking", "description": "recipe", "type": "link"}],
                subject="engine number",
                reference_target="ENGINE_NUMBER_LOCATION",
                language="en",
            )

        self.assertEqual(saved, [])
        self.assertEqual(client.db["reference_media"], [])


if __name__ == "__main__":
    unittest.main()
