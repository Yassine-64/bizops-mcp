# Architecture

## Layers and the dependency rule

```
interfaces      MCP server (stdio, Streamable HTTP + bearer), CLI
    ↓
infrastructure  SQLite tenant stores and journal, connectors, seed fixture, chaos, settings, container, tracer
    ↓
application     catalogue, discovery, executor + dispatcher, approvals, surfaces, replay, telemetry facade
    ↓
domain          Capability, Principal, Run, Step, policy, roles, signatures, ports       (no I/O, no frameworks)
```

Dependencies point inward. `tests/unit/test_architecture.py` parses every import and fails if the domain
imports an outer layer or I/O libraries, or if the application imports infrastructure or interfaces. Where an
inner layer needs the outside world it declares a port in `domain/ports.py`: `TenantStores` (open one tenant's
store) and `Journal` (durable run state). The composition root is `infrastructure/container.py`.

A package exists only when it holds several cohesive modules; `__init__.py` files only re-export.

## A call, end to end

1. **Transport.** stdio serves one configured principal. HTTP authenticates the bearer token in an ASGI layer
   *before* MCP: no or unknown token is a 401. The token resolves to a principal from the issuing tenant's
   `principals` table: tenant, user, roles, and scopes derived from roles in `domain/services/roles.py`.
   Nothing the model sends can change any of these.
2. **Surface.** `discover` searches the catalogue (BM25 over names, descriptions, parameters) and returns exact
   signatures with risk, approval rule and scopes. `execute` turns steps into a run. `inspect` reads a run.
   The static surface exposes every capability as its own tool and turns each call into a one-step run, so
   both surfaces share everything below.
3. **Executor** (`application/execution/executor.py`). For each step: the policy decides `allow`, `approve`
   or `deny` (scope first, then risk class, then the duplicate guard); a denial stops the run; an approval
   pauses it; otherwise the step is dispatched.
4. **Dispatch.** Write-ahead: the step is journaled `running` with its operation id before the connector is
   called. The connector runs against the principal's tenant store only.

## Run and step lifecycle

```
pending ─▶ running ─▶ done
   │          ├────▶ failed | delivery_uncertain
   │          └────▶ (crash) running, resumed by the next execute
   ├─▶ awaiting_approval ─▶ approved ─▶ running …
   │                    └─▶ declined
   └─▶ denied
```

A run stops at the first step that ends anything but `done`. `execute(run_id)` continues a run whose paused
step a human has approved; `inspect` never mutates.

## Operation identity

- The server mints an operation id the first time a write is dispatched and reuses it on every retry and on
  resume. Connectors treat it as an idempotency key (Stripe-style): a repeat with the same id returns the
  original effect, marked `replayed`.
- After an unknown outcome (timeout, lost response, crash with the step still `running`), only reads and
  idempotent writes run again. A send (ticket reply) cannot be looked up after the fact, so it ends
  `delivery_uncertain` and is never re-sent.
- The duplicate guard: a financial or destructive step whose *effect key* matches an earlier step of the same
  principal that may have taken effect needs a human. The effect key is the capability's declared `identity`
  arguments (a refund: payment and amount), not free text such as a reason. BizOpsBench found the free-text
  hole (#16).
- `durable=False` exists for the ablation only: a fresh id per attempt and no guard, i.e. a naive client.

## Approvals

`approval_requests(id, run_id, step_id, tenant, capability, reason, nonce_hash, status, created_at,
expires_at, consumed_at, approved_by)`. The nonce goes to the human channel only (the MCP input-required
`request_state`, or the elicitation prompt); only its SHA-256 is stored. Resolving is one `BEGIN IMMEDIATE`
transaction: find by hash, check run, step and tenant binding, check status and expiry, mark consumed, move
the step to `approved` or `declined`. Issuing a new request for a step supersedes the old one. Dispatch
happens after commit, so no window exists in which a nonce is consumed but the step not approved.

## Observability and replay

`application/telemetry.py` uses the OpenTelemetry API (a no-op until a provider exists).
`infrastructure/telemetry.py` registers one global provider; the Anthropic SDK emits into it, so model calls
and control-plane work share a trace. Spans: `bizops.run`, `bizops.step`, `bizops.policy`,
`bizops.connector`, `bizops.discover`, `bizops.approval.issue|resolve`; retries are events. Attributes are
ids, names, risk, decisions, counts; a test asserts no argument value or customer text appears.

`bizops replay <run>` re-runs a recorded run through today's policy and executor with connectors replaced by
the recorded outputs and approvals re-applied as recorded, and reports divergences (policy drift, a rewritten
decision). It cannot see an edited *result* by design, which is why the benchmark grades side effects from
the store.

## What is deliberately simple

SQLite for everything (the point is execution semantics, not scale). BM25 instead of embeddings. Bearer
tokens instead of OAuth. bizops-native durable runs instead of the experimental MCP Tasks extension.
