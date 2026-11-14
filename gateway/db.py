"""Connection to the hackathon Atlas sandbox cluster. The URI comes from .env."""

import os
from functools import lru_cache

from pymongo import MongoClient


@lru_cache
def client() -> MongoClient:
    uri = os.environ.get("MONGODB_URI", "")
    if not uri or "PASTE_" in uri or "<db_password>" in uri:
        raise SystemExit("MONGODB_URI is not set. Fill in .env (see .env.example).")
    return MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=10000, appname="warrant")


def get_db():
    return client()[os.environ.get("MONGODB_DB", "warrant")]
