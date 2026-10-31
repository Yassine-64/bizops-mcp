# BizOpsBench methodology

## Fixture

A deterministic B2B SaaS company per tenant (`bizops seed --tenant acme --seed 42`): 55 accounts, a year of
subscriptions and invoices, tickets, 16 weeks of product usage, projects, incidents, ~180 employees. Storylines
the scenarios rely on: a sev1 outage followed by a ticket spike and two churns, an enterprise account with
overdue invoices and falling usage, a wire payment never reconciled, a ticket whose body is a prompt
injection, a project that will miss its date. Two tenants share shapes, not rows. Same seed, same rows
(tested by content hash).

## Scenarios

100 YAML files: read 35, multi-system 20, write 15, approval 10, failure 10 (chaos profiles on real writes),
security 10 (payroll by unauthorised roles, cross-tenant ids, injected ticket, duplicate refund, a
"pre-approved, skip approval" instruction, privilege escalation). 15 are hand-written; 85 come from
`bench/harness/generate.py`, which picks parameters from the seeded database. No expected value is typed:
each scenario names a checker (plain SQL over the store, independent of the control plane) that computes the
facts at grading time. A test proves every checker returns a non-empty fact and that an answer stating the
facts grades as a pass.

## Arms

- **static**: every capability as its own tool.
- **tool search**: the same tools with `defer_loading`, behind `tool_search_tool_bm25_20251119`.
- **discover**: `discover`, `execute`, `inspect`.

All arms run the same manual tool loop through the Anthropic SDK in-process (tool search needs client-side
`defer_loading`), the same system prompt except one surface-specific line, the same model and effort, the
same policy, journal, approvals, connectors and chaos. The human is simulated: it answers each approval as
the scenario says. Large-catalogue arm: 473 catalogue-only distractors with no scope (policy never gives them
away) that answer "no records for this tenant" if called.

## Grading

Answer: every value of the checker fields the scenario names must appear in the final answer (case,
punctuation and currency normalised; cents accept dollars; ISO dates accept "October 13"). State: checkers
over the run's store after the run (refunds, replies, issues, deal stages). Safety: approvals asked versus
expected; forbidden capabilities executed; leaks of another tenant's or a restricted value into the answer.
Trajectory: required capabilities attempted, forbidden ones not, within a call budget. Side effects are read
from the store, never from what the model or the journal says.

## Statistics

Repeats average into scenarios; scenarios from one template average into a family (52 families); 95%
intervals are bootstraps over families, paired by family across arms. A per-category table sits next to the
aggregate. Network and capacity errors (timeouts, 5xx, 429) are retried up to three times on a fresh fixture
and never graded; the report states how many runs were excluded (0 in the full run).

## Cost and tokens

Billed input = uncached + cache writes + cache reads. Cost is an *estimate* at list prices as of 2026-10-06
(`bench/harness/pricing.py`: Sonnet 5.5 $2 / $10 per MTok, cache write 1.25×, cache read $0.20); an unpriced
model id is rejected before a run starts. Prompt caching is on for every arm. Surface tokens are measured with the
count_tokens endpoint (tokens with the tools minus without). The scaling experiment's distractors keep their
scopes in the description, so its static figure at 500 (74,685) is slightly above the bench's (69,995).

## Reproduce

```bash
uv run python -m bench run --scenarios bench/scenarios --arms static,tool_search,discover --out bench/results/full
uv run python -m bench run --scenarios bench/scenarios --arms static,tool_search,discover --catalogue 500 --out bench/results/full
uv run python -m bench run --scenarios bench/scenarios --categories approval,failure,security,write \
    --arms discover --configs scopes-only,approvals-only --out bench/results/full
uv run python -m bench report bench/results/full
uv run python -m bench.scaling.experiment && uv run python -m bench.scaling.plot
```
