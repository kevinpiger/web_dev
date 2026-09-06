import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.core.enums import ParseItemStatus
from app.models.analysis_task import AnalysisTask
from app.models.execution import Execution
from app.models.parse_item import ParseItem
from app.models.result import Result
from app.repositories.base import BaseRepository


class AnalysisTaskRepository(BaseRepository[AnalysisTask]):
    model = AnalysisTask

    async def get_owned(self, task_id: uuid.UUID, user_id: uuid.UUID) -> AnalysisTask | None:
        """None both when missing and when owned by someone else — callers map both to 404."""
        result = await self.session.execute(
            select(AnalysisTask).where(
                AnalysisTask.id == task_id,
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_owned_for_update(
        self, task_id: uuid.UUID, user_id: uuid.UUID
    ) -> AnalysisTask | None:
        """Row-locked read, so two concurrent dispatch/cancel calls can't interleave."""
        result = await self.session.execute(
            select(AnalysisTask)
            .where(
                AnalysisTask.id == task_id,
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_any_owned(self, task_id: uuid.UUID, user_id: uuid.UUID) -> AnalysisTask | None:
        """Includes soft-deleted rows, so delete can tell 'already gone' from 'never yours'."""
        result = await self.session.execute(
            select(AnalysisTask).where(
                AnalysisTask.id == task_id, AnalysisTask.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[AnalysisTask]:
        """All non-deleted tasks owned by the caller; no pagination or total query."""
        result = await self.session.execute(
            select(AnalysisTask).where(
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def activity_times(
        self, task_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[datetime | None, datetime | None]]:
        """First actual start and latest child activity, including soft deletions.

        Historical runs still contribute to the task's first start/activity times;
        only progress uses the latest execution of each eligible parse item.
        """
        if not task_ids:
            return {}
        result = await self.session.execute(
            select(
                ParseItem.task_id,
                func.min(Execution.started_at),
                func.max(func.greatest(
                    ParseItem.updated_at,
                    ParseItem.deleted_at,
                    Execution.updated_at,
                    Result.updated_at,
                )),
            )
            .select_from(ParseItem)
            .outerjoin(Execution, Execution.parse_id == ParseItem.id)
            .outerjoin(Result, Result.execution_id == Execution.id)
            .where(ParseItem.task_id.in_(task_ids))
            .group_by(ParseItem.task_id)
        )
        return {task_id: (started_at, updated_at) for task_id, started_at, updated_at in result}

    async def item_counts(self, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Active DRAFT + READY parse_item count per task."""
        if not task_ids:
            return {}
        result = await self.session.execute(
            select(ParseItem.task_id, func.count())
            .where(
                ParseItem.task_id.in_(task_ids),
                ParseItem.status.in_((ParseItemStatus.DRAFT.value, ParseItemStatus.READY.value)),
                ParseItem.deleted_at.is_(None),
            )
            .group_by(ParseItem.task_id)
        )
        return {row[0]: row[1] for row in result}

    async def execution_status_counts(
        self, task_ids: list[uuid.UUID], *, eligible_only: bool = False
    ) -> dict[uuid.UUID, dict[str, int]]:
        """Per task, count parse items by the status of their *latest* execution.

        Re-runs create additional executions for the same parse item (freeze §15), so
        progress must look at the newest one per item, not at every row.
        """
        if not task_ids:
            return {}

        filters = [ParseItem.task_id.in_(task_ids), ParseItem.deleted_at.is_(None)]
        if eligible_only:
            filters.append(ParseItem.status.in_((
                ParseItemStatus.DRAFT.value, ParseItemStatus.READY.value,
            )))
        latest_per_item = (
            select(
                ParseItem.task_id.label("task_id"),
                Execution.parse_id.label("parse_id"),
                Execution.status.label("status"),
            )
            .join(Execution, Execution.parse_id == ParseItem.id)
            .where(*filters)
            .distinct(Execution.parse_id)
            .order_by(Execution.parse_id, Execution.created_at.desc())
            .subquery()
        )

        result = await self.session.execute(
            select(latest_per_item.c.task_id, latest_per_item.c.status, func.count())
            .group_by(latest_per_item.c.task_id, latest_per_item.c.status)
        )

        counts: dict[uuid.UUID, dict[str, int]] = {}
        for task_id, status, count in result:
            counts.setdefault(task_id, {})[status] = count
        return counts
