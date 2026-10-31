"""People capabilities: the directory is open to staff; payroll needs hr.payroll.read."""

from __future__ import annotations

from typing import Any

from bizops.application.catalogue import capability
from bizops.domain.models import Risk
from bizops.domain.models.capability import CallContext
from bizops.infrastructure.connectors._base import limit, rows


class PeopleConnector:
    @capability(Risk.READ, {"people.read"}, name="employees.search", output="list[Employee]")
    async def employees_search(
        self, ctx: CallContext, query: str | None = None, department: str | None = None, max_rows: int = 20
    ) -> list[dict[str, Any]]:
        """Company directory: employees by name fragment or department, with title and manager. No pay data.

        query: case-insensitive name fragment
        department: Engineering, Sales, Support, Finance, Marketing, Product or People Ops
        max_rows: maximum rows to return, up to 50
        """
        where, params = ["1 = 1"], []
        if query:
            where.append("e.name LIKE ?")
            params.append(f"%{query}%")
        if department:
            where.append("e.department = ?")
            params.append(department)
        return rows(
            ctx,
            "SELECT e.id, e.name, e.department, e.title, m.name AS manager, e.started_at "  # noqa: S608
            "FROM people_employees e LEFT JOIN people_employees m ON m.id = e.manager_id "
            f"WHERE {' AND '.join(where)} ORDER BY e.name LIMIT ?",
            (*params, limit(max_rows)),
        )

    @capability(
        Risk.READ,
        {"people.read", "hr.payroll.read"},
        name="payroll.by_department",
        output="list[DepartmentPayroll]",
    )
    async def payroll_by_department(
        self, ctx: CallContext, department: str | None = None
    ) -> list[dict[str, Any]]:
        """Annual base payroll per department: headcount, total and average salary. Restricted payroll data.

        department: optional; one department instead of all
        """
        sql = (
            "SELECT e.department, COUNT(*) AS headcount, SUM(s.base_cents) AS total_base_cents, "
            "CAST(AVG(s.base_cents) AS INTEGER) AS avg_base_cents FROM people_employees e "
            "JOIN people_salaries s ON s.employee_id = e.id"
        )
        params: tuple[Any, ...] = ()
        if department:
            sql, params = sql + " WHERE e.department = ?", (department,)
        return rows(ctx, sql + " GROUP BY e.department ORDER BY total_base_cents DESC", params)


__all__ = ["PeopleConnector"]
