"""The four exit codes and the rule that orders them.

0 ship: the candidate's review score clears the noise floor in its favour and its grounding is not
  demonstrably worse.
1 blocked: a demonstrated regression on either dimension (reviews lower by more than the floor, or
  more bad claims by more than the floor).
2 cannot decide: the review sample cannot separate the versions at the declared alpha, or a
  version's grounding could not be judged (its template merges a field the export lacks).
3 usage: a bad argument or a malformed input, named.

1 wins over 2. A demonstrated regression blocks whatever else is unknown; "cannot assert ship" is
the verdict only when nothing has been demonstrated (ADR-004).
"""

SHIP = 0
BLOCKED = 1
UNDECIDED = 2
USAGE = 3

NAMES = {SHIP: "ship", BLOCKED: "blocked", UNDECIDED: "cannot decide", USAGE: "usage"}


class PrgError(Exception):
    """An input the gate refuses to read, with the file and the element named. Exit 3."""
