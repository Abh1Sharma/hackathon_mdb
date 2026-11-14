"""Kill switch fast path: a change stream on `runs` tells this process about a kill without polling.

Correctness never depends on it. The decision transaction re-reads the run, so a
killed run cannot get a warrant even if this stream lags or drops.
"""

import threading
import time

from pymongo.errors import PyMongoError

_killed: set[str] = set()
_thread = None


def start(db) -> None:
    global _thread
    if _thread:
        return

    def watch():
        pipeline = [{"$match": {"operationType": "update",
                                "updateDescription.updatedFields.status": "killed"}}]
        while True:
            try:
                with db.runs.watch(pipeline) as stream:
                    _killed.update(r["_id"] for r in db.runs.find({"status": "killed"}, {"_id": 1}))
                    for event in stream:
                        _killed.add(event["documentKey"]["_id"])
            except PyMongoError:
                time.sleep(1)

    _thread = threading.Thread(target=watch, daemon=True, name="killswitch")
    _thread.start()


def is_killed(run_id: str) -> bool:
    return run_id in _killed
