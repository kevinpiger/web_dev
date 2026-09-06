import uuid

from sqlalchemy import update

from app.core.enums import OutboxEventStatus
from app.models.outbox_event import OutboxEvent
from app.repositories.base import BaseRepository

CANCELLED_ERROR = "EXECUTION_CANCELLED"


class OutboxEventRepository(BaseRepository[OutboxEvent]):
    model = OutboxEvent

    async def abandon_pending_for_executions(self, execution_ids: list[uuid.UUID]) -> int:
        """Stop un-published events from ever reaching the queue.

        The frozen enum has no CANCELLED value, so a cancelled-before-publish event is
        recorded as FAILED with an explicit last_error rather than left PENDING for the
        publisher to pick up.
        """
        if not execution_ids:
            return 0

        result = await self.session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.execution_id.in_(execution_ids),
                OutboxEvent.status == OutboxEventStatus.PENDING.value,
            )
            .values(status=OutboxEventStatus.FAILED.value, last_error=CANCELLED_ERROR)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount or 0
