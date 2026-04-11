import os
import typing

import pytest
from sqlalchemy.ext import asyncio as sa_async


@pytest.fixture
async def async_engine() -> typing.AsyncIterator[sa_async.AsyncEngine]:
    engine: typing.Final = sa_async.create_async_engine(url=os.environ["DB_DSN"], echo=True, echo_pool=True)
    try:
        yield engine
    finally:
        await engine.dispose()
