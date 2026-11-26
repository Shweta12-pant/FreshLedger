import os

import pytest

from inventory.commands import initialize
from inventory.db import build_engine, store_now
from inventory.models import Base


@pytest.fixture
def today():
    return store_now().date()


@pytest.fixture(params=["sqlite", "mysql"])
def engine(request, tmp_path, today, monkeypatch):
    monkeypatch.delenv("APP_USERNAME", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    url = (
        os.getenv("TEST_MYSQL_URL") if request.param == "mysql" else f"sqlite:///{tmp_path / 'test.db'}"
    )
    if not url:
        pytest.skip("Set TEST_MYSQL_URL to a disposable database to run MySQL tests.")
    database = build_engine(url)
    if request.param == "mysql":
        assert database.url.database == "freshledger_test", "Use a database named freshledger_test."
    Base.metadata.drop_all(database)
    initialize(database, demo=False, today=today)
    yield database
    Base.metadata.drop_all(database)
    database.dispose()
