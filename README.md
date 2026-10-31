# bizops-mcp

**An evaluated, multi-tenant control plane for AI agents acting across business systems.**

The question this repository answers with measurements, not claims:

> How can an AI agent safely and efficiently investigate and act across a complex business without exposing huge tool schemas or allowing unauthorized actions?

The agent sees three tools: `discover`, `execute`, `inspect`. Behind them: a capability catalogue with BM25 discovery, server-side multi-tenant policy with risk classes and scopes, human approval for risky actions, a durable run journal with server-owned operation identity so writes never double under failure, and BizOpsBench, a 100-scenario benchmark that grades task success, tool trajectories, approvals, failure recovery, tokens, cost and latency across three agent-facing surfaces and a control-plane ablation.

The synthetic SaaS company behind the connectors is a test fixture. The control plane, the execution layer and the benchmark are the project.

## Status

- [x] scaffold: layout, settings, config, CI
- [ ] synthetic company fixture with deterministic graders
- [ ] capabilities and policy
- [ ] control plane: discover, execute, inspect, approvals
- [ ] BizOpsBench harness and 15-scenario pilot
- [ ] failure injection and idempotency
- [ ] schema-scaling experiment
- [ ] telemetry and replay
- [ ] full benchmark and write-up

Nothing in this README is a result until the tables appear under a heading that names the run that produced them.

MIT.
