"""🍪 The publish-needs-a-fresh-sign-in case (2026-10-08, heartbeat arm).

Substack started answering publish with a 403 "reauthentication_required" while the same
cookie could still read and draft. The raw error sent me rediscovering a recipe I'd already
written. This test makes sure the tool now SAYS what happened, keeps the draft id, and points
at the fix, and that any OTHER publish error still bubbles up untouched (so I didn't just
build a place for real errors to hide).
"""
import asyncio
import json
import unittest

import importlib

# the package exports a `server` OBJECT that shadows the submodule name, so go via importlib
srv = importlib.import_module("substack_mcp.server")


class _FakeClient:
    def __init__(self, err):
        self.err = err

    def publish_draft(self, draft_id, send_email=False):
        raise Exception(self.err)


def _run(name, args):
    out = asyncio.run(srv._call_tool_impl(name, args))
    return json.loads(out[-1].text)


class TestPublishReauth(unittest.TestCase):
    def setUp(self):
        self._saved = srv.client

    def tearDown(self):
        srv.client = self._saved

    def test_reauth_403_explains_itself_and_keeps_the_draft(self):
        # the exact shape of the error that came back on 2026-10-08
        srv.client = _FakeClient('403 on POST /drafts/219439681/publish -- server said: '
                                 '{"error":"For your security, please sign out and sign back in to do this.",'
                                 '"type":"reauthentication_required"}')
        r = _run("substack_publish", {"draft_id": 219439681, "send_email": True})
        self.assertFalse(r["success"])
        self.assertIn("reauthentication_required", r["error"])
        self.assertEqual(r["draft_id"], 219439681)
        self.assertTrue(r["publish_by_hand"].endswith("/publish/post/219439681"))
        self.assertIn("reference_substack_mcp.md", r["fix"])

    def test_any_other_publish_error_is_NOT_dressed_up(self):
        # positive control in the other direction: a different failure must not get the reauth story
        srv.client = _FakeClient("500 on POST /drafts/1/publish -- server exploded")
        r = _run("substack_publish", {"draft_id": 1})
        self.assertNotIn("publish_by_hand", r)
        self.assertIn("500", json.dumps(r))


if __name__ == "__main__":
    unittest.main()
