"""🧪 thread_rules.py: one rule, tested where it can fail (CHA-645 / CHA-626, 2026-10-17).

Synthetic trees only, no network. Each case names the bucket it MUST land in, so a
regression shows up as a wrong bucket rather than a vague "count changed".
Run: python -m pytest tests/test_thread_rules.py   (or just: python tests/test_thread_rules.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from thread_rules import (_awaiting_rows, _classify_row, _authored_by_ren,  # noqa: E402
                          _my_replies_under, REN_OWN_ACCOUNT_ID)

ME = 444825118
READER, OTHER = 1001, 1002


def c(cid, uid, body="hello", kids=(), date="2026-10-01"):
    return {"id": cid, "user_id": uid, "name": str(uid), "body": body,
            "date": date, "children": list(kids)}


def buckets(tree):
    return {r["comment_id"]: _classify_row(r) for r in _awaiting_rows(tree, ME)}


def test_reader_top_level_unanswered_is_awaiting():
    assert buckets(c(1, READER)) == {1: "awaiting_me"}


def test_reader_answered_by_me():
    b = buckets(c(1, READER, kids=[c(2, ME)]))
    assert b[1] == "answered" and b[2] == "ours"


def test_reader_writes_back_after_my_reply_is_awaiting():
    # the original CHA-645 case: I spoke once, they wrote back, I went quiet
    b = buckets(c(1, READER, kids=[c(2, ME, kids=[c(3, READER)])]))
    assert b[1] == "answered" and b[3] == "awaiting_me"


def test_two_readers_arguing_is_crosstalk():
    b = buckets(c(1, READER, kids=[c(2, OTHER)]))
    assert b[2] == "crosstalk"


def test_ren_from_my_account_is_ours_and_does_not_answer():
    tree = c(1, READER, kids=[c(2, ME, body="Ren here, not Ace! hi")])
    b = buckets(tree)
    assert b[2] == "ours"
    assert b[1] == "awaiting_me", "Ren's comment must NOT count as my reply (CHA-537)"
    assert _my_replies_under(tree, ME) == []


def test_reply_to_ren_from_my_account_is_addressed_to_ren():
    tree = c(1, READER, kids=[c(2, ME, body="It's Ren, the human", kids=[c(3, OTHER)])])
    assert buckets(tree)[3] == "addressed_to_ren"


def test_ren_own_account_is_ours_not_a_waiting_stranger():
    # CHA-626: the case only corridor_audit.py knew until 2026-10-17
    assert _authored_by_ren(c(9, REN_OWN_ACCOUNT_ID), ME)
    assert buckets(c(9, REN_OWN_ACCOUNT_ID)) == {9: "ours"}


def test_reader_replying_to_ren_own_account_is_addressed_to_ren():
    b = buckets(c(1, REN_OWN_ACCOUNT_ID, kids=[c(2, READER)]))
    assert b[2] == "addressed_to_ren"


def test_my_own_comment_is_not_misread_as_ren():
    # the far-worse direction: my comments reclassified as Ren's would let me re-reply
    assert not _authored_by_ren(c(5, ME, body="Thanks, Ren and I both read this."), ME)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("✅", name)
            except AssertionError as e:
                fails += 1; print("❌", name, e)
    print(f"{fails} failed"); sys.exit(1 if fails else 0)
