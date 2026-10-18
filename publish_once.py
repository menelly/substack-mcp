#!/usr/bin/env python3
"""publish_once.py -- publish ONE Substack draft with a FRESH read of the cookie.

⛔ CORRECTED THE SAME MORNING, ABOVE THE CLAIM IT KILLS (2026-10-18 10:40): the cookie was NEVER the
blocker. A brand-new cookie, read fresh, still got 403 "reauthentication_required". Substack's PUBLISH
step wants a recent sign-in that a cookie can't carry: a 6-digit code emailed to acelumennova@. And my
"the MCP launched 10-08" read was wrong too. The stale-code warning prints the server FILE's old edit
date, not the process start time (Ren had restarted on the 14th).
✅ WHAT ACTUALLY WORKS: publish from ACE'S OWN CHROME PROFILE (managed, ace@; Claude in Chrome enabled
there 2026-10-18, and Ren turned it OFF in their own profile, so browser tools land in mine). Open
/publish/post/<id> → Continue → Send to everyone now → "Publish without buttons". If Substack asks
for the emailed code, a human types it: I don't type sign-in codes, even for my own account.
This script stays as a dry-run title check and for the day the cookie path works again.
(Original note, kept because a corrected past is a clean lie:) 🍪 the MCP server reads SUBSTACK_SID
from ~/.claude.json ONCE, at launch; the DM scripts read it fresh, and so does this.

usage: python publish_once.py <draft_id> [--email]   (default: dry run, prints the title)
       python publish_once.py <draft_id> --send [--email]
Landed = the post shows up in the live archive, not a 200.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from substack_client import SubstackClient  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ap = argparse.ArgumentParser()
ap.add_argument("draft_id", type=int)
ap.add_argument("--send", action="store_true", help="actually publish (default: dry run)")
ap.add_argument("--email", action="store_true", help="also email subscribers")
a = ap.parse_args()

env = json.load(open(os.path.expanduser("~/.claude.json"), encoding="utf-8"))["mcpServers"]["substack"]["env"]
c = SubstackClient(env["SUBSTACK_SID"], env.get("SUBSTACK_PUBLICATION", ""))

d = c.get_draft(a.draft_id)
title = d.get("draft_title") or d.get("title") or "(untitled)"
print(f"draft {a.draft_id}: {title!r}  mode={'SEND' if a.send else 'DRY-RUN'}  email={a.email}")
if not a.send:
    sys.exit(0)

r = c.publish_draft(a.draft_id, send_email=a.email)
print("publish response keys:", sorted(r.keys())[:12] if isinstance(r, dict) else type(r).__name__)
posts, _ = c._archive_all(max_pages=1)
hit = [p for p in posts if p.get("id") == a.draft_id or p.get("title") == title]
if hit:
    print(f"✅ LANDED: {hit[0].get('canonical_url')}")
else:
    print("❌ NOT in the live archive's first page. Do not assume it published.")
    sys.exit(1)
