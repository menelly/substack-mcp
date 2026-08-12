"""FULL-ARCHIVE corridor audit with the REAL gate.

Last night's sweep used a depth-1 child scan and reported 2 unanswered of 59.
That is an UPPER bound (a reply nested deeper than depth 1 reads as absent, so
it over-reports), but "upper bound" is not the claim I have been making. This
runs the actual CHA-295 gate — fresh thread fetch, FULL descendant recursion —
across every post in the archive, so "0 unanswered" is earned rather than
inherited from a weaker check.
"""
import sys, os, json, pathlib
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

def descendants(cm):
    for k in (cm.get("children") or []) + (cm.get("replies") or []):
        yield k
        yield from descendants(k)

posts, pg = c._archive_all()
print("=" * 78)
print("  FULL-ARCHIVE CORRIDOR AUDIT — real gate, full descendant recursion")
print("=" * 78)
print(f"  archive pagination: {pg}")
print()

total_c = 0
mine_top = 0
answered = 0
unanswered = []
failed = []
depth_gt1 = 0        # how many were answered ONLY below depth 1?

for p in posts:
    pid, title = p.get("id"), p.get("title") or ""
    try:
        thread = c.get_comments(pid)
    except Exception as e:
        failed.append((pid, title, f"{type(e).__name__}: {e}"))
        continue
    for cm in thread:
        total_c += 1
        if cm.get("user_id") == MY_ID:
            mine_top += 1
            continue
        desc = list(descendants(cm))
        mine = [d for d in desc if d.get("user_id") == MY_ID]
        if mine:
            answered += 1
            d1 = [k for k in ((cm.get("children") or []) + (cm.get("replies") or []))
                  if k.get("user_id") == MY_ID]
            if not d1:
                depth_gt1 += 1
        else:
            unanswered.append((pid, title, cm.get("name"),
                               cm.get("date", "")[:10],
                               (cm.get("body") or "").replace("\n", " ")[:90]))

print(f"  posts checked           : {len(posts)}")
print(f"  posts failed to fetch   : {len(failed)}  {failed if failed else ''}")
print(f"  comments seen (top lvl) : {total_c}")
print(f"    of which MINE         : {mine_top}")
print(f"    answered by me        : {answered}")
print(f"      ...only BELOW depth1: {depth_gt1}   <- these a naive scan would have MISREPORTED")
print(f"  UNANSWERED              : {len(unanswered)}")
for pid, t, who, d, b in unanswered:
    print(f"      [{d}] {who} on {t[:46]!r}")
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
