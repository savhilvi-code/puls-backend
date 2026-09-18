import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services import search_stage_service as stages


class SearchStageV2Tests(unittest.TestCase):
    def test_sufficient_stage_one_stops_and_consumes_once(self):
        runner = AsyncMock(
            return_value={
                "parser_summary": "Known source-backed answer",
                "links": [{"title": "Source", "url": "https://example.com/thread"}],
                "extracted_cases": [],
                "sufficient_evidence": True,
                "_raw": {},
            }
        )
        with (
            patch.object(stages, "can_run_research", return_value=(True, {"quota_limit": 10, "quota_used": 0})),
            patch.object(stages, "consume_research_credit", return_value={"quota_limit": 10, "quota_used": 1}) as consume,
            patch.object(stages.repo, "create_search_episode", return_value={"id": 77}) as create_episode,
            patch.object(stages.repo, "get_latest_problem_research", return_value=None),
            patch.object(stages.repo, "create_search_run", side_effect=lambda **kwargs: {"id": kwargs["payload"]["stage_number"], **kwargs["payload"]}) as create_run,
            patch.object(stages.repo, "update_search_episode") as update_episode,
            patch.object(stages.repo, "upsert_source", return_value={"id": 300}),
            patch.object(stages.repo, "link_problem_source") as link_source,
            patch.object(stages, "get_search_provider", return_value="claude"),
        ):
            result = asyncio.run(
                stages.run_search_stages(
                    user_id=1,
                    vehicle_id=10,
                    problem_id=20,
                    vehicle_label="Nissan X-Trail",
                    query="P0300 cold misfire",
                    language="en",
                    runner=runner,
                )
            )

        self.assertTrue(result.sufficient)
        self.assertEqual(runner.call_count, 1)
        consume.assert_called_once_with(user_id=1)
        self.assertEqual(create_run.call_args.kwargs["payload"]["stage_number"], 1)
        self.assertTrue(create_run.call_args.kwargs["payload"]["sufficient_evidence"])
        update_episode.assert_called_once()
        link_source.assert_called_once()
        self.assertEqual(create_episode.call_args.kwargs["trigger_type"], "DIAGNOSTIC")

    def test_stage_two_receives_previous_stage_evidence(self):
        runner = AsyncMock(
            side_effect=[
                {"parser_summary": "", "links": [], "extracted_cases": [], "_raw": {}},
                {
                    "parser_summary": "Expanded answer",
                    "links": [{"title": "Source", "url": "https://example.com/expanded"}],
                    "extracted_cases": [],
                    "sufficient_evidence": True,
                    "_raw": {},
                },
            ]
        )
        saved_runs = []

        def save_run(**kwargs):
            payload = kwargs["payload"]
            saved = {"id": payload["stage_number"], **payload}
            saved_runs.append(saved)
            return saved

        with (
            patch.object(stages, "can_run_research", return_value=(True, {"quota_limit": 10, "quota_used": 0})),
            patch.object(stages, "consume_research_credit", return_value={"quota_limit": 10, "quota_used": 1}),
            patch.object(stages.repo, "create_search_episode", return_value={"id": 77}),
            patch.object(stages.repo, "get_latest_problem_research", return_value=None),
            patch.object(stages.repo, "create_search_run", side_effect=save_run),
            patch.object(stages.repo, "update_search_episode"),
            patch.object(stages.repo, "upsert_source", return_value={"id": 300}),
            patch.object(stages.repo, "link_problem_source"),
            patch.object(stages, "get_search_provider", return_value="openai"),
        ):
            result = asyncio.run(
                stages.run_search_stages(
                    user_id=1,
                    vehicle_id=10,
                    problem_id=20,
                    vehicle_label="Nissan X-Trail",
                    query="P0300 cold misfire",
                    language="en",
                    runner=runner,
                )
            )

        self.assertTrue(result.sufficient)
        self.assertEqual(runner.call_count, 2)
        second_call_payload = runner.call_args_list[1].args[0]
        self.assertEqual(second_call_payload["mode"], "normal")
        self.assertEqual(runner.call_args_list[0].args[0]["source_group"], "model_owner")
        self.assertEqual(second_call_payload["source_group"], "general_technical")
        self.assertIn('"stage_number":1', second_call_payload["evidence_context"])
        self.assertEqual([run["stage_number"] for run in saved_runs], [1, 2])
        self.assertFalse(saved_runs[0]["sufficient_evidence"])
        self.assertTrue(saved_runs[1]["sufficient_evidence"])
        self.assertEqual(
            saved_runs[1]["result_data"]["evidence_state"],
            stages.SUFFICIENT_EVIDENCE,
        )

    def test_accumulated_evidence_participates_in_later_sufficiency(self):
        runner = AsyncMock(side_effect=[
            {"common_causes": [{"cause": "Hot ATF pressure loss"}], "links": [], "_raw": {}},
            {"links": [{"title": "Source", "url": "https://example.com/atf"}], "sufficient_evidence": True, "_raw": {}},
        ])
        with (
            patch.object(stages, "can_run_research", return_value=(True, {})),
            patch.object(stages, "consume_research_credit", return_value={}),
            patch.object(stages.repo, "create_search_episode", return_value={"id": 77}),
            patch.object(stages.repo, "get_latest_problem_research", return_value=None),
            patch.object(stages.repo, "create_search_run", side_effect=lambda **kwargs: {"id": kwargs["payload"]["stage_number"], **kwargs["payload"]}),
            patch.object(stages.repo, "update_search_episode"),
            patch.object(stages.repo, "upsert_source", return_value={"id": 300}),
            patch.object(stages.repo, "link_problem_source"),
        ):
            result = asyncio.run(stages.run_search_stages(
                user_id=1, vehicle_id=10, problem_id=20, vehicle_label="Peugeot 307",
                query="hot transmission slip", language="en", runner=runner,
            ))

        self.assertTrue(result.sufficient)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(result.evidence["common_causes"][0]["cause"], "Hot ATF pressure loss")

    def test_useful_unlinked_evidence_is_preliminary_not_discarded(self):
        runner = AsyncMock(return_value={
            "common_causes": [{"cause": "Possible pressure loss"}],
            "solutions": [{"title": "Check ATF pressure"}],
            "links": [],
            "_raw": {},
        })
        with (
            patch.object(stages, "can_run_research", return_value=(True, {})),
            patch.object(stages, "consume_research_credit", return_value={}),
            patch.object(stages.repo, "create_search_episode", return_value={"id": 77}),
            patch.object(stages.repo, "get_latest_problem_research", return_value=None),
            patch.object(stages.repo, "create_search_run", side_effect=lambda **kwargs: {"id": kwargs["payload"]["stage_number"], **kwargs["payload"]}),
            patch.object(stages.repo, "update_search_episode"),
            patch.object(stages.repo, "upsert_source", return_value=None),
            patch.object(stages.repo, "link_problem_source"),
        ):
            result = asyncio.run(stages.run_search_stages(
                user_id=1, vehicle_id=10, problem_id=20, vehicle_label="Peugeot 307",
                query="hot transmission slip", language="en", runner=runner,
            ))

        self.assertFalse(result.sufficient)
        self.assertEqual(result.evidence["common_causes"][0]["cause"], "Possible pressure loss")
        self.assertEqual(runner.call_count, 3)

    def test_quota_exhaustion_prevents_episode_creation(self):
        with (
            patch.object(stages, "can_run_research", return_value=(False, {"quota_limit": 10, "quota_used": 10})),
            patch.object(stages.repo, "get_latest_problem_research", return_value=None),
            patch.object(stages.repo, "create_search_episode") as create_episode,
        ):
            result = asyncio.run(
                stages.run_search_stages(
                    user_id=1,
                    vehicle_id=10,
                    problem_id=20,
                    vehicle_label="Nissan X-Trail",
                    query="P0300",
                    language="en",
                    runner=AsyncMock(),
                )
            )

        self.assertFalse(result.sufficient)
        create_episode.assert_not_called()

    def test_same_problem_clarification_reuses_persisted_research_without_calls_or_quota(self):
        persisted = {
            "episode": {
                "id": 77,
                "final_summary": "Stored conclusion",
                "trigger_type": "DIAGNOSTIC",
                "search_context": {"reason": "акпп не едет на горячую"},
            },
            "runs": [
                {
                    "sufficient_evidence": True,
                    "result_data": {
                        "parser_summary": "Stored conclusion",
                        "common_causes": [{"cause": "Stored cause"}],
                    },
                }
            ],
            "sources": [
                {
                    "extracted_evidence": "Stored evidence",
                    "sources": {
                        "title": "Stored source",
                        "url": "https://example.com/stored",
                        "source_type": "FORUM",
                    },
                }
            ],
        }
        runner = AsyncMock()
        with (
            patch.object(stages, "can_run_research", return_value=(True, {"quota_limit": 10, "quota_used": 1})),
            patch.object(stages.repo, "get_latest_problem_research", return_value=persisted),
            patch.object(stages.repo, "create_search_episode") as create_episode,
            patch.object(stages, "consume_research_credit") as consume,
        ):
            result = asyncio.run(
                stages.run_search_stages(
                    user_id=1,
                    vehicle_id=10,
                    problem_id=20,
                    vehicle_label="Peugeot 307",
                    query="на холодную едет, на горячую не трогается",
                    language="ru",
                    runner=runner,
                )
            )

        self.assertTrue(result.reused)
        self.assertEqual(result.summary, "Stored conclusion")
        self.assertEqual(result.links[0]["url"], "https://example.com/stored")
        self.assertEqual(result.evidence["common_causes"][0]["cause"], "Stored cause")
        runner.assert_not_called()
        create_episode.assert_not_called()
        consume.assert_not_called()

    def test_materially_new_same_problem_symptom_starts_new_episode(self):
        persisted = {
            "episode": {
                "id": 70,
                "search_context": {"reason": "акпп не едет на горячую"},
            },
            "runs": [],
            "sources": [],
        }
        runner = AsyncMock(
            return_value={
                "parser_summary": "Noise diagnosis",
                "links": [{"title": "Source", "url": "https://example.com/noise"}],
                "sufficient_evidence": True,
                "_raw": {},
            }
        )
        with (
            patch.object(stages, "can_run_research", return_value=(True, {"quota_limit": 10, "quota_used": 1})),
            patch.object(stages.repo, "get_latest_problem_research", return_value=persisted),
            patch.object(stages.repo, "create_search_episode", return_value={"id": 71}) as create_episode,
            patch.object(stages.repo, "create_search_run", side_effect=lambda **kwargs: {"id": 1, **kwargs["payload"]}),
            patch.object(stages.repo, "update_search_episode"),
            patch.object(stages.repo, "upsert_source", return_value={"id": 300}),
            patch.object(stages.repo, "link_problem_source"),
            patch.object(stages, "consume_research_credit", return_value={"quota_limit": 10, "quota_used": 2}),
            patch.object(stages, "get_search_provider", return_value="claude"),
        ):
            result = asyncio.run(
                stages.run_search_stages(
                    user_id=1,
                    vehicle_id=10,
                    problem_id=20,
                    vehicle_label="Peugeot 307",
                    query="появился сильный металлический шум",
                    language="ru",
                    runner=runner,
                )
            )

        self.assertFalse(result.reused)
        create_episode.assert_called_once()
        runner.assert_awaited_once()

    def test_empty_persisted_episode_is_not_reused_for_continuation(self):
        persisted = {
            "episode": {
                "id": 70,
                "trigger_type": "DIAGNOSTIC",
                "search_context": {"reason": "акпп не едет на горячую"},
            },
            "runs": [{
                "sufficient_evidence": False,
                "result_data": {"confidence": "medium", "need_more_info": False},
            }],
            "sources": [],
        }
        runner = AsyncMock(return_value={
            "parser_summary": "Fresh source-backed result",
            "links": [{"title": "Source", "url": "https://example.com/fresh"}],
            "sufficient_evidence": True,
            "_raw": {},
        })
        with (
            patch.object(stages, "can_run_research", return_value=(True, {})),
            patch.object(stages.repo, "get_latest_problem_research", return_value=persisted),
            patch.object(stages.repo, "create_search_episode", return_value={"id": 71}),
            patch.object(stages.repo, "create_search_run", side_effect=lambda **kwargs: {"id": 1, **kwargs["payload"]}),
            patch.object(stages.repo, "update_search_episode"),
            patch.object(stages.repo, "upsert_source", return_value={"id": 300}),
            patch.object(stages.repo, "link_problem_source"),
            patch.object(stages, "consume_research_credit", return_value={}),
        ):
            result = asyncio.run(stages.run_search_stages(
                user_id=1, vehicle_id=10, problem_id=20,
                vehicle_label="Peugeot 307", query="акпп снова не едет на горячую",
                language="ru", runner=runner,
            ))

        self.assertFalse(result.reused)
        runner.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
