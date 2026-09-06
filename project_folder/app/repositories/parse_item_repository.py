import uuid

from sqlalchemy import func, select

from app.core.enums import ParseItemStatus
from app.models.analysis_task import AnalysisTask
from app.models.asset import Asset
from app.models.execution import Execution
from app.models.parse_item import ParseItem
from app.repositories.base import BaseRepository


class ParseItemRepository(BaseRepository[ParseItem]):
    model = ParseItem

    async def get_owned(
        self, parse_item_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[ParseItem, AnalysisTask, str] | None:
        """Ownership runs through the parent task, which is what carries user_id.

        The asset join has no `deleted_at` filter: a soft-deleted source file should still
        show its name in the parse list rather than blanking out.
        """
        result = await self.session.execute(
            select(ParseItem, AnalysisTask, Asset.file_name)
            .join(AnalysisTask, AnalysisTask.id == ParseItem.task_id)
            .join(Asset, Asset.id == ParseItem.asset_id)
            .where(
                ParseItem.id == parse_item_id,
                ParseItem.deleted_at.is_(None),
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
        )
        row = result.first()
        return (row[0], row[1], row[2]) if row else None

    async def get_any_owned(
        self, parse_item_id: uuid.UUID, user_id: uuid.UUID
    ) -> ParseItem | None:
        """Includes soft-deleted rows, so delete can tell 'already gone' from 'not yours'."""
        result = await self.session.execute(
            select(ParseItem)
            .join(AnalysisTask, AnalysisTask.id == ParseItem.task_id)
            .where(ParseItem.id == parse_item_id, AnalysisTask.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_task(self, task_id: uuid.UUID) -> list[tuple[ParseItem, str]]:
        """Parse items plus their source file name, for the 確認解析清單 table."""
        result = await self.session.execute(
            select(ParseItem, Asset.file_name)
            .join(Asset, Asset.id == ParseItem.asset_id)
            .where(ParseItem.task_id == task_id, ParseItem.deleted_at.is_(None))
            .order_by(Asset.file_name, ParseItem.page_no, ParseItem.created_at)
        )
        return [(row[0], row[1]) for row in result]

    async def list_dispatchable_for_task(self, task_id: uuid.UUID) -> list[ParseItem]:
        result = await self.session.execute(
            select(ParseItem)
            .where(
                ParseItem.task_id == task_id,
                ParseItem.status.in_((ParseItemStatus.DRAFT.value, ParseItemStatus.READY.value)),
                ParseItem.deleted_at.is_(None),
            )
            .order_by(ParseItem.page_no, ParseItem.created_at)
        )
        return list(result.scalars().all())

    async def ids_for_task(self, task_id: uuid.UUID) -> list[uuid.UUID]:
        """Deliberately includes soft-deleted items: 中斷 must also stop executions that
        belong to a subtask the user removed while it was still running."""
        result = await self.session.execute(
            select(ParseItem.id).where(ParseItem.task_id == task_id)
        )
        return list(result.scalars().all())

    async def active_ids_for_task(self, task_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(ParseItem.id).where(
                ParseItem.task_id == task_id, ParseItem.deleted_at.is_(None)
            )
        )
        return list(result.scalars().all())

    async def execution_count(self, parse_item_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Execution).where(Execution.parse_id == parse_item_id)
        )
        return result.scalar_one()
