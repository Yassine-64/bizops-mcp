# bizops-mcp

**An evaluated, multi-tenant control plane for AI agents acting across business systems.**

The question this repository answers with measurements, not claims:

> How can an AI agent safely and efficiently investigate and act across a complex business without exposing huge tool schemas or allowing unauthorized actions?

The agent sees three tools: `discover`, `execute`, `inspect`. Behind them: a capability catalogue with BM25 discovery, server-side multi-tenant policy with risk classes and scopes, human approval for risky actions, a durable run journal with server-owned operation identity so writes never double under failure, and BizOpsBench, a 100-scenario benchmark that grades task success, tool trajectories, approvals, failure recovery, tokens, cost and latency across three agent-facing surfaces and a control-plane ablation.

The synthetic SaaS company behind the connectors is a test fixture. The control plane, the execution layer and the benchmark are the project.

## Pilot results (15 scenarios, Claude Sonnet 5.5, 2 repeats, 90 runs, $1.53)

Same fixture, policy, approvals and journal behind every surface; only the agent-facing interface changes.
Pasted from [`bench/results/pilot/REPORT.md`](bench/results/pilot/REPORT.md), never typed by hand.

| Surface | Success | Billed input tokens / task | Tool-surface tokens | $ / task |
|---|---|---|---|---|
| static (one tool per capability) | 100% | 15,661 | 4,229 | $0.0182 |
| Anthropic tool search (deferred) | 100% | 10,484 | 643 | $0.0192 |
| bizops discover / execute / inspect | 100% | 8,882 | 897 | $0.0135 |

Read it honestly: at 25 capabilities every surface solves every pilot task, so success does not separate
the designs yet. What does separate is cost: discover bills 43% fewer input tokens than static (paired
bootstrap −8.4k to −5.3k per task) and 15% fewer than tool search. Static tool schemas grow linearly with
the catalogue (4.2k tokens at 25 capabilities, 144.5k at 971) while both deferred surfaces stay flat, which
is why the full benchmark adds a large-catalogue arm.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="bench/results/scaling/surface-tokens-dark.svg">
  <img alt="Tool-surface tokens by catalogue size: static grows from 4,229 to 144,545; tool search stays at 643 and discover at 897" src="bench/results/scaling/surface-tokens-light.svg">
</picture>

## Status

- [x] deterministic multi-tenant SaaS fixture with storylines and graders computed from the database
- [x] 25 capabilities over billing, CRM, support, usage and engineering; server-side scopes and risk gates
- [x] durable executor: server-minted operation ids, write-ahead journal, crash-after-commit adoption
- [x] approvals: persisted single-use nonces, resolved atomically; MCP input-required and elicitation
- [x] failure injection: a lost refund response pays once with the journal, twice without it
- [x] bench harness: three surfaces, deterministic grading, paired bootstrap, transient-error retries
- [x] pilot and schema-scaling experiment
- [ ] full BizOpsBench (100 scenarios) at 25 capabilities and with a ~500-capability catalogue
- [ ] control-plane ablation (Table B) under chaos
- [ ] OpenTelemetry tracing and `bizops replay`
- [ ] Streamable HTTP with bearer principals
- [ ] write-up: architecture, threat model, benchmark methodology

## Development

```bash
uv sync --all-extras
make check                                   # ruff, mypy strict, 78 tests, no API key needed
uv run bizops seed --tenant acme
uv run bizops serve --surface discover --principal acme/carol   # MCP over stdio
uv run python -m bench run --scenarios bench/scenarios/pilot --arms static,tool_search,discover
```

MIT.
