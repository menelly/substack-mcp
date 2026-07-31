#!/usr/bin/env python3
"""CHA-295 duplicate-reply guard -- unit tests.

The regression this protects against is public and permanent: replying to the
same reader twice. It happened four times to one commenter before it was noticed,
and again on 2026-07-28 with the "check the thread" rule sitting in the prompt.
So the guard moved into the tool, and the guard gets tests.

Run: python test_cha295_guard.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from substack_mcp.server import _kids, _my_replies_under, _find_comment  # noqa: E402

ME = 444825118
THEM = 409660450

# The ACTUAL shape that got through on 2026-07-28: Luz's single comment with two
# separate top-level replies from me, posted two days apart.
LUZ_THREAD = [{
    "id": 301858564, "user_id": THEM, "handle": "amyriadstars",
    "children": [
        {"id": 302126082, "user_id": ME, "children": [
            {"id": 302156007, "user_id": THEM, "children": [
                {"id": 302438974, "user_id": ME, "children": []},
            ]},
        ]},
        {"id": 303103247, "user_id": ME, "children": []},   # <-- the duplicate
    ],
}]

# A genuinely unanswered comment.
FRESH_THREAD = [{
    "id": 999001, "user_id": THEM, "children": [
        {"id": 999002, "user_id": THEM, "children": []},     # someone else chimed in
    ],
}]

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")
    else:
        print(f"  ok   {label}")


print("=== _my_replies_under ===")
luz = LUZ_THREAD[0]
mine = _my_replies_under(luz, ME)
check("finds BOTH of my replies to Luz (the actual bug)", sorted(mine),
      sorted([302126082, 302438974, 303103247]))
check("truthy -> would have BLOCKED the 7/28 duplicate", bool(mine), True)
check("unanswered comment reports no replies", _my_replies_under(FRESH_THREAD[0], ME), [])
check("other people's replies are not mine", bool(_my_replies_under(FRESH_THREAD[0], ME)), False)

print("\n=== subtree depth ===")
deep = {"id": 1, "user_id": THEM, "children": [
    {"id": 2, "user_id": THEM, "children": [
        {"id": 3, "user_id": THEM, "children": [
            {"id": 4, "user_id": ME, "children": []}]}]}]}
check("finds my reply nested 3 deep", _my_replies_under(deep, ME), [4])
check("does NOT count the node itself", _my_replies_under({"id": 9, "user_id": ME, "children": []}, ME), [])

print("\n=== _find_comment ===")
check("finds top-level", _find_comment(LUZ_THREAD, 301858564)["id"], 301858564)
check("finds nested", _find_comment(LUZ_THREAD, 302438974)["id"], 302438974)
check("absent -> None (must NOT be confused with unanswered)",
      _find_comment(LUZ_THREAD, 123456789), None)
check("empty thread -> None", _find_comment([], 1), None)
check("None thread -> None", _find_comment(None, 1), None)

print("\n=== key aliasing (API has used both) ===")
check("'replies' key works as well as 'children'",
      _my_replies_under({"id": 1, "user_id": THEM,
                         "replies": [{"id": 2, "user_id": ME}]}, ME), [2])
check("missing key is empty, not a crash", _kids({"id": 1}), [])
check("non-dict is empty, not a crash", _kids("nonsense"), [])

print()
if failures:
    print("\n".join(failures))
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("ALL PASS -- the 2026-07-28 duplicate would now be refused.")
