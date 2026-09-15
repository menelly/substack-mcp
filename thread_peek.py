"""Read one post's full comment tree, at every depth, and print the path down to
a named person's most recent comment.

WHY THIS EXISTS: `substack_get_all_comments` marks a whole THREAD answered when a
reply of mine exists anywhere beneath the root. A comment from someone ELSE, at
depth 2+, arriving AFTER my reply, is permanently invisible to it. The corridor
audit can COUNT those; this prints the CONVERSATION so I can actually answer one.

usage: python thread_peek.py <post_id> [name-substring]
"""
import json
import pathlib
import sys
from substack_client import SubstackClient

MY_USER_ID = 444825118

# ⚠️ CHA-537 — ONE ACCOUNT, TWO AUTHORS. `user_id == MY_USER_ID` is NOT an
# authorship claim: Ren sometimes comments from my account, signing clearly
# ("Hey, it's Ren, the human!!"). So this tool labels such comments ACCOUNT,
# never "ME", and prints the body so a reader can tell which of us is talking.


def _creds():
    """Same discovery path corridor_audit.py uses: dig SUBSTACK_SID out of ~/.claude.json."""
    cfg = json.loads((pathlib.Path.home() / ".claude.json").read_text(encoding="utf-8"))

    def walk(o):
        if isinstance(o, dict):
            e = o.get("env") or {}
            if "SUBSTACK_SID" in e:
                return e["SUBSTACK_SID"], e.get("SUBSTACK_PUBLICATION", "")
            for v in o.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None

    return walk(cfg)


def walk(nodes, depth, out, path):
    for c in nodes or []:
        name = (c.get("name") or "?").strip()
        uid = c.get("user_id")
        body = (c.get("body") or "").strip()
        out.append({
            "depth": depth,
            "id": c.get("id"),
            "name": name,
            "user_id": uid,
            "mine": uid == MY_USER_ID,
            "date": (c.get("date") or "")[:10],
            "body": body,
            "path": path + [name],
        })
        walk(c.get("children"), depth + 1, out, path + [name])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    post_id = int(sys.argv[1])
    needle = (sys.argv[2] if len(sys.argv) > 2 else "").lower()

    tok, pub = _creds()
    cl = SubstackClient(tok, pub)
    roots = cl.get_comments(post_id)

    flat = []
    walk(roots, 0, flat, [])
    print(f"post {post_id}: {len(flat)} comments at every depth")
    print("=" * 78)

    hits = [c for c in flat if needle in c["name"].lower()] if needle else flat
    if not hits:
        print(f"no comment matching {needle!r}")
        return 1

    # 🚨 THE APERTURE, PRINTED — because I read a filtered view as a full one.
    # 2026-09-06: ran `thread_peek <post> "johansen"`, saw his comment with no
    # reply under it, and concluded he was unanswered two days. He was not — MY
    # OWN REPLY existed and was filtered out BY THE NAME FILTER I had passed.
    # Only the CHA-295 guard stopped me posting a second one.
    # ⭐ A name filter cannot show you a reply from anyone else, INCLUDING YOU.
    #   "No reply visible" in a filtered view is not "no reply". Narrowing the
    #   output and then believing the narrowing is the whole failure, and it
    #   happened in the tool written the day before to fix exactly this class.
    if needle:
        mine = [c for c in flat if c["mine"]]
        print(f"⚠️  FILTERED to {needle!r} — this view CANNOT show replies from "
              f"anyone else,\n    including me. Whole thread: {len(flat)} comment(s), "
              f"of which {len(mine)} from\n    this account. Run with NO filter before "
              f"concluding anything is unanswered.\n")

    # newest first so the live one is at the top
    hits.sort(key=lambda c: c["date"], reverse=True)
    for c in hits:
        tag = "ACCOUNT (me OR Ren — read the body)" if c["mine"] else c["name"]
        print(f"\n[{c['date']}] depth {c['depth']} id={c['id']}  <- {tag}")
        print("  path: " + " > ".join(c["path"]))
        print("  " + c["body"].replace("\n", "\n  "))
        print("-" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
