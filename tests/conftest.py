"""Tests run against the Atlas sandbox, in their own database so they never wipe demo state."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

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


RESULTS = []


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        RESULTS.append({"id": report.nodeid, "outcome": report.outcome, "seconds": round(report.duration, 2)})


def pytest_sessionfinish(session, exitstatus):
    """`WARRANT_RECEIPT=1 pytest` writes what passed to docs/evidence/tests.json, for the console's Proof tab."""
    if os.environ.get("WARRANT_RECEIPT") != "1":
        return
    receipt = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "database": os.environ["MONGODB_DB"],
               "passed": sum(r["outcome"] == "passed" for r in RESULTS),
               "failed": sum(r["outcome"] != "passed" for r in RESULTS),
               "seconds": round(sum(r["seconds"] for r in RESULTS)), "cases": RESULTS}
    path = Path(__file__).parent.parent / "docs" / "evidence" / "tests.json"
    path.write_text(json.dumps(receipt, indent=1) + "\n")
