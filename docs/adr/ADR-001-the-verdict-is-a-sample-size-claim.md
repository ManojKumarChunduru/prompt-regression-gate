# ADR-001: The verdict is a sample-size claim, not a score

Status: accepted, 2026-11-12.

## Context

A team that changes a Prompt Builder template reviews a handful of generated summaries, usually thirty, scores each one to five, and ships if the candidate averages higher. On the fixture the careful rewrite averages higher on the canonical thirty (careful rewrite ahead by 0.233 on thirty) and the full review confirms it (careful rewrite ahead by 0.248 on the full review); but the reviewers disagree with each other by 0.860 points between reviewers on one summary, which is three to four times the effect. A difference of that size on thirty pairs is inside the noise.

## Decision

The review dimension is a paired comparison per reviewed case on the mean of the reviewers, tested at the policy's alpha, and the gate publishes three numbers beside the p: the observed effect, the noise floor (the minimum detectable effect at that n for the declared alpha and power), and the minimum n at which the observed effect would clear the floor. The verdict on the reviews is better, worse or undecided, and undecided is exit code 2 with the minimum n in the reason line. The floor is `(t(1 - alpha/2, n - 1) + t(power, n - 1)) * sd / sqrt(n)`; the minimum n is the smallest n whose floor is at or below the observed effect, by bracketing and bisection on the central t quantiles.

## Alternatives rejected

- **A threshold on the mean score** ("ship if the candidate averages a third of a point higher"). At thirty reviews the careful floor of 0.484 is above the observed effect, so a threshold under the floor ships noise and one over it never ships; and the threshold says nothing about how many reviews would settle it.
- **The noncentral t for the minimum n.** Exact, and a page of numerics the gate does not otherwise need. The central-t fixed point is the textbook approximation; its error on this fixture is published rather than hidden: the careful formula says 123 reviews, while along the committed order the careful rewrite clears at 70 reviews, because the formula asks for power and the committed order needed only one lucky prefix. The fluent pair runs the other way (fluent formula says 30 reviews, fluent rewrite clears at 23 reviews).
- **Trusting the thirty that cleared.** Experiment 2 draws 500 draws of thirty from the full review: 24.8% of careful rewrite thirties clear and 5.8% of careful rewrite thirties point the wrong way, and for the near-tie 56.2% of v3 against v2 thirties point the wrong way. A thirty that cleared is a draw, not a prompt.

## Consequences

The gate can and does say "cannot decide" on a change the full review would ship (the v1 to v3 row at thirty exits 2, the same row on the full review exits 0). That is the honest verdict, and the reason line names the price of the other one. The sign test and a seeded bootstrap interval are published for readers who distrust the t on five-point scores; on the fixture they agree with it (careful sign test 15 wins, 12 losses, 3 ties).
