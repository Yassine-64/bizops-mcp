"""Catalogue-only capabilities for the schema-scaling experiment. They have realistic names, descriptions and
schemas and no implementation. Many are deliberately near-misses of the real ones (accounting.invoices.list
next to billing.invoices.list, sales_ops.revenue_forecast next to billing.mrr_by_month), because easy
distractors would flatter discovery."""

from __future__ import annotations

import random

from bizops.domain.models import Risk
from bizops.domain.models.capability import Capability, Parameter

# system -> resources (singular, plural) with a domain word for descriptions
SYSTEMS: dict[str, list[tuple[str, str, str]]] = {
    "accounting": [
        ("invoice", "invoices", "vendor bills"),
        ("journal_entry", "journal_entries", "ledger postings"),
        ("ledger", "ledgers", "general ledger accounts"),
        ("tax_filing", "tax_filings", "tax returns"),
        ("payment_run", "payment_runs", "outgoing vendor payments"),
    ],
    "sales_ops": [
        ("forecast", "forecasts", "revenue forecast"),
        ("quota", "quotas", "sales quotas"),
        ("territory", "territories", "sales territories"),
        ("commission", "commissions", "rep commissions"),
        ("pipeline_snapshot", "pipeline_snapshots", "pipeline history"),
    ],
    "marketing": [
        ("campaign", "campaigns", "marketing campaigns"),
        ("lead", "leads", "inbound leads"),
        ("segment", "segments", "audience segments"),
        ("email_blast", "email_blasts", "email sends"),
        ("webinar", "webinars", "webinar registrations"),
    ],
    "hr": [
        ("employee", "employees", "employee records"),
        ("payroll_run", "payroll_runs", "payroll"),
        ("time_off", "time_off_requests", "leave requests"),
        ("review", "reviews", "performance reviews"),
        ("candidate", "candidates", "job candidates"),
    ],
    "procurement": [
        ("purchase_order", "purchase_orders", "purchase orders"),
        ("vendor", "vendors", "suppliers"),
        ("contract", "contracts", "supplier contracts"),
        ("rfq", "rfqs", "requests for quote"),
    ],
    "it": [
        ("device", "devices", "laptops and phones"),
        ("license", "licenses", "software seats"),
        ("access_request", "access_requests", "system access"),
        ("ticket", "tickets", "IT helpdesk tickets"),
    ],
    "security": [
        ("alert", "alerts", "security alerts"),
        ("vulnerability", "vulnerabilities", "CVE findings"),
        ("audit_log", "audit_logs", "audit events"),
        ("policy", "policies", "security policies"),
    ],
    "analytics": [
        ("dashboard", "dashboards", "BI dashboards"),
        ("metric", "metrics", "business metrics"),
        ("cohort", "cohorts", "customer cohorts"),
        ("report", "reports", "scheduled reports"),
        ("experiment", "experiments", "A/B tests"),
    ],
    "success": [
        ("health_check", "health_checks", "customer health"),
        ("renewal", "renewals", "contract renewals"),
        ("qbr", "qbrs", "business reviews"),
        ("playbook", "playbooks", "success playbooks"),
        ("nps_survey", "nps_surveys", "NPS responses"),
    ],
    "infra": [
        ("deployment", "deployments", "service deployments"),
        ("service", "services", "running services"),
        ("on_call", "on_call_shifts", "on-call rotations"),
        ("cost_report", "cost_reports", "cloud spend"),
        ("status_page", "status_pages", "public status"),
    ],
    "legal": [
        ("matter", "matters", "legal matters"),
        ("nda", "ndas", "non-disclosure agreements"),
        ("dpa", "dpas", "data processing agreements"),
        ("trademark", "trademarks", "trademarks"),
    ],
    "inventory": [
        ("sku", "skus", "stock keeping units"),
        ("warehouse", "warehouses", "warehouses"),
        ("shipment", "shipments", "outbound shipments"),
        ("return", "returns", "customer returns"),
    ],
    "partners": [
        ("partner", "partners", "channel partners"),
        ("referral", "referrals", "partner referrals"),
        ("payout", "payouts", "partner payouts"),
        ("integration", "integrations", "partner integrations"),
    ],
}
SYSTEMS.update(
    {
        "finance": [
            ("budget", "budgets", "department budgets"),
            ("expense", "expenses", "expense claims"),
            ("forecast", "forecasts", "cash forecast"),
            ("revenue_report", "revenue_reports", "revenue by month"),
        ],
        "support_ops": [
            ("queue", "queues", "support queues"),
            ("macro", "macros", "canned replies"),
            ("sla", "slas", "response time targets"),
            ("escalation", "escalations", "escalated cases"),
            ("csat_survey", "csat_surveys", "satisfaction surveys"),
        ],
        "product": [
            ("feature", "features", "product features"),
            ("roadmap", "roadmaps", "roadmap items"),
            ("release", "releases", "product releases"),
            ("feedback", "feedback_items", "customer feedback"),
        ],
        "data": [
            ("pipeline", "pipelines", "data pipelines"),
            ("table", "tables", "warehouse tables"),
            ("job", "jobs", "scheduled jobs"),
            ("quality_check", "quality_checks", "data quality checks"),
        ],
        "facilities": [
            ("office", "offices", "office locations"),
            ("desk", "desks", "desk bookings"),
            ("visitor", "visitors", "office visitors"),
        ],
        "travel": [
            ("trip", "trips", "business trips"),
            ("booking", "bookings", "flight and hotel bookings"),
            ("reimbursement", "reimbursements", "travel reimbursements"),
        ],
        "subscriptions": [
            ("plan", "plans", "price plans"),
            ("coupon", "coupons", "discount coupons"),
            ("trial", "trials", "free trials"),
            ("usage_record", "usage_records", "metered usage"),
        ],
    }
)
FINANCIAL_EXTRA = {"expense", "reimbursement", "coupon"}

READ_VERBS = [
    ("list", "List {plural} ({word}), newest first, with optional filters."),
    ("get", "Get one {singular} ({word}) by id with its details."),
    ("search", "Search {plural} ({word}) by name, owner or status."),
    ("summary", "Summarize {plural} ({word}) by month: counts, totals and change from the month before."),
    ("trend", "Weekly trend of {plural} ({word}) over the last quarter."),
    ("export_report", "Build a report of {plural} ({word}) for a date range."),
]
WRITE_VERBS = [
    ("create", "Create a {singular} ({word}).", Risk.WRITE),
    ("update", "Update fields of a {singular} ({word}).", Risk.WRITE),
    ("archive", "Archive a {singular} ({word}); it can be restored later.", Risk.DESTRUCTIVE),
    ("approve", "Approve a pending {singular} ({word}).", Risk.WRITE),
    ("delete", "Permanently delete a {singular} ({word}).", Risk.DESTRUCTIVE),
]
FINANCIAL = {
    "invoice",
    "payment_run",
    "commission",
    "payroll_run",
    "purchase_order",
    "payout",
} | FINANCIAL_EXTRA
FILTERS = [
    ("status", "str", "filter by status"),
    ("owner", "str", "filter by owner user name"),
    ("since", "str", "ISO date; only records on or after it"),
    ("max_rows", "int", "maximum rows, up to 50"),
]


def _read(
    system: str, singular: str, plural: str, word: str, verb: str, text: str, rng: random.Random
) -> Capability:
    if verb == "get":
        params = (Parameter(f"{singular}_id", "str", True, f"id of the {singular}"),)
    elif verb in ("summary", "trend", "export_report"):
        params = (
            Parameter("months" if verb == "summary" else "weeks", "int", False, "how far back"),
            Parameter("segment", "str", False, "optional segment filter"),
        )
    else:
        k = rng.randint(1, len(FILTERS))
        params = tuple(Parameter(n, t, False, d) for n, t, d in rng.sample(FILTERS, k))
        if verb == "search":
            params = (Parameter("query", "str", True, "text to match"), *params)
    out = (
        f"list[{singular.title().replace('_', '')}]"
        if verb not in ("get",)
        else singular.title().replace("_", "")
    )
    name = f"{system}.{plural if verb in ('list', 'search') else singular}.{verb}"
    return Capability(
        name,
        text.format(singular=singular.replace("_", " "), plural=plural.replace("_", " "), word=word),
        params,
        out,
        Risk.READ,
        frozenset({f"{system}.read"}),
    )


def _write(system: str, singular: str, word: str, verb: str, text: str, risk: Risk) -> Capability:
    params = [Parameter(f"{singular}_id", "str", verb != "create", f"id of the {singular}")]
    if verb in ("create", "update"):
        params += [
            Parameter("name", "str", verb == "create", "display name"),
            Parameter("owner", "str", False, "owner user name"),
        ]
    amount = None
    if singular in FINANCIAL and verb in ("create", "approve"):
        risk, amount = Risk.FINANCIAL, "amount_cents"
        params.append(Parameter("amount_cents", "int", True, "amount in cents"))
    return Capability(
        f"{system}.{singular}.{verb}",
        text.format(singular=singular.replace("_", " "), word=word),
        tuple(params),
        singular.title().replace("_", ""),
        risk,
        frozenset({f"{system}.read", f"{system}.write"}),
        amount_field=amount,
    )


def synthetic_catalogue(seed: int = 7) -> list[Capability]:
    """Every generated capability in a fixed, shuffled order; take a prefix for a given catalogue size."""
    rng = random.Random(seed)
    caps: list[Capability] = []
    for system, resources in SYSTEMS.items():
        for singular, plural, word in resources:
            for verb, text in READ_VERBS:
                caps.append(_read(system, singular, plural, word, verb, text, rng))
            for verb, text, risk in WRITE_VERBS:
                caps.append(_write(system, singular, word, verb, text, risk))
    names: set[str] = set()
    unique = [c for c in caps if not (c.name in names or names.add(c.name))]  # type: ignore[func-returns-value]
    rng.shuffle(unique)
    return unique


__all__ = ["synthetic_catalogue"]
