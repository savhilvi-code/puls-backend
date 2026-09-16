import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from contextlib import ExitStack
from app.services import conversation_orchestrator as chat
from app.services import v2_repository as repo
from tests.test_v2_repository import FakeClient, FakeQuery, USER_ID, VEHICLE_ID

CONV = "55555555-5555-4555-8555-555555555555"

class ChatStabilizationTests(unittest.TestCase):
    def run_turn(self, hours):
        rows=[{"role":"USER","content":"hello","created_at":(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()}]
        with ExitStack() as stack:
            stack.enter_context(patch.object(chat,"get_or_create_profile",AsyncMock(return_value=SimpleNamespace(id=USER_ID))))
            stack.enter_context(patch.object(chat,"ensure_user_subscription",return_value=None))
            stack.enter_context(patch.object(chat,"quota_payload",return_value={}))
            stack.enter_context(patch.object(repo,"recent_conversation_messages",return_value=rows))
            stack.enter_context(patch.object(chat,"_latest_problem_for_context",return_value=None))
            stack.enter_context(patch.object(repo,"list_user_vehicles",return_value=[]))
            stack.enter_context(patch.object(chat,"resolve_relevant_problem",return_value=None))
            create=stack.enter_context(patch.object(repo,"get_or_create_conversation",return_value={"id":CONV,"vehicle_id":None,"problem_id":None}))
            save=stack.enter_context(patch.object(repo,"save_message"))
            reply=stack.enter_context(patch.object(chat,"_natural_reply",AsyncMock(return_value="Hello")))
            result=asyncio.run(chat.process_chat_message_v2({"message":"hello","conversation_id":CONV}))
            self.assertEqual(result.conversation_id,CONV)
            self.assertEqual(save.call_count,2)
            return create.call_args.kwargs['conversation_id'], reply.call_args.kwargs['recent_messages']

    def test_current_conversation_reuses_identity_and_context(self):
        identity,rows=self.run_turn(1)
        self.assertEqual(identity,CONV)
        self.assertTrue(rows)

    def test_expired_conversation_is_not_reused_or_deleted(self):
        identity,rows=self.run_turn(12)
        self.assertIsNone(identity)
        self.assertEqual(rows,[])

    def test_history_requires_conversation_ownership(self):
        class Client(FakeClient):
            def table(self,name):
                q=FakeQuery(name,data=[])
                self.queries.append(q)
                return q
        client=Client()
        with patch.object(repo,'get_supabase_client',return_value=client):
            self.assertEqual(repo.recent_conversation_messages(user_id=USER_ID,conversation_id=CONV),[])
        self.assertEqual(len(client.queries),1)
        self.assertIn(('eq','user_id',USER_ID),client.queries[0].calls)

if __name__=='__main__': unittest.main()
