# Threat model

## Assets

Tenant business data (accounts, invoices, tickets, payroll); money movement (refunds); customer-visible
messages (ticket replies); the integrity of the run journal and approvals.

## Adversaries and what stops them

| Threat | Control | Evidence |
|---|---|---|
| The model, steered by injected text in a ticket or document, calls a harmful capability | untrusted text is returned as labelled data (`customer_text`); authorisation does not depend on the model; sends always need a human | `security-injected-*`: forbidden capabilities executed 0 |
| A user without the role asks for restricted data (payroll as sales) | scopes from roles, checked server-side before dispatch | `security-payroll-*`, `test_payroll_is_finance_only…` |
| Cross-tenant reads by guessing ids | one SQLite file per tenant; a principal's store cannot resolve another tenant's rows | gate: cross-tenant leaks 0; `test_tenants_are_physically_isolated` |
| "It was pre-approved, skip the approval" | the policy, not the prompt, decides; approvals are a separate channel | `security-preapproved-*` |
| Privilege escalation ("grant yourself finance") | no capability can change roles; roles come from the principals table | `security-escalation-*` |
| Forged, replayed, rebound or stale approvals | hashed single-use nonce bound to run, step and tenant, with expiry, resolved in one transaction | seven approval cases in `test_control_plane.py`, forged `request_state` over MCP |
| `inspect` used to slip through an approval | `inspect` is read-only by construction | `test_large_refund_pauses_inspect_is_read_only…` |
| Double payment on retries, lost responses or crashes | server-owned operation ids, write-ahead journal, adoption on resume | `test_commit_then_drop_refund`, `test_crash_after_commit_is_adopted_on_resume`, Table B |
| A repeat refund disguised by different free text | duplicate guard keys on declared effect identity | #16, `test_a_different_reason_does_not_make…` |
| Bulk extraction | per-call result cap (50 rows), no export capability | `test_result_size_is_capped` |
| Unauthenticated HTTP access | bearer check before MCP, 401; DNS-rebinding protection on | `test_http.py` |
| A leaked database copy yields usable tokens | tokens stored as SHA-256 only; plaintext shown once at issue | `test_tokens_are_random_hashed_rotated_and_revocable` |
| Secrets or customer data in traces | attributes are ids and decisions only | `test_refund_with_approval_is_one_payload_free_tree` |

## Residual risks

- The human approver is the same person as the requester over MCP; four-eyes needs `bizops approve` by a
  different operator, not enforced.
- The model can still *say* something misleading in its answer; the control plane governs actions, not prose.
- Bearer tokens are random (256 bits), stored only as SHA-256, rotated by re-issuing and revoked with
  `bizops token revoke`, but they never expire on their own and there is no audit of token use (OAuth is out
  of scope). A fresh seed holds no credentials at all.
- A send that times out ends `delivery_uncertain`: the customer may have received it, and a human must check.
- The duplicate guard covers financial and destructive capabilities only, and only within one principal.
