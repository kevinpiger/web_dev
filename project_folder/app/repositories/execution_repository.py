import uuid

from sqlalchemy import func, select, update

from app.core.enums import ExecutionStatus
from app.models.analysis_task import AnalysisTask
from app.models.execution import Execution
from app.models.parse_item import ParseItem
from app.repositories.base import BaseRepository
from app.utils.datetime import utcnow

NON_TERMINAL_STATUSES = (
    ExecutionStatus.CREATED.value,
    ExecutionStatus.QUEUED.value,
    ExecutionStatus.RUNNING.value,
)


class ExecutionRepository(BaseRepository[Execution]):
    model = Execution

    def _owned_query(self, execution_id: uuid.UUID, user_id: uuid.UUID):
        return (
            select(Execution)
            .join(ParseItem, ParseItem.id == Execution.parse_id)
            .join(AnalysisTask, AnalysisTask.id == ParseItem.task_id)
            .where(
                Execution.id == execution_id,
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
        )

    async def get_owned(self, execution_id: uuid.UUID, user_id: uuid.UUID) -> Execution | None:
        result = await self.session.execute(self._owned_query(execution_id, user_id))
        return result.scalar_one_or_none()

    async def get_owned_for_update(
        self, execution_id: uuid.UUID, user_id: uuid.UUID
    ) -> Execution | None:
        result = await self.session.execute(
            self._owned_query(execution_id, user_id).with_for_update(of=Execution)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        task_id: uuid.UUID | None = None,
        parse_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[Execution], int]:
        filters = [AnalysisTask.user_id == user_id, AnalysisTask.deleted_at.is_(None)]
        if task_id:
            filters.append(ParseItem.task_id == task_id)
        if parse_id:
            filters.append(Execution.parse_id == parse_id)
        if status:
            filters.append(Execution.status == status)

        base = (
            select(Execution)
            .join(ParseItem, ParseItem.id == Execution.parse_id)
            .join(AnalysisTask, AnalysisTask.id == ParseItem.task_id)
            .where(*filters)
        )

        total_result = await self.session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = total_result.scalar_one()

        items_result = await self.session.execute(
            base.order_by(Execution.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(items_result.scalars().all()), total

    async def latest_for_parse_items(
        self, parse_item_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Execution]:
        """Newest execution per parse item — a re-run adds rows rather than replacing."""
        if not parse_item_ids:
            return {}
        result = await self.session.execute(
            select(Execution)
            .where(Execution.parse_id.in_(parse_item_ids))
            .distinct(Execution.parse_id)
            .order_by(Execution.parse_id, Execution.created_at.desc())
        )
        return {row.parse_id: row for row in result.scalars().all()}

    async def get_latest_for_parse_item_for_update(
        self, parse_item_id: uuid.UUID
    ) -> Execution | None:
        result = await self.session.execute(
            select(Execution)
            .where(Execution.parse_id == parse_item_id)
            .order_by(Execution.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def cancel_non_terminal_for_parse_items(self, parse_item_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        """Mark every still-cancellable execution of these parse items CANCELLED.

        A RUNNING execution is only cancelled in the DB here; the worker is expected to
        check status before writing results back (there is no in-flight kill signal).
        """
        if not parse_item_ids:
            return []

        result = await self.session.execute(
            update(Execution)
            .where(
                Execution.parse_id.in_(parse_item_ids),
                Execution.status.in_(NON_TERMINAL_STATUSES),
            )
            .values(status=ExecutionStatus.CANCELLED.value, finished_at=utcnow())
            .returning(Execution.id)
            .execution_options(synchronize_session=False)
        )
        return list(result.scalars().all())
