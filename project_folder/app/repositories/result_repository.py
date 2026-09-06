import uuid

from sqlalchemy import func, select

from app.models.result import Result
from app.repositories.base import BaseRepository


class ResultRepository(BaseRepository[Result]):
    model = Result

    async def list_for_execution(self, execution_id: uuid.UUID) -> list[Result]:
        """Every round, oldest first — the 版本演進 (v01 / v02 / 最終) history."""
        result = await self.session.execute(
            select(Result)
            .where(Result.execution_id == execution_id)
            .order_by(Result.round_no)
        )
        return list(result.scalars().all())

    async def next_round_no(self, execution_id: uuid.UUID) -> int:
        """Caller must already hold a lock on the execution row: round_no is unique per
        execution, so two unsynchronized appends would collide on the same number."""
        result = await self.session.execute(
            select(func.coalesce(func.max(Result.round_no), 0)).where(
                Result.execution_id == execution_id
            )
        )
        return result.scalar_one() + 1

    async def latest_for_executions(
        self, execution_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Result]:
        if not execution_ids:
            return {}
        result = await self.session.execute(
            select(Result)
            .where(Result.execution_id.in_(execution_ids))
            .distinct(Result.execution_id)
            .order_by(Result.execution_id, Result.round_no.desc())
        )
        return {row.execution_id: row for row in result.scalars().all()}

    async def counts_for_executions(
        self, execution_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not execution_ids:
            return {}
        result = await self.session.execute(
            select(Result.execution_id, func.count())
            .where(Result.execution_id.in_(execution_ids))
            .group_by(Result.execution_id)
        )
        return {row[0]: row[1] for row in result}
