import contextlib
import typing

import pytest
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext import asyncio as sa_async

from db_retry import Transaction


class _Base(orm.DeclarativeBase):
    pass


class _Item(_Base):
    __tablename__ = "transaction_items"
    id: orm.Mapped[int] = orm.mapped_column(primary_key=True)


@pytest.fixture
async def transaction(async_engine: sa_async.AsyncEngine) -> typing.AsyncIterator[Transaction]:
    async with sa_async.AsyncSession(async_engine, expire_on_commit=False, autoflush=False) as session:
        yield Transaction(session=session)


@pytest.fixture
async def transaction_serializable(async_engine: sa_async.AsyncEngine) -> typing.AsyncIterator[Transaction]:
    async with sa_async.AsyncSession(async_engine, expire_on_commit=False, autoflush=False) as session:
        yield Transaction(session=session, isolation_level="SERIALIZABLE")


async def test_transaction_with_commit(transaction: Transaction) -> None:
    async with transaction:
        assert transaction.session.in_transaction()
        await transaction.commit()
        assert not transaction.session.in_transaction()


async def test_transaction_serializable_with_commit(transaction_serializable: Transaction) -> None:
    async with transaction_serializable:
        assert transaction_serializable.session.in_transaction()
        await transaction_serializable.commit()
        assert not transaction_serializable.session.in_transaction()


async def test_transaction_with_rollback(transaction: Transaction) -> None:
    async with transaction:
        assert transaction.session.in_transaction()
        await transaction.rollback()
        assert not transaction.session.in_transaction()


async def test_transaction_without_commit(transaction: Transaction) -> None:
    async with transaction:
        assert transaction.session.in_transaction()
    assert not transaction.session.in_transaction()


async def test_transaction_with_exception(transaction: Transaction) -> None:
    with contextlib.suppress(Exception):
        async with transaction:
            assert transaction.session.in_transaction()
            msg: typing.Final = "some error"
            raise Exception(msg)  # noqa: TRY002
    assert not transaction.session.in_transaction()


@pytest.mark.usefixtures("lost_pooled_connection")
async def test_entering_rolls_back_a_transaction_whose_connection_was_lost(transaction: Transaction) -> None:
    with pytest.raises(DBAPIError) as lost:
        await transaction.session.scalar(sqlalchemy.text("SELECT 1"))
    assert lost.value.connection_invalidated
    async with transaction:
        assert await transaction.session.scalar(sqlalchemy.text("SELECT 1")) == 1


async def test_entering_joins_a_live_transaction(transaction: Transaction) -> None:
    await transaction.session.execute(sqlalchemy.text("CREATE TEMP TABLE joined (x int)"))
    await transaction.session.execute(sqlalchemy.text("INSERT INTO joined VALUES (1)"))
    async with transaction:
        assert await transaction.session.scalar(sqlalchemy.text("SELECT count(*) FROM joined")) == 1


@pytest.mark.usefixtures("lost_pooled_connection")
async def test_a_recovered_transaction_keeps_its_isolation_level(transaction_serializable: Transaction) -> None:
    with pytest.raises(DBAPIError):
        await transaction_serializable.session.scalar(sqlalchemy.text("SELECT 1"))
    async with transaction_serializable:
        level: typing.Final = await transaction_serializable.session.scalar(
            sqlalchemy.text("SHOW transaction_isolation")
        )
        assert level == "serializable"


async def test_entering_after_autobegin_keeps_the_isolation_level(transaction_serializable: Transaction) -> None:
    transaction_serializable.session.add(_Item(id=1))
    assert transaction_serializable.session.in_transaction()
    async with transaction_serializable:
        level: typing.Final = await transaction_serializable.session.scalar(
            sqlalchemy.text("SHOW transaction_isolation")
        )
        assert level == "serializable"


async def test_entering_a_session_with_only_mapper_binds(async_engine: sa_async.AsyncEngine) -> None:
    async with sa_async.AsyncSession(binds={_Item: async_engine}, autoflush=False) as session:
        session.add(_Item(id=1))
        async with Transaction(session=session):
            assert session.in_transaction()


@pytest.mark.usefixtures("lost_pooled_connection")
async def test_entering_rolls_back_a_transaction_whose_flush_lost_the_connection(transaction: Transaction) -> None:
    transaction.session.add(_Item(id=1))
    with pytest.raises(DBAPIError) as lost:
        await transaction.session.flush()
    assert lost.value.connection_invalidated
    assert not transaction.session.is_active
    async with transaction:
        assert await transaction.session.scalar(sqlalchemy.text("SELECT 1")) == 1
