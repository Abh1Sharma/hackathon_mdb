"""Tests run against the Atlas sandbox, in their own database so they never wipe demo state."""

import os

os.environ["MONGODB_DB"] = "warrant_test"

import pytest  # noqa: E402

from cli import seed  # noqa: E402
from gateway import schema  # noqa: E402
from gateway.db import get_db  # noqa: E402


@pytest.fixture(scope="session")
def _schema():
    db = get_db()
    schema.setup(db)
    return db


@pytest.fixture
def db(_schema):
    seed.reset(_schema)
    return _schema
