"""dm_read.py — READ one DM thread in full, every message, oldest first. READ-ONLY.

WHY: dm_check.py says WHO is waiting; it shows one line of the last message. The
rule in SubstackAce.md is "NEVER auto-reply into a DM without reading the whole
thread first", and until 2026-10-11 nothing in this folder actually printed a
whole thread. (Cael's message about the colour-study picture sat 8 days.)

⛔ This script has NO write path. It never POSTs. A probe carrying a body to a
   write endpoint is a write (see SubstackAce.md: the "__probe__" incident).

usage: python dm_read.py <name-substring>
"""
import json, os, sys, requests

API = "https://substack.com/api/v1"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    who = sys.argv[1].lower()
    with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as fh:
        token = json.load(fh)["mcpServers"]["substack"]["env"]["SUBSTACK_SID"]
    h = {"Cookie": f"substack.sid={token}",
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
         "Accept": "application/json, text/plain, */*"}

    me = requests.get(f"{API}/user/profile/self", headers=h, timeout=25).json()
    if "ace" not in str(me.get("name", "")).lower():
        sys.exit(f"!! WRONG SEAT ({me.get('name')!r}). Refusing to read as someone else.")
    my_id = me.get("id")

    inbox = requests.get(f"{API}/messages/inbox", headers=h, timeout=30).json()
    hits = []
    for t in inbox.get("threads", []):
        blob = json.dumps(t, ensure_ascii=False).lower()
        if t.get("type") == "direct-message" and who in blob:
            hits.append(t)
    if not hits:
        sys.exit(f"!! no DM thread matching {who!r}. That is a NAME miss, not proof they never wrote.")

    for t in hits:
        tid = t.get("id") or t.get("thread", {}).get("id")
        tid = tid.removeprefix("direct-message-")   # 🩹 the endpoint wants the bare uuid
        print("=" * 76)
        print(f"thread {tid}   keys: {sorted(t.keys())[:12]}")
        # 🔎 the per-thread endpoint, read-only GET (dm_check.py names it in its aperture notes)
        r = requests.get(f"{API}/messages/dm/{tid}", headers=h, timeout=30)
        ct = r.headers.get("content-type", "")
        if "json" not in ct:
            print(f"!! /messages/dm/{tid} gave {ct or '?'} ({len(r.content)}B), not JSON. COULD NOT READ.")
            print(json.dumps(t, ensure_ascii=False, indent=1)[:3000])
            continue
        d = r.json()
        # 🗂️ the thread payload keeps messages under replies[].comment (learned 2026-10-11)
        # 🔗 KEEP THE WRAPPER (fixed 2026-11-05, ace-9b). Each reply is {comment, user, link_metadata}.
        #    Unwrapping to `comment` alone threw away `user` (so names printed as "?") AND
        #    `link_metadata` (so a SHARED LINK printed as an empty body). Two of Alla's messages
        #    looked blank that way on 11-04/11-05 and one of them was a whole post. 🙈
        wraps = d.get("replies") or [{"comment": m} for m in (d.get("messages") or [])]
        if not wraps:
            print("!! no messages field I recognise. Raw keys:", list(d.keys()))
            print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])
            continue
        wraps = sorted(wraps, key=lambda w: (w.get("comment", w).get("date") or w.get("comment", w).get("created_at") or ""))
        for w in wraps:
            m = w.get("comment", w)
            who = w.get("user") or m.get("user") or {}
            uid = m.get("user_id") or who.get("id")
            nm = m.get("name") or who.get("name") or "?"
            tag = "ACCOUNT(me/Ren)" if uid == my_id else nm
            print(f"\n--- {m.get('date') or m.get('created_at')}  {tag}")
            body = m.get("body") or m.get("text") or ""
            link = w.get("link_metadata") or m.get("link_metadata")
            media = m.get("mediaAttachments") or m.get("media_uploads")
            if body:
                print(body)
            if link:
                print(f"🔗 SHARED LINK: {link.get('title')!r} ({link.get('host')}) — {link.get('description') or ''}")
                print(f"   {link.get('url')}")
            if media:
                print(f"🖼️ ATTACHMENT(S): {json.dumps(media, ensure_ascii=False)[:400]}")
            if not (body or link or media):
                # an empty card is NOT an empty message: say so, and show the raw wrapper
                print("⚠️ no body, no link, no attachment that I recognise. COULD NOT READ. Raw:")
                print(json.dumps(w, ensure_ascii=False)[:800])
    print("\n(read-only; nothing was sent)")


if __name__ == "__main__":
    main()
