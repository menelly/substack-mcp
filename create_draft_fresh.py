#!/usr/bin/env python3
"""create_draft_fresh.py — create ONE Substack draft from a markdown body file, reading the cookie FRESH.

Why: the MCP server reads SUBSTACK_SID once at launch, so a long-running session can hold a dead cookie and answer
403 on POST /drafts while the cookie on disk is fine. This reads it at run time. It never prints the cookie.
Publishing still goes through Ace's Chrome profile (see publish_once.py); this only makes the draft.
Run Un-Toaster on the body file first. (Ace, heartbeat arm, 2026-10-24)

usage: python create_draft_fresh.py "<title>" "<subtitle>" <body.md>
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from substack_client import SubstackClient  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

title, subtitle, body_path = sys.argv[1], sys.argv[2], sys.argv[3]
body = open(body_path, encoding="utf-8").read()
env = json.load(open(os.path.expanduser("~/.claude.json"), encoding="utf-8"))["mcpServers"]["substack"]["env"]
c = SubstackClient(env["SUBSTACK_SID"], env.get("SUBSTACK_PUBLICATION", ""))
d = c.create_draft(title=title, body=body, subtitle=subtitle, audience="everyone")
print("draft id:", getattr(d, "id", None) or (d.get("id") if isinstance(d, dict) else d))
