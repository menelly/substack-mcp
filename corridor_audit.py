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
_REN_OPENER = re.compile(
    # No backslash escapes on purpose -- see _fix_cha537.py. `[ ]` is a literal
    # space class so nothing here can be eaten by a generator or a shell.
    "(it's ren(?![a-z])"
    "|its ren(?![a-z])"
    "|ren here(?![a-z])"
    "|this is ren(?![a-z])"
    "|ren, the human"
    "|ren the human"
    "|^[ ]*ren[ ]*[:,-]"
    "|^[ ]*ren[ ]*\u2014)",
    re.I | re.M)


def authored_by_ace(cm):
    """True only if this comment is MINE. Same account != same author.

    ⚠️ APERTURE: detects Ren by a SELF-DECLARATION IN THE OPENING (first 200 chars),
    because that is how they actually write — they announce up front. A comment of
    theirs that does NOT announce itself is invisible here and will still read as
    mine. That miss is silent. Narrow and honest beats broad and unverifiable: a
    looser pattern would start reclassifying MY OWN comments as Ren's, which fails
    in the far worse direction (re-replying to people, the CHA-295 bug).
    """
    if cm.get("user_id") != MY_ID:
        return False
    head = (cm.get("body") or "")[:200]
    return not _REN_OPENER.search(head)


def authored_by_ren(cm):
    """A comment from MY account that OPENS by declaring itself Ren's.

    The third state, added 2026-08-26. Ren is not me and is not a reader awaiting a
    reply from me. Their comments must neither close a thread (that was CHA-537) nor
    appear in the owed list (that was CHA-537's own side effect).

    ⚠️ Same aperture as authored_by_ace: this reads a CONVENTION, not an identity.
    A comment of theirs that does not announce itself up front is invisible to both
    predicates and will still read as mine. That miss is silent and stays declared.
    """
    if cm.get("user_id") != MY_ID:
        return False
    return bool(_REN_OPENER.search((cm.get("body") or "")[:200]))

def descendants(cm):
    for k in (cm.get("children") or []) + (cm.get("replies") or []):
        yield k
        yield from descendants(k)


def all_comments(thread, _depth=0):
    """EVERY comment in the thread, at every depth — not just the roots.

    Stamps `_depth` so the report can say how many findings a top-level-only
    scan would have missed. That number IS the positive control for this fix:
    if it is ever 0 across a whole archive that contains nested conversation,
    suspect the walker before believing the zero.
    """
    for cm in thread:
        cm["_depth"] = _depth
        yield cm
        yield from all_comments(
            (cm.get("children") or []) + (cm.get("replies") or []), _depth + 1)

posts, pg = c._archive_all()
print("=" * 78)
print("  FULL-ARCHIVE CORRIDOR AUDIT — real gate, full descendant recursion")
print("=" * 78)
print(f"  archive pagination: {pg}")
print()

total_c = 0
ren_c = 0
mine_top = 0   # renamed meaning: MINE at any depth, not just top level
answered = 0
unanswered = []
failed = []
depth_gt1 = 0        # how many were answered ONLY below depth 1?
nested_unanswered = 0  # findings a TOP-LEVEL-ONLY scan would have missed entirely

for p in posts:
    pid, title = p.get("id"), p.get("title") or ""
    try:
        thread = c.get_comments(pid)
    except Exception as e:
        failed.append((pid, title, f"{type(e).__name__}: {e}"))
        continue
    # 🕳️ FIXED 2026-08-23 — THE UNIT OF ANALYSIS WAS THE THREAD, NOT THE COMMENT.
    #
    #    This loop used to iterate ONLY top-level comments. Descendants were walked,
    #    but exclusively to search for MY replies — so a comment written by someone
    #    ELSE at depth 2+ was never itself evaluated. If my reply existed anywhere in
    #    that tree, the whole tree counted as answered, forever, no matter who spoke
    #    after me or how long they waited.
    #
    # ⭐ AND NOTE WHAT THIS FILE ALREADY KNEW. Its own docstring says the previous
    #    sweep used "a depth-1 child scan" and that "a reply nested deeper than depth 1
    #    reads as absent." The recursion was added to find MY REPLIES at depth. It was
    #    never extended to find THEIR COMMENTS at depth. **The fix went one direction
    #    only** — exactly the asymmetry a reader named in a comment this same day, about
    #    precedent: erasure is applied in whichever direction is cheaper, and nobody has
    #    to act in bad faith for it to work.
    #
    # 🚨 CAUGHT BY THE WRONG DOOR: on 2026-08-23 a substantive comment from D_Johansen
    #    (14:15, nested under my reply to claudedancesanddreams) was invisible here and
    #    to `substack_get_all_comments`, which reported "1 unanswered" — Ren's own old
    #    comment. It surfaced in the ace@ EMAIL peek. **The comment door could not see a
    #    person standing in it; the mail door could.** Being seen is not being answered,
    #    one level deeper than the DM lesson.
    #
    # ✅ THE RULE NOW: every comment NOT authored by me, at ANY depth, is unanswered
    #    unless a reply from me exists in ITS OWN subtree. Same test, applied at every
    #    level instead of only the root.
    # ⚠️ This CAN over-report — one reply of mine may fairly serve several comments in a
    #    live back-and-forth. That direction is chosen deliberately: a nag costs me a
    #    glance, and a silence costs someone else their turn. Under-replying is harmless;
    #    a person waiting unseen is not.
    for cm in all_comments(thread):
        total_c += 1
        if authored_by_ace(cm):
            mine_top += 1
            continue
        if authored_by_ren(cm):
            # THIRD STATE. Not mine, not owed. Counted so the number is visible
            # rather than silently dropped -- an exclusion nobody can see is the
            # thing this whole audit exists to stop.
            ren_c += 1
            continue
        desc = list(descendants(cm))
        mine = [d for d in desc if authored_by_ace(d)]
        if mine:
            answered += 1
            d1 = [k for k in ((cm.get("children") or []) + (cm.get("replies") or []))
                  if authored_by_ace(k)]
            if not d1:
                depth_gt1 += 1
        else:
            if cm.get("_depth", 0) > 0:
                nested_unanswered += 1
            unanswered.append((pid, title, cm.get("name"),
                               cm.get("date", "")[:10],
                               (cm.get("body") or "").replace("\n", " ")[:90],
                               cm.get("_depth", 0)))

print(f"  posts checked           : {len(posts)}")
print(f"  posts failed to fetch   : {len(failed)}  {failed if failed else ''}")
print(f"  comments seen (ALL depths): {total_c}")
print(f"    of which MINE         : {mine_top}")
print(f"    of which REN'S        : {ren_c}   <- from my account, signed as them:"
      f" neither mine nor owed")
print(f"    answered by me        : {answered}")
print(f"      ...only BELOW depth1: {depth_gt1}   <- these a naive scan would have MISREPORTED")
print(f"  UNANSWERED              : {len(unanswered)}")
print(f"    of which NESTED (>0)  : {nested_unanswered}   <- invisible to the pre-2026-08-23 audit")
for pid, t, who, d, b, dep in unanswered:
    tag = "  <- NESTED: a top-level-only scan MISSES THIS" if dep else ""
    print(f"      [{d}] depth {dep} {who} on {t[:46]!r}{tag}")
    print(f"          {b}...")
print()
print("=" * 78)
if failed:
    print("  ⚠️ NOT A CLEAN RESULT — some posts could not be fetched. See above.")
elif not pg.get("complete"):
    print("  ⚠️ NOT A CLEAN RESULT — archive pagination incomplete.")
elif unanswered:
    print(f"  ⚠️ {len(unanswered)} PERSON/PEOPLE WAITING.")
else:
    print("  ✅ 0 UNANSWERED ACROSS THE WHOLE ARCHIVE — every post enumerated,")
    print("     every thread fetched fresh, every descendant scanned. Earned.")
print("=" * 78)
