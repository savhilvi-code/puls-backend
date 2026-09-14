import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services import user_service


def _normalized(text: str = "hello"):
    return SimpleNamespace(text=text, language="ru", car_info="")


def _user():
    return SimpleNamespace(id=1, car_info="", conversation_history="", requests_left=6)


class QuotaSemanticsTests(unittest.TestCase):
    def _run_update(self, **overrides):
        consume = Mock()
        create_parser_run = Mock(return_value={"id": 22})
        update_diagnostic = Mock()
        kwargs = {
            "answer": "answer",
            "should_decrease_limit": False,
            "message_type": "general",
            "parser_used": False,
            "deep_search_used": False,
            "parsed_case": None,
        }
        kwargs.update(overrides)

        with (
            patch.object(user_service, "get_or_create_conversation", return_value={"id": 11}),
            patch.object(user_service, "save_message"),
            patch.object(user_service, "create_diagnostic_request", return_value={"id": 33}),
            patch.object(user_service, "create_parser_run", create_parser_run),
            patch.object(user_service, "consume_parser_credit", consume),
            patch.object(user_service, "update_diagnostic_request", update_diagnostic),
            patch.object(user_service, "save_media_files"),
            patch.object(user_service, "save_video_library"),
            patch.object(user_service, "get_latest_diagnostic_request", return_value=None),
            patch.object(user_service, "create_feedback"),
            patch.object(user_service, "_hydrate_runtime_fields"),
        ):
            asyncio.run(user_service.update_user_after_response(_user(), _normalized(), **kwargs))

        return consume, create_parser_run, update_diagnostic

    def test_general_chat_does_not_consume_credit(self):
        consume, create_parser_run, update_diagnostic = self._run_update(message_type="general")

        consume.assert_not_called()
        create_parser_run.assert_not_called()
        update_diagnostic.assert_not_called()

    def test_meta_chat_does_not_consume_credit(self):
        consume, create_parser_run, update_diagnostic = self._run_update(message_type="general")

        consume.assert_not_called()
        create_parser_run.assert_not_called()
        update_diagnostic.assert_not_called()

    def test_clarification_does_not_consume_credit(self):
        consume, create_parser_run, update_diagnostic = self._run_update(message_type="clarification")

        consume.assert_not_called()
        create_parser_run.assert_not_called()
        update_diagnostic.assert_not_called()

    def test_kb_hit_does_not_consume_credit(self):
        consume, create_parser_run, update_diagnostic = self._run_update(message_type="kb_match")

        consume.assert_not_called()
        create_parser_run.assert_not_called()
        update_diagnostic.assert_not_called()

    def test_parser_episode_consumes_exactly_one_credit(self):
        consume, create_parser_run, update_diagnostic = self._run_update(
            message_type="parser",
            parser_used=True,
            parsed_case={"parser_summary": "combined several external searches"},
            should_decrease_limit=True,
        )

        create_parser_run.assert_called_once()
        consume.assert_called_once_with(user_id=1)
        update_diagnostic.assert_called_once_with(
            diagnostic_request_id=33,
            payload={"request_cost_counted": True},
        )


if __name__ == "__main__":
    unittest.main()
