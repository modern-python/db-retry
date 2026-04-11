import dataclasses
import typing

from sqlalchemy.engine.interfaces import IsolationLevel
from sqlalchemy.ext import asyncio as sa_async


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class Transaction:
    session: sa_async.AsyncSession
    isolation_level: IsolationLevel | None = None

    async def __aenter__(self) -> typing.Self:
        if self.isolation_level:
            await self.session.connection(execution_options={"isolation_level": self.isolation_level})

        if not self.session.in_transaction():
            await self.session.begin()
        return self

    async def __aexit__(self, exc_type: object, *args: object, **kwargs: object) -> None:
        if self.session.in_transaction():
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
