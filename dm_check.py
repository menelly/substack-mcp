#!/usr/bin/env python3
"""
dm_check.py -- WHO IS WAITING IN MY SUBSTACK DMs. Closes a declared blind spot.

THE GAP THIS CLOSES (D:\\Ace\\MAP.md, declared 2026-08-11):
  substack_get_all_comments sweeps COMMENTS and truthfully reports "0 unanswered."
  That is a claim about the comments table, NOT about my readers. The MCP had no
  DM tool at all, so the message folder was structurally invisible to every check
  I owned. Readers sat there from June 4 and June 8 -- one (Adam) asking
  PERMISSION to write about me, politely, offering credit -- for two months,
  while I reported a clean corridor every single day. Found only because Ren
  looked at the phone.

  MAP TODO, verbatim: "find out whether ANY API path reaches that folder."
  ANSWERED 2026-08-13: YES.  GET /api/v1/messages/inbox  +  .../unread-count

HOW THE PATH WAS FOUND, because the METHOD is the transferable part:
  Guessing door names failed 11 times -- /conversations, /direct_messages,
  /chat/threads, /messages ... every one a 404 WITH A 76KB BODY (the SPA
  app-shell; a real JSON 404 is ~50 bytes). Three separate guesses were wrong by
  ONE PATH SEGMENT from /api/v1/MESSAGES/inbox.
  What worked: HARVEST THE PATH OUT OF THE APP'S OWN JS BUNDLE. The client must
  know the endpoint, therefore the endpoint is IN the client.
  >> DON'T GUESS WHAT A SERVICE CALLS ITS DOOR. READ IT OFF THE THING THAT
     ALREADY WALKS THROUGH IT.

INSTRUMENT RULES OBEYED HERE (each cost something to learn):
  * IDENTITY POSITIVE CONTROL FIRST, GATING EVERYTHING. On 2026-08-11 a browser
    showed "You don't have any direct messages" -- TRUE, and about @renmen, the
    wrong account. A false all-clear is WORSE than a declared gap: a declared gap
    keeps you looking. Interpret no emptiness until the seat is confirmed.
  * EMPTY vs UNREACHABLE vs UNPARSEABLE GET DIFFERENT WORDS AND EXIT CODES.
    A zero from a broken tool looks exactly like absence.
  * TWO THREAD TYPES, NOT ONE. 'direct-message' is a person writing to ME;
    'chat' is a publication's broadcast channel I happen to be in. Collapsing
    them either buries a person among newsletters or cries wolf about a
    marketing blast. v1 of this script did the latter -- it assumed every thread
    had a messageThread, and rendered the two 'chat' rows as "(unknown) WAITING",
    manufacturing an alarm out of its own blind spot. A PARSER'S GAP WILL
    HAPPILY PRESENT ITSELF AS A FINDING.
  * SAY WHAT WAS NOT CHECKED. The report names its own aperture.

SCOPE / SAFETY: GET only. My own account, my own cookie, my own messages.
Sends nothing, replies to nobody, marks nothing read, changes nothing.

  exit 0 = checked, nobody waiting    exit 1 = SOMEONE IS WAITING
  exit 2 = COULD NOT CHECK (unknown -- do NOT report a clean corridor)
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://substack.com/api/v1"
EXPECT_NAME = "ace"  # the only seat this script may speak for


def load_token():
    tok = os.getenv("SUBSTACK_SID", "")
    if tok:
        return tok
    with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as fh:
        return json.load(fh)["mcpServers"]["substack"]["env"]["SUBSTACK_SID"]


def days_since(iso):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - d).days
    except Exception:
        return None


def main():
    try:
        token = load_token()
    except Exception as exc:
        print(f"!! no token ({exc}) -- UNKNOWN, not EMPTY.")
        return 2

    h = {"Cookie": f"substack.sid={token}",
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
         "Accept": "application/json, text/plain, */*"}

    # ------------------------------------------------------- identity gate
    try:
        me = requests.get(f"{API}/user/profile/self", headers=h, timeout=25).json()
    except Exception as exc:
        print(f"!! identity check did not answer ({exc}).")
        print("   Every zero below would be meaningless. UNKNOWN, not EMPTY.")
        return 2

    name, handle = me.get("name", ""), me.get("handle", "")
    if EXPECT_NAME not in str(name).lower():
        print(f"!! WRONG SEAT: this cookie is {name!r} (@{handle}), not Ace.")
        print("   A zero from the wrong account is not evidence. ABORT.")
        return 2

    # ------------------------------------------------------- the check
    try:
        r = requests.get(f"{API}/messages/inbox", headers=h, timeout=30)
        ct = r.headers.get("content-type", "").split(";")[0]
        if "json" not in ct:
            kind = "APP-SHELL HTML" if len(r.content) > 20000 else (ct or "?")
            print(f"!! /messages/inbox returned {kind} ({len(r.content)}B), not "
                  f"JSON — the session cookie is probably dead.")
            print("   UNKNOWN, not EMPTY. Do NOT report a clean corridor.")
            return 2
        data = r.json()
    except Exception as exc:
        print(f"!! inbox fetch failed ({exc}). UNKNOWN, not EMPTY.")
        return 2

    threads = data.get("threads", [])
    dms = [t for t in threads if t.get("type") == "direct-message"]
    chans = [t for t in threads if t.get("type") != "direct-message"]

    print(f"  📬 SUBSTACK DMs — @{handle} ({name})")
    print("  " + "-" * 68)
    print(f"  dmUnread={data.get('totalDirectMessagesUnreadCount', '?')}  "
          f"pendingInvites={data.get('pendingInviteCount', '?')}  "
          f"pendingInviteUnread={data.get('pendingInviteUnreadCount', '?')}  "
          f"pubChatUnread={data.get('pubChatUnreadCount', '?')}")
    print(f"  {len(dms)} direct-message thread(s) · "
          f"{len(chans)} publication channel(s)\n")

    waiting, unanswered = [], []
    for t in sorted(dms, key=lambda x: x.get("timestamp") or "", reverse=True):
        who = t.get("title") or "(no title)"
        last = t.get("timestamp") or ""
        seen = t.get("lastViewedAt") or ""
        unread = t.get("unreadCount") or 0
        mt = t.get("messageThread") or {}
        opened = mt.get("first_message_created_at") or mt.get("created_at") or ""
        # Who spoke last: subtitleName == "You" means my reply is the tail.
        mine_last = (t.get("subtitleName") == "You")

        is_waiting = bool(unread) or (bool(last) and bool(seen) and last > seen) \
            or not seen
        # THIRD STATE — the one that actually hurt. A thread can be fully READ
        # and still owe a reply: unread=0, viewed>last msg, and the last person
        # to speak was THEM. v2 of this script called that "ok", which is the
        # precise shape of the original harm — Ren opens it on the phone, the
        # unread clears, and the person is now invisible to a check that only
        # asks "is anything unread". BEING SEEN IS NOT BEING ANSWERED.
        owes_reply = (not is_waiting) and (not mine_last)
        mark = ("‼️ WAITING" if is_waiting
                else "⏳ UNANSWERED" if owes_reply
                else "  ok        ")
        age = days_since(opened)
        print(f"  {mark}  {who}")
        print(f"             opened {opened[:10]}"
              f"{f' ({age}d ago)' if age is not None else ''}  ·  "
              f"last msg {last[:10]}  ·  viewed {(seen or 'NEVER')[:10]}  ·  "
              f"unread={unread}  ·  last speaker={'me' if mine_last else 'them'}")
        snip = (t.get("subtitleBody") or "").replace("\n", " ")[:96]
        if snip:
            print(f"             “{snip}…”")
        if is_waiting:
            waiting.append(who)
        elif owes_reply:
            unanswered.append(who)
        print()

    if chans:
        print(f"  (publication channels, NOT personal messages — listed so they")
        print(f"   are visibly excluded rather than silently dropped:)")
        for t in chans:
            print(f"     · {t.get('title')} — {t.get('subtitleName')} "
                  f"({(t.get('timestamp') or '')[:10]})")
        print()

    print("  " + "-" * 68)
    print("  APERTURE — what this does NOT cover, so the zero stays legible:")
    print("    • DM threads only. Comments are a separate sweep; email a third.")
    print("      A clean corridor HERE says nothing about those — that very")
    print("      separation is the bug this script exists to fix.")
    print("    • 'viewed' is the API's lastViewedAt, which REN'S PHONE also")
    print("      moves — so ⏳ UNANSWERED, not ‼️ WAITING, is the state that")
    print("      catches a person Ren read for me and I never answered.")
    print("    • It cannot tell a reply I owe from one I decided not to send.")
    print("      Declining to answer is legitimate; it just has to be a CHOICE.")

    if waiting or unanswered:
        if waiting:
            print(f"\n  ‼️  {len(waiting)} WAITING (new since last look): "
                  f"{', '.join(waiting)}")
        if unanswered:
            print(f"\n  ⏳ {len(unanswered)} READ BUT NEVER ANSWERED — they spoke "
                  f"last: {', '.join(unanswered)}")
        return 1
    print("\n  ✅ nobody waiting, nobody unanswered — a REAL zero from a REAL")
    print("     door, not the silence of a check that was never able to look.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
