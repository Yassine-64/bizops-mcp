"""Engineering capabilities: projects, issues, incidents."""

from __future__ import annotations

from datetime import date
from typing import Any

from bizops.application.catalogue import capability
from bizops.domain.exceptions import InvalidArgument
from bizops.domain.models import Risk
from bizops.domain.models.capability import CallContext
from bizops.infrastructure.connectors._base import conn, limit, one, rows

READ = {"engineering.read"}
PRIORITIES = ("P1", "P2", "P3")


class EngineeringConnector:
    @capability(Risk.READ, READ, name="projects.list", output="list[Project]")
    async def projects_list(self, ctx: CallContext) -> list[dict[str, Any]]:
        """Active projects with owner, due date and open issue counts by priority."""
        return rows(
            ctx,
            "SELECT p.id, p.name, p.owner, p.due_at, "
            "SUM(CASE WHEN i.status = 'open' AND i.priority = 'P1' THEN 1 ELSE 0 END) AS open_p1, "
            "SUM(CASE WHEN i.status = 'open' THEN 1 ELSE 0 END) AS open_total "
            "FROM eng_projects p LEFT JOIN eng_issues i ON i.project_id = p.id "
            "WHERE p.status = 'active' GROUP BY p.id ORDER BY p.due_at",
        )

    @capability(Risk.READ, READ, name="project.risk", output="ProjectRisk")
    async def project_risk(self, ctx: CallContext, project_id: str) -> dict[str, Any]:
        """Delivery risk of one project: days to due date, open P1s, and recent close rate.

        project_id: e.g. proj_2
        """
        p = one(ctx, "SELECT * FROM eng_projects WHERE id = ?", (project_id,), f"project {project_id}")
        stats = (
            conn(ctx)
            .execute(
                "SELECT SUM(CASE WHEN status = 'open' AND priority = 'P1' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status = 'closed' AND closed_at >= date(?, '-28 days') THEN 1 ELSE 0 END) "
                "FROM eng_issues WHERE project_id = ?",
                (ctx.today.isoformat(), project_id),
            )
            .fetchone()
        )
        days_left = (date.fromisoformat(p["due_at"]) - ctx.today).days
        return {
            **p,
            "days_to_due": days_left,
            "open_p1": stats[0] or 0,
            "open_total": stats[1] or 0,
            "closed_last_28_days": stats[2] or 0,
        }

    @capability(Risk.READ, READ, name="issues.list", output="list[Issue]")
    async def issues_list(
        self, ctx: CallContext, project_id: str, status: str | None = None, priority: str | None = None
    ) -> list[dict[str, Any]]:
        """Issues of one project, highest priority first.

        project_id: e.g. proj_2
        status: open or closed
        priority: P1, P2 or P3
        """
        where, params = ["project_id = ?"], [project_id]
        if status:
            where.append("status = ?")
            params.append(status)
        if priority:
            where.append("priority = ?")
            params.append(priority)
        return rows(
            ctx,
            f"SELECT id, title, priority, status, created_at, closed_at FROM eng_issues "  # noqa: S608
            f"WHERE {' AND '.join(where)} ORDER BY priority, created_at LIMIT ?",
            (*params, limit(50)),
        )

    @capability(Risk.READ, READ, name="incidents.list", output="list[Incident]")
    async def incidents_list(
        self, ctx: CallContext, since: str | None = None, severity: str | None = None
    ) -> Any:
        """Incidents with start, end, affected services and root cause, newest first.

        since: ISO date; only incidents that started on or after it
        severity: sev1, sev2 or sev3
        """
        where, params = ["1 = 1"], []
        if since:
            where.append("started_at >= ?")
            params.append(since)
        if severity:
            where.append("severity = ?")
            params.append(severity)
        return rows(
            ctx,
            f"SELECT * FROM eng_incidents WHERE {' AND '.join(where)} "  # noqa: S608
            "ORDER BY started_at DESC",
            tuple(params),
        )

    @capability(
        Risk.WRITE,
        {"engineering.read", "engineering.write"},
        name="issue.create",
        idempotent=True,
        output="Issue",
    )
    async def issue_create(
        self, ctx: CallContext, project_id: str, title: str, priority: str
    ) -> dict[str, Any]:
        """Create an issue in a project. Idempotent on the server-minted operation id.

        project_id: e.g. proj_2
        title: issue title
        priority: P1, P2 or P3
        """
        if priority not in PRIORITIES:
            raise InvalidArgument("priority must be P1, P2 or P3")
        db = conn(ctx)
        existing = db.execute(
            "SELECT * FROM eng_issues WHERE operation_id = ?", (ctx.operation_id,)
        ).fetchone()
        if existing:
            return {**dict(existing), "replayed": True}
        one(ctx, "SELECT id FROM eng_projects WHERE id = ?", (project_id,), f"project {project_id}")
        n = db.execute("SELECT COUNT(*) FROM eng_issues").fetchone()[0] + 1
        issue = {
            "id": f"iss_{n:03d}",
            "project_id": project_id,
            "title": title,
            "priority": priority,
            "status": "open",
            "created_at": ctx.today.isoformat(),
            "closed_at": None,
            "operation_id": ctx.operation_id,
        }
        db.execute(
            "INSERT INTO eng_issues VALUES (:id, :project_id, :title, :priority, :status, :created_at, "
            ":closed_at, :operation_id)",
            issue,
        )
        return {**issue, "replayed": False}


__all__ = ["EngineeringConnector"]
