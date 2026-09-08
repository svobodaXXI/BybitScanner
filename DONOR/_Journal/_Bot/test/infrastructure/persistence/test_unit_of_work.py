import asyncio

import pytest

from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork


class FakeSession:
    def __init__(self):
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    async def begin(self):
        self.begin_count += 1

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1

    async def close(self):
        self.close_count += 1


class Repo:
    def __init__(self, session):
        self.session = session


def test_sqlalchemy_uow_shares_one_session_and_explicit_commit_closes(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyTradeRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyExecutionRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyAccountRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyInstrumentRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyCustomFieldRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyTradeCustomValueRepository", Repo)

    async def run():
        uow = SqlAlchemyUnitOfWork(lambda: session)
        async with uow:
            assert {id(repo.session) for repo in (
                uow.trades,
                uow.executions,
                uow.accounts,
                uow.instruments,
                uow.custom_fields,
                uow.custom_values,
            )} == {id(session)}
            await uow.commit()

    asyncio.run(run())
    assert session.begin_count == 1
    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.close_count == 1


def test_sqlalchemy_uow_rolls_back_on_failure_and_never_hides_commit():
    session = FakeSession()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyTradeRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyExecutionRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyAccountRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyInstrumentRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyCustomFieldRepository", Repo)
    monkeypatch.setattr("app.infrastructure.persistence.unit_of_work.SqlAlchemyTradeCustomValueRepository", Repo)
    try:
        async def run():
            uow = SqlAlchemyUnitOfWork(lambda: session)
            async with uow:
                raise RuntimeError("forced failure")
        with pytest.raises(RuntimeError):
            asyncio.run(run())
    finally:
        monkeypatch.undo()
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.close_count == 1
