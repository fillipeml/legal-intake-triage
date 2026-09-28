"""How a demand closes.

By e-mail: the lawyer answers the client in the same thread with the intake account in
copy. Four conditions, all required: the message reached the intake mailbox; it is in the
thread of a demand; the sender is internal; the demand is in execution. That closing
records the real date of the reply to the client, the source of the response-time KPI.

By the board: the lawyer marked the task complete and forgot the copy. A periodic sync
closes the demand without a reply date; the dashboard measures that gap."""

from __future__ import annotations

from datetime import datetime

from ..models import ClosedVia, DemandStatus, InboundMessage
from ..services import Services


def try_close_by_reply(services: Services, message: InboundMessage, at: datetime) -> str | None:
    settings = services.settings
    if not settings.is_internal(message.sender):
        return None
    demand = services.registry.by_conversation(message.conversation_id)
    if demand is None or demand.status != DemandStatus.IN_EXECUTION:
        return None
    demand.status = DemandStatus.DONE
    demand.replied_at = message.received_at
    demand.closed_via = ClosedVia.EMAIL
    demand.closed_at = message.received_at
    services.registry.update(demand)
    if demand.board_task_id:
        services.board.complete(demand.board_task_id, message.received_at)
    return f"{demand.id} closed by the reply of {message.sender}"


def sync_from_board(services: Services, at: datetime) -> list[str]:
    closed: list[str] = []
    for demand in services.registry.list(status=DemandStatus.IN_EXECUTION):
        if not demand.board_task_id:
            continue
        task = services.board.get(demand.board_task_id)
        if task and task.percent_complete >= 100:
            demand.status = DemandStatus.DONE
            demand.closed_via = ClosedVia.BOARD
            demand.closed_at = task.completed_at or at
            services.registry.update(demand)
            closed.append(f"{demand.id} closed from the board (task {task.id}), no reply date")
    return closed
