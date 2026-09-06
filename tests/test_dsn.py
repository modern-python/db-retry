import typing

from db_retry import build_db_dsn, is_dsn_multihost


def test_build_db_dsn() -> None:
    database_name: typing.Final = "new_db_name"
    drivername: typing.Final = "postgresql+asyncpg"
    result_dsn: typing.Final = build_db_dsn(
        db_dsn="postgresql://login:password@/db_placeholder?host=host1&host=host2",
        database_name=database_name,
        drivername=drivername,
    )

    assert database_name in result_dsn
    assert drivername in result_dsn


def test_use_replica_overrides_a_target_session_attrs_already_in_the_dsn() -> None:
    """INVARIANT: ``use_replica`` alone decides ``target_session_attrs``; a value in the DSN never wins.

    Broken by flipping the dict union in ``build_db_dsn`` to ``{"target_session_attrs": ...} |
    db_dsn_query``, which reads as a harmless reordering and makes the stored DSN authoritative
    instead. Only the caller knows whether this particular call is a read that may be served by a
    replica; the DSN is one shared string reused for every call in the process. Under the flip, a
    DSN pinned to ``read-write`` would route every ``use_replica=True`` read to the primary -- an
    invisible load regression, since the reads still succeed -- and one pinned to ``prefer-standby``
    would aim writes at a standby, where they fail. Every other query parameter is deliberately
    carried through, so nothing else about the URL changes to give the flip away.
    """
    dsn: typing.Final = (
        "postgresql://login:password@/db_placeholder"
        "?host=host1&host=host2&target_session_attrs=read-write&application_name=svc"
    )

    replica: typing.Final = build_db_dsn(db_dsn=dsn, database_name="db", use_replica=True)
    assert replica.query["target_session_attrs"] == "prefer-standby"
    assert replica.query["application_name"] == "svc"

    primary: typing.Final = build_db_dsn(
        db_dsn=dsn.replace("read-write", "prefer-standby"), database_name="db", use_replica=False
    )
    assert primary.query["target_session_attrs"] == "read-write"


def test_is_dsn_multihost() -> None:
    assert is_dsn_multihost("postgresql://login:password@/db_placeholder?host=host1&host=host2")
    assert not is_dsn_multihost("postgresql://login:password@/db_placeholder?host=host1")
    assert not is_dsn_multihost("postgresql://login:password@host/db_placeholder")
