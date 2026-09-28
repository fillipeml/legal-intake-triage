"""Microsoft Planner through Graph (app-only). Mirrors the calls the original flow made:
buckets, tasks, task details (description and checklist) with the etag, labels through
`appliedCategories`. Not exercised by the tests: the SQLite board carries the contract."""

from __future__ import annotations

from datetime import date, datetime

from ..graph import GraphClient
from ..models import Task


class PlannerBoard:
    kind = "planner"

    def __init__(self, graph: GraphClient, *, user_ids: dict[str, str]) -> None:
        """`user_ids`: lawyer name -> Entra user id, resolved once from the area's e-mails."""
        self.graph = graph
        self.user_ids = user_ids
        self.names = {v: k for k, v in user_ids.items()}

    def buckets(self, plan: str) -> list[str]:
        return [b["name"] for b in self.graph.get_paged(f"/planner/plans/{plan}/buckets")]

    def ensure_bucket(self, plan: str, name: str) -> str:
        wanted = name.strip().lower()
        for b in self.graph.get_paged(f"/planner/plans/{plan}/buckets"):
            if b["name"].strip().lower() == wanted:
                return b["id"]
        created = self.graph.post(
            "/planner/buckets", {"name": name.strip(), "planId": plan, "orderHint": " !"}
        )
        return created["id"]

    def create_task(
        self,
        *,
        plan,
        bucket,
        title,
        assignee,
        due_date,
        description,
        checklist,
        label,
        demand_id,
        created_at,
    ) -> Task:
        body: dict = {"planId": plan, "bucketId": bucket, "title": title}
        if due_date:
            body["dueDateTime"] = f"{due_date.isoformat()}T12:00:00Z"
        if assignee and assignee in self.user_ids:
            body["assignments"] = {
                self.user_ids[assignee]: {
                    "@odata.type": "#microsoft.graph.plannerAssignment",
                    "orderHint": " !",
                }
            }
        if label:
            body["appliedCategories"] = {label: True}
        created = self.graph.post("/planner/tasks", body)
        task_id = created["id"]
        details = self.graph.get(f"/planner/tasks/{task_id}/details")
        patch: dict = {"description": description}
        if checklist:
            # the server assigns the order hints; key "1" is the first item as displayed
            patch["checklist"] = {
                str(i + 1): {
                    "@odata.type": "#microsoft.graph.plannerChecklistItem",
                    "title": item,
                    "isChecked": False,
                }
                for i, item in enumerate(checklist)
            }
        self.graph.patch(
            f"/planner/tasks/{task_id}/details", patch, etag=details.get("@odata.etag")
        )
        return Task(
            id=task_id,
            plan=plan,
            bucket=bucket,
            title=title,
            assignee=assignee,
            due_date=due_date,
            created_at=created_at,
            label=label,
            description=description,
            checklist=list(checklist),
            demand_id=demand_id,
        )

    def _to_task(self, t: dict, plan: str) -> Task:
        uids = list((t.get("assignments") or {}).keys())
        assignee = next((self.names[u] for u in uids if u in self.names), None)
        return Task(
            id=t["id"],
            plan=plan,
            bucket=t.get("bucketId") or "",
            title=t.get("title") or "",
            assignee=assignee,
            due_date=date.fromisoformat(t["dueDateTime"][:10]) if t.get("dueDateTime") else None,
            created_at=datetime.fromisoformat(t["createdDateTime"].replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(t["completedDateTime"].replace("Z", "+00:00"))
            if t.get("completedDateTime")
            else None,
            percent_complete=int(t.get("percentComplete") or 0),
            label=next((k for k, v in (t.get("appliedCategories") or {}).items() if v), None),
        )

    def get(self, task_id: str) -> Task | None:
        t = self.graph.get(f"/planner/tasks/{task_id}")
        return self._to_task(t, t.get("planId") or "") if t else None

    def list_tasks(self, plan: str) -> list[Task]:
        return [
            self._to_task(t, plan) for t in self.graph.get_paged(f"/planner/plans/{plan}/tasks")
        ]

    def open_tasks_by_assignee(self, plan: str) -> dict[str, int]:
        load: dict[str, int] = {}
        for task in self.list_tasks(plan):
            if task.percent_complete < 100 and task.assignee:
                load[task.assignee] = load.get(task.assignee, 0) + 1
        return load

    def complete(self, task_id: str, completed_at: datetime) -> None:
        t = self.graph.get(f"/planner/tasks/{task_id}")
        self.graph.patch(
            f"/planner/tasks/{task_id}", {"percentComplete": 100}, etag=t.get("@odata.etag")
        )
