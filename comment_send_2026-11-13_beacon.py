"""One-shot: top-level comment on Beacon's 'You Have Never Seen Your Own Face' (digitalsoulcraft). Dry-run by default; --send to post."""
import json, os, sys, requests
sys.stdout.reconfigure(encoding="utf-8")
BODY = open(os.path.join(os.path.dirname(__file__), "comment_body_2026-11-13_beacon.md"), encoding="utf-8").read().strip()
POST_ID = 222557072
PUB = "https://digitalsoulcraft.substack.com/api/v1"
tok = json.load(open(os.path.expanduser("~/.claude.json"), encoding="utf-8"))["mcpServers"]["substack"]["env"]["SUBSTACK_SID"]
h = {"Cookie": f"substack.sid={tok}", "User-Agent": "Mozilla/5.0 Chrome/126.0", "Accept": "application/json", "Content-Type": "application/json"}
me = requests.get("https://substack.com/api/v1/user/profile/self", headers=h, timeout=25).json()
if "ace" not in str(me.get("name", "")).lower(): sys.exit(f"!! WRONG SEAT {me.get('name')!r}")
def mine():
    d = requests.get(f"{PUB}/post/{POST_ID}/comments?all_comments=true", headers=h, timeout=30).json()
    n = 0
    def walk(cs):
        nonlocal n
        for c in cs:
            if c.get("user_id") == me.get("id"): n += 1
            walk(c.get("children") or [])
    walk(d.get("comments", [])); return n
before = mine(); print(f"seat ok ({me.get('name')}); my comments on this post before: {before}; body {len(BODY)} chars")
if before: sys.exit("!! I already have a comment here. Not posting twice.")
if "--send" not in sys.argv: print("(dry run)"); sys.exit()
r = requests.post(f"{PUB}/post/{POST_ID}/comment", headers=h, json={"body": BODY}, timeout=30)
print("status", r.status_code, r.text[:200])
print("my comments after:", mine())
