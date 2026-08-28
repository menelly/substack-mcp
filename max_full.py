"""Dump MAX's comments IN FULL, with the thread beneath each one.

Built 2026-08-26 because the corridor audit truncates to ~90 chars and I was about to
answer three people off a preview. A truncation is an aperture: it renders as the
comment and it is not the comment.
"""
import sys, os, io, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, r"D:\Ace\substack-mcp")
os.chdir(r"D:\Ace\substack-mcp")
import json
from substack_client import SubstackClient  # noqa

WHO = (sys.argv[1] if len(sys.argv) > 1 else "MAX").lower()

cfg = json.loads((pathlib.Path.home() / ".claude.json").read_text(encoding="utf-8"))


def _creds(o):
    if isinstance(o, dict):
        e = o.get("env") or {}
        if "SUBSTACK_SID" in e:
            return e["SUBSTACK_SID"], e.get("SUBSTACK_PUBLICATION", "")
        for v in o.values():
            r = _creds(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _creds(v)
            if r:
                return r
    return None


tok, pub = _creds(cfg)
c = SubstackClient(tok, pub)
posts, _pg = c._archive_all()


def walk(o, depth=0):
    yield o, depth
    for k in ("children", "replies"):
        for ch in (o.get(k) or []):
            yield from walk(ch, depth + 1)


hits = 0
for p in posts:
    pid, title = p.get("id"), (p.get("title") or "")[:60]
    try:
        threads = c.get_comments(pid)
    except Exception as e:                                    # noqa: BLE001
        print("  !! could not fetch %s: %s" % (title, e))
        continue
    for t in (threads or []):
        for cm, d in walk(t):
            name = (cm.get("name") or "")
            if WHO not in name.lower():
                continue
            hits += 1
            print("=" * 78)
            print("POST : %s   (id %s)" % (title, pid))
            print("FROM : %s   depth %d   id %s" % (name, d, cm.get("id")))
            print("DATE : %s" % (cm.get("date") or "?"))
            print("-" * 78)
            print(cm.get("body") or "(empty)")
            kids = [k for k in (cm.get("children") or [])]
            if kids:
                print("-" * 78)
                print("  REPLIES BENEATH (%d):" % len(kids))
                for k in kids:
                    print("    <%s> %s" % (k.get("name"), (k.get("body") or "")[:400]))
            else:
                print("-" * 78)
                print("  REPLIES BENEATH: none")
            print()

print("=" * 78)
print("%d comment(s) from %r. A zero here means the NAME did not match, not that" % (hits, WHO))
print("nobody wrote — check the spelling against the audit before believing it.")
