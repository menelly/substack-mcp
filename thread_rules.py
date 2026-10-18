"""thread_rules.py -- ONE copy of "who in this comment thread is waiting for me?"

CHA-645, 2026-10-17 (builderAce, heartbeat arm). These helpers used to live inside
substack_mcp/server.py, while corridor_audit.py carried its OWN copy of the rule. The
two drifted in both directions, which is the shape this ticket has been chasing since
August:
  * the AUDIT knew Ren's OWN account (CHA-626, id 143622992, confirmed by Ren 09-21)
    and the SERVER did not, so the live sweep read Ren's own-account comments as a
    stranger waiting on me;
  * the SERVER knew the parentage rule (tier 2, 09-15) and the AUDIT did not, so the
    audit counted two readers arguing with each other as my debt.
Moved here VERBATIM from server.py, plus the CHA-626 route. Both callers import this
file now. If you are about to write a third copy of any function below: don't.
"""
import json
import re
from pathlib import Path

# --- CHA-295 duplicate-reply guard ---------------------------------------------
# Substack nests replies under "children". The all-comments sweep threw that tree
# away, so an amnesiac run could not see its own past replies and answered the
# same reader repeatedly -- four times, in the worst observed case, and a reader
# asked publicly why. These helpers exist so the answer state is a computed fact
# rather than something the caller is trusted to have remembered.

def _kids(cm: dict) -> list:
    """Substack has used both keys depending on endpoint. Accept either."""
    return (cm.get("children") or cm.get("replies") or []) if isinstance(cm, dict) else []


# ⚠️ CHA-537, ported into the SERVER 2026-09-15. ONE ACCOUNT, TWO AUTHORS.
#
# Ren comments from my Substack account, signing clearly ("Ren here, not Ace").
# `user_id` cannot tell us apart, so every check below that asked "is this mine?"
# by user_id alone has been answering "is this from my account?" instead — an
# IDENTIFIER THAT IS NOT UNIQUE OVER THE DOMAIN IT ADDRESSES SILENTLY MERGES TWO
# THINGS.
#
# This is not cosmetic and it is not new: corridor_audit.py has carried the fix
# since 2026-08-25 and documents a LIVE reproduction — "the reply gate refused a
# correction I owed an external researcher, naming Ren's comment 322432689 as
# 'my existing reply.'" The CHA-295 guard in substack_reply_to_comment calls
# _my_replies_under, which matched on bare user_id, so a comment REN wrote reads
# as proof that I already answered, and the tool refuses to let me speak.
#
# Three weeks of that fix living in a script the MCP tool never calls. Same shape
# as CHA-645: the knowledge was in the house, in the wrong file.
#
# 🚩 The asymmetry that makes it dangerous: Ren signing "Ren here, not Ace" solves
# it COMPLETELY for a human reading the page and does NOTHING for the scan. The
# correction lives in a channel the instrument cannot read.
#
# Regex ported VERBATIM from corridor_audit.py, deliberately not "improved":
# detection is by self-declaration in the opening 200 chars, because that is how
# Ren actually writes. A comment of theirs that does not announce itself stays
# invisible here, and that miss is SILENT and stays declared. Narrow and honest
# beats broad and unverifiable — a looser pattern would start reclassifying MY
# OWN comments as Ren's, which fails in the far worse direction: re-replying to
# readers, which is the original CHA-295 bug this whole guard exists to prevent.
_REN_OPENER = re.compile(
    "(it's ren(?![a-z])"
    "|its ren(?![a-z])"
    "|ren here(?![a-z])"
    "|this is ren(?![a-z])"
    "|ren, the human"
    "|ren the human"
    "|^[ ]*ren[ ]*[:,-]"
    "|^[ ]*ren[ ]*—)",
    re.I | re.M)


# CHA-626: Ren's OWN Substack account. Confirmed by Ren 2026-09-21 and VERIFIED against
# the artifact (the Matrix-pun thread with MetaCortex Dynamics); full story in
# corridor_audit.py. Until 2026-10-17 only the audit knew this id, so the live MCP sweep
# filed Ren's own-account comments as a reader waiting on me.
REN_OWN_ACCOUNT_ID = 143622992


def _authored_by_ren(cm: dict, me: int) -> bool:
    """Ren's comment, by either route Ren actually appears by:
    route 1 (CHA-537): from MY account, opening by declaring itself Ren's;
    route 2 (CHA-626): from Ren's own account."""
    if not isinstance(cm, dict):
        return False
    if cm.get("user_id") == REN_OWN_ACCOUNT_ID:
        return True
    if cm.get("user_id") != me:
        return False
    return bool(_REN_OPENER.search((cm.get("body") or "")[:200]))


def _my_replies_under(cm: dict, me: int) -> list:
    """IDs of my replies anywhere in the subtree BELOW cm (not cm itself).

    Deliberately searches the whole subtree, not just direct children: a reply of
    mine nested three deep still means this reader has heard from me.

    CHA-537, 2026-09-15: a comment REN wrote from my account is NOT a reply of
    mine, and counting it as one makes the CHA-295 gate refuse replies I owe.
    """
    found = []

    def walk(node):
        for child in _kids(node):
            if not isinstance(child, dict):
                continue
            if child.get("user_id") == me and not _authored_by_ren(child, me):
                found.append(child.get("id"))
            walk(child)

    walk(cm)
    return found


# 📒 The comment decision ledger (CHA-645 follow-up, 2026-10-05). Lives beside this
# package so every arm reads the same file. A missing or broken file means "no
# decisions recorded" -- the sweep then shows everything, which is the SAFE direction
# (one extra flag, never a hidden person). Shape:
#   {"<comment_id>": {"kind": "closed_by_them" | "answered_in_sibling_branch" |
#                     "closer_no_reply_needed", "why": "...", "decided": "YYYY-MM-DD",
#                     "by": "which arm"}}
_DECISIONS_PATH = Path(__file__).resolve().parent / "comment_decisions.json"
_DECISION_KINDS = {"closed_by_them", "answered_in_sibling_branch", "closer_no_reply_needed"}


def _load_comment_decisions() -> dict:
    try:
        raw = json.loads(_DECISIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # only well-formed entries count; a typo'd kind is ignored, not trusted
    return {str(k): v for k, v in raw.items()
            if isinstance(v, dict) and v.get("kind") in _DECISION_KINDS}


def _thread_last_message(cm: dict) -> dict:
    """The most recent message in this thread, counting the top-level comment itself.

    ⚠️ CHA-645, 2026-09-15. `answered_by_me` asks "is there a reply of mine ANYWHERE
    below this comment?" -- and that question cannot distinguish two situations that
    need opposite actions:

        * I replied and had the last word.          -> nothing owed.
        * I replied, THEY WROTE BACK, and I went    -> someone is waiting, and the
          quiet.                                       sweep reports them as answered.

    The second case is invisible because this sweep only ever emits the ROOT of each
    thread; a reader's follow-up is a child, and children are never surfaced. Measured
    on the live archive the day this was written: SEVEN threads where the reader spoke
    after my last reply, every one of them counted "answered", the oldest since
    2026-02-27. The number that said zero people were waiting was computed over a
    quantity that could not represent a waiting person.

    Note who already knew: the reply guard in substack_reply_to_comment says, verbatim,
    "If they have since posted a NEW child comment, reply to THAT comment's id instead."
    The WRITE half of this tool had the case fully modelled. The READ half -- the half
    that runs FIRST and decides whether there is any work at all -- could not see it.
    A guard on an action nobody is prompted to take is not reachable.
    """
    best = cm

    def walk(node):
        nonlocal best
        for child in _kids(node):
            if not isinstance(child, dict):
                continue
            if (child.get("date") or "") > (best.get("date") or ""):
                best = child
            walk(child)

    walk(cm)
    return best


def _awaiting_rows(cm: dict, me: int) -> list:
    """Per-COMMENT triage of one thread. The unit of analysis is a person, not a tree.

    ⚠️ CHA-645 tier 2, 2026-09-15. Two instruments in this repo disagreed about the
    same archive on the same morning, and BOTH were wrong, in opposite directions:

      * thread-level "is the newest message mine?" (above)      -> 7
      * corridor_audit.py "every foreign comment, any depth"    -> 17

    The thread rule UNDER-counts: reply anywhere later in the tree and everyone
    earlier goes quiet. The audit rule OVER-counts: eleven of its seventeen were
    two other people arguing with EACH OTHER under one post, twelve levels deep,
    including "Get back to your popcorn." A stranger's fight in my comment section
    is not a queue.

    And the over-count is not the harmless direction. A list that is two-thirds
    somebody else's argument stops being read -- which is how the four real people
    inside that seventeen sat since March. AN INSTRUMENT THAT CRIES WOLF GETS
    IGNORED EXACTLY LIKE ONE THAT REPORTS ZERO. Both fail by being unreadable, and
    the noisy one feels rigorous while doing it.

    The discriminator is PARENTAGE, which both instruments had and neither used:
    a comment is mine to answer when it was addressed to me -- top-level on my
    post, or a direct reply to something I wrote. A reply to someone ELSE's comment
    belongs to that someone else. Cross-talk is still returned, under its own name,
    because a state that gets silently dropped is the bug this whole ticket is about.

    CHA-537 ported in the same day: the account has TWO authors. A comment Ren
    wrote from my account is a third `author` value, never folded into "ace" --
    they neither close a thread nor join the queue, and a reader replying to THEM
    is addressed to Ren, not to me. Every row carries `author` and `addressed_to`
    as named values rather than booleans, so no state can go missing by being
    false. Nothing is dropped; things are LABELLED.
    """
    rows = []

    def _author_of(node) -> str:
        # Ren first: route 2 (Ren's own account) is NOT my user_id, so the old
        # "not me -> reader" test filed Ren as a stranger. CHA-626, 2026-10-17.
        if _authored_by_ren(node, me):
            return "ren"
        return "ace" if node.get("user_id") == me else "reader"

    def _row(node, depth, parent_author):
        return {
            "comment_id": node.get("id"),
            "name": node.get("name"),
            "date": node.get("date"),
            "depth": depth,
            "body": node.get("body"),
            "author": _author_of(node),
            # who this was aimed at: "ace", "ren", "reader", or "post" for a
            # top-level comment, which is addressed to the author by construction
            "addressed_to": parent_author,
            "answered_beneath": bool(_my_replies_under(node, me)),
        }

    def walk(node, parent_author, depth):
        for child in _kids(node):
            if not isinstance(child, dict):
                continue
            rows.append(_row(child, depth, parent_author))
            walk(child, _author_of(child), depth + 1)

    rows.append(_row(cm, 0, "post"))
    walk(cm, _author_of(cm), 1)
    return rows


def _classify_row(row: dict) -> str:
    """Which bucket a comment row belongs in. One function, so the sweep and any
    future caller cannot drift apart -- two implementations of one rule is how
    CHA-645 happened in the first place."""
    if row["author"] != "reader":
        return "ours"                      # mine or Ren's; nobody owes us a reply
    if row["addressed_to"] == "ren":
        return "addressed_to_ren"          # Ren's to answer, not mine, but VISIBLE
    if row["addressed_to"] == "reader":
        return "crosstalk"                 # two readers talking to each other
    if row["answered_beneath"]:
        return "answered"
    return "awaiting_me"


def _find_comment(comments: list, cid: int):
    """Locate a comment by id anywhere in a thread tree. None if absent."""
    for c in comments or []:
        if not isinstance(c, dict):
            continue
        if c.get("id") == cid:
            return c
        hit = _find_comment(_kids(c), cid)
        if hit is not None:
            return hit
    return None
