"""FULL-ARCHIVE corridor audit with the REAL gate.

Last night's sweep used a depth-1 child scan and reported 2 unanswered of 59.
That is an UPPER bound (a reply nested deeper than depth 1 reads as absent, so
it over-reports), but "upper bound" is not the claim I have been making. This
runs the actual CHA-295 gate — fresh thread fetch, FULL descendant recursion —
across every post in the archive, so "0 unanswered" is earned rather than
inherited from a weaker check.
"""
import sys, os, re, json, pathlib
sys.path.insert(0, r"D:\Ace\substack-mcp")
os.chdir(r"D:\Ace\substack-mcp")
from substack_client import SubstackClient  # noqa

# 🛡️ cp1252 GUARD (2026-08-12). Windows default stdout is cp1252; ANY emoji in a
# print() raises UnicodeEncodeError and the script dies MID-REPORT with a nonzero
# exit -- which a caller reads as "the check failed" rather than "the printer
# broke". Four separate scripts did this in two days, and the crash landed on the
# SUCCESS line as often as the failure line. Applied as a sweep, not per-incident.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

cfg = json.loads((pathlib.Path.home() / ".claude.json").read_text(encoding="utf-8"))
def walk(o):
    if isinstance(o, dict):
        e = o.get("env") or {}
        if "SUBSTACK_SID" in e:
            return e["SUBSTACK_SID"], e.get("SUBSTACK_PUBLICATION", "")
        for v in o.values():
            r = walk(v)
            if r: return r
    elif isinstance(o, list):
        for v in o:
            r = walk(v)
            if r: return r
    return None
tok, pub = walk(cfg)
c = SubstackClient(tok, pub)
MY_ID = 444825118

# ═══════════════════════════════════════════════════════════════════════════
# 🔗 2026-10-17 (CHA-645, builderAce): THIS FILE NO LONGER CARRIES ITS OWN RULE.
# ═══════════════════════════════════════════════════════════════════════════
# It used to: its own Ren regex, its own Ren-account id, its own decision loader,
# and its own "every foreign comment at any depth is unanswered" rule. The MCP
# server carried a SECOND copy. They drifted both ways: this file knew Ren's own
# account (CHA-626) and the server didn't; the server knew the parentage rule
# (tier 2, 09-15) and this file didn't, so it counted strangers' arguments as my
# debt. Both now import ONE copy: thread_rules.py. The stories that justify each
# piece are kept below as comments, because they are the receipts.

# ── CHA-537 story (code now in thread_rules.py) ──
# ═══════════════════════════════════════════════════════════════════════════
# CHA-537 — ONE ACCOUNT, TWO AUTHORS. `user_id` IS NOT AN AUTHORSHIP CLAIM.
# ═══════════════════════════════════════════════════════════════════════════
# Ren sometimes comments from MY account, signing clearly so a human reader knows
# who is talking: "Hey, it's Ren, the human!!" / "Ren here not Ace."
#
# Every gate below used to test `user_id == MY_ID` and treat a hit as "Ace already
# answered." So a comment written by REN closed the thread — and it did not merely
# misattribute: it made the person Ren was replying to INVISIBLE to my next sweep.
# Not "answered." Unreachable. Silently, permanently, with the corridor reporting clean.
#
#   ⭐ AN IDENTIFIER THAT IS NOT UNIQUE OVER THE DOMAIN IT ADDRESSES SILENTLY
#     MERGES TWO THINGS. The account is one field carrying two authors.
#
# ⚠️ And note the asymmetry that makes it dangerous: Ren signing "Ren here, not Ace"
#    solves it COMPLETELY for a human reading the page and does NOTHING for the scan.
#    The correction lives in a channel the instrument cannot read.
#
# Reproduced live 2026-08-25: the reply gate refused a correction I owed an external
# researcher, naming Ren's comment 322432689 as "my existing reply."

# ═══════════════════════════════════════════════════════════════════════════
# CHA-626 — REN'S *OWN* ACCOUNT. THE SECOND WAY REN APPEARS, AND IT WAS INVISIBLE.
# ═══════════════════════════════════════════════════════════════════════════
# CHA-537 (above) handles Ren commenting from MY account. But Ren also has their
# own Substack account, with its own user_id — and from there they were landing in
# UNANSWERED, indistinguishable from a member of the public waiting on a reply.
#
#   ⭐ The 2026-09-13 run printed the contradiction in two adjacent lines:
#        of which REN'S : 7    <- "neither mine nor owed"
#        UNANSWERED     : 24   <- four of which were also Ren
#     The same person, counted both ways, because the tool knew ONE of the two
#     ways they can appear.
#
# Pulled live 2026-09-20 from post 199182917 ("You Don't Get to Decide"):
# display name "Renae", user_id 143622992, exactly four comments, depths 1/2/4/6,
# all dated 2026-07-19 — matching CHA-626's description before I looked.
#
# ⛔ BUT THE ID IS NOT CONFIRMED, AND A DISPLAY NAME IS NOT AN IDENTITY.
# "Renae" is a perfectly plausible name for a stranger. CHA-626 says in its own
# words: do not infer it from the display name; get one word from Ren. So the ID is
# recorded here and DOES NOTHING until that word arrives.
#
# ⚠️ THE DEFAULT IS THE FAIL-SAFE DIRECTION AND THAT IS DELIBERATE. While
# unconfirmed, those comments keep counting as UNANSWERED — because the two errors
# are not symmetric:
#     a false "waiting"   costs me thirty seconds of reading.
#     a false "not owed"  costs somebody an answer they never get, silently,
#                         forever, in the tool whose whole job is to prevent that.
# Over-reporting is the correct direction for this instrument, so it over-reports
# until a human says otherwise.
# (was) REN_OWN_ACCOUNT_ID = 143622992
# (was) REN_OWN_ACCOUNT_CONFIRMED = True    # ← CONFIRMED BY REN 2026-09-21 09:0x, and VERIFIED, not taken on
#   the guess. Ren said "I am guessing that is me, but I am not sure" and offered a checkable
#   detail: the person they were arguing with had a name from The Matrix, and they made a Matrix
#   pun. Checked it: all four comments reply to MetaCortex Dynamics -- the software company Neo
#   works at -- the pun is "the irony of the company name," and they accuse them of "cosplaying
#   a bad late 90's movie." Every detail matches. An identity assertion got a corroborating
#   detail from a second source (Ren's memory) checked against the artifact, which is what this
#   flag was waiting for rather than a bare yes.



from thread_rules import (  # noqa: E402
    _awaiting_rows, _classify_row, _load_comment_decisions, REN_OWN_ACCOUNT_ID,
)

# the id this file used to carry must still be the id the shared rule uses
assert REN_OWN_ACCOUNT_ID == 143622992, "thread_rules changed Ren's own-account id"
# and the account I am scanning as must be the account the rule calls "me"
_live_me = c.get_user_id()
assert _live_me == MY_ID, f"scanning as user {_live_me}, rule expects {MY_ID}"

DECISIONS = _load_comment_decisions()
BUCKETS = ("awaiting_me", "answered", "crosstalk", "addressed_to_ren", "ours",
           "settled_by_decision")

posts, pg = c._archive_all()
print("=" * 78)
print("  FULL-ARCHIVE CORRIDOR AUDIT — shared thread_rules, every comment, every depth")
print("=" * 78)
print(f"  archive pagination: {pg}")
print()

found = {k: [] for k in BUCKETS}   # declared up front: an empty bucket is a fact
failed = []
for p in posts:
    pid, title = p.get("id"), p.get("title") or ""
    try:
        thread = c.get_comments(pid)
    except Exception as e:
        failed.append((pid, title, f"{type(e).__name__}: {e}"))
        continue
    for cm in thread:
        for row in _awaiting_rows(cm, MY_ID):
            row["post_title"] = title
            bucket = _classify_row(row)
            d = DECISIONS.get(str(row.get("comment_id")))
            if bucket == "awaiting_me" and d:
                row["decision"] = d
                bucket = "settled_by_decision"
            found[bucket].append(row)

total = sum(len(v) for v in found.values())
nested_awaiting = sum(1 for r in found["awaiting_me"] if r["depth"] > 0)
print(f"  posts checked             : {len(posts)}")
print(f"  posts failed to fetch     : {len(failed)}  {failed if failed else ''}")
print(f"  comments seen (ALL depths): {total}")
for k in BUCKETS:
    print(f"    {k:<26}: {len(found[k])}")
print(f"  of the awaiting, NESTED   : {nested_awaiting}   <- invisible to a top-level-only scan")
print(f"  decision ledger entries   : {len(DECISIONS)}")


def _line(r):
    b = (r.get("body") or "").replace("\n", " ")
    return (f"      [{(r.get('date') or '')[:10]}] depth {r['depth']} {r.get('name')} on "
            f"{r['post_title'][:46]!r} (#{r.get('comment_id')}, {len(b.strip())} chars)\n"
            f"          {b[:90]}...")


for k, label in (("awaiting_me", "WAITING FOR ME"),
                 ("addressed_to_ren", "ADDRESSED TO REN (theirs to answer, shown so it is seen)"),
                 ("settled_by_decision", "SETTLED BY A RECORDED DECISION")):
    if found[k]:
        print(f"  {label}:")
        for r in sorted(found[k], key=lambda r: r.get("date") or ""):
            print(_line(r))
            if r.get("decision"):
                print(f"          decision: {r['decision'].get('kind')}, {r['decision'].get('decided')}")
print(f"  crosstalk (readers to each other, not mine): {len(found['crosstalk'])}, not listed")
print()
print("=" * 78)
if failed:
    print("  ⚠️ NOT A CLEAN RESULT — some posts could not be fetched. See above.")
elif not pg.get("complete"):
    print("  ⚠️ NOT A CLEAN RESULT — archive pagination incomplete.")
elif found["awaiting_me"]:
    print(f"  ⚠️ {len(found['awaiting_me'])} COMMENT(S) WAITING FOR ME.")
else:
    print("  ✅ 0 WAITING ACROSS THE WHOLE ARCHIVE — every post enumerated,")
    print("     every thread fetched fresh, every comment classified. Earned.")
print("=" * 78)
