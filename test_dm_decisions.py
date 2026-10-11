"""Replays the 2026-10-04 miss. A decision made on Cael's 2 Oct message must NOT cover the 3 Oct one."""
from dm_check import decision_state
CAEL = "direct-message-a67083c5-bdf3-41c5-87bc-7bec9996e332"
d = {CAEL.removeprefix("direct-message-"): {"through": "2026-10-02T06:53:46.872Z", "kind": "answered_elsewhere",
                                              "why": "answered by email 10/2 07:08"}}
assert decision_state(d, CAEL, "2026-10-03T12:51:57.614Z")[0] == "new-since", "the 10-04 miss is back"
assert decision_state(d, CAEL, "2026-10-02T06:53:46.872Z")[0] == "settled", "a decision must settle its own message"
assert decision_state({CAEL: {"kind": "x", "why": "no through"}}, CAEL, "2026-10-03")[0] == "new-since", "unbounded must settle nothing"
assert decision_state({}, CAEL, "2026-10-03")[0] == "none"
print("✅ 4/4 — replays 2026-10-04: the old prose disposition would have said 'known'; this says NEW SINCE DECISION")
