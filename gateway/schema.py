"""Collections, validators and indexes for the `warrant` database.

`setup(db)` is idempotent. Search indexes build in the background, so run it
early. `reset` never drops collections, so validators and indexes survive.
"""

from pymongo import ASCENDING
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

STR = {"bsonType": "string"}
INT = {"bsonType": ["int", "long"]}
DATE = {"bsonType": "date"}
OBJ = {"bsonType": "object"}
REFS = {
    "bsonType": "array",
    "items": {"bsonType": "object", "required": ["id", "version"], "additionalProperties": False,
              "properties": {"id": STR, "version": INT}},
}

LEDGER = {"$jsonSchema": {
    "bsonType": "object",
    "additionalProperties": False,
    "required": ["_id", "run_id", "seq", "ts", "type", "actor", "prev_hash", "hash"],
    "properties": {
        "_id": STR,
        "run_id": STR,
        "seq": INT,
        "ts": DATE,
        "type": {"enum": ["decision", "execution", "verification", "approval", "kill", "rollback", "violation",
                          "ruling"]},
        "actor": STR,
        "on_behalf_of": STR,
        "step": INT,
        "tool": STR,
        "reason": STR,
        "decision": {"enum": ["allow", "deny", "step_up"]},
        "policy_refs": REFS,
        "precedent_refs": {"bsonType": "array", "items": OBJ},
        "warrant_id": STR,
        "payload": OBJ,
        "trace_id": STR,
        "prev_hash": STR,
        "hash": STR,
    },
}}

WARRANTS = {"$jsonSchema": {
    "bsonType": "object",
    "additionalProperties": False,
    "required": ["_id", "run_id", "step", "agent_id", "on_behalf_of", "tool", "args_digest",
                 "policy_refs", "status", "issued_at", "expires_at"],
    "properties": {
        "_id": STR,
        "run_id": STR,
        "step": INT,
        "agent_id": STR,
        "on_behalf_of": STR,
        "tool": STR,
        "args_digest": STR,
        "policy_refs": REFS,
        "status": {"enum": ["issued", "used", "revoked", "expired"]},
        "issued_at": DATE,
        "expires_at": DATE,
        "used_at": DATE,
        "approval_id": STR,
    },
}}

RUNS = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["_id", "agent_id", "on_behalf_of", "status", "started_at", "last_hash", "next_seq"],
    "properties": {
        "status": {"enum": ["running", "paused", "killed", "completed", "rolled_back"]},
        "next_seq": INT,
        "last_hash": STR,
    },
}}

APPROVALS = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["_id", "run_id", "step", "request", "status", "created_at", "expires_at"],
    "properties": {
        "status": {"enum": ["pending", "approved", "denied", "expired"]},
        "channel": {"enum": ["web", "voice"]},
    },
}}

PRECEDENTS = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["_id", "tool", "decision", "summary", "seeded", "created_at"],
    "properties": {"decision": {"enum": ["approved", "denied"]}, "summary": STR, "seeded": {"bsonType": "bool"}},
}}

VALIDATED = {"ledger": LEDGER, "warrants": WARRANTS, "runs": RUNS, "approvals": APPROVALS, "precedents": PRECEDENTS}
PLAIN = ["identities", "policies", "sys_tickets", "sys_orders", "sys_payments", "sys_crm", "sys_outbox"]

VEC_INDEX = "precedents_vec"
TEXT_INDEX = "precedents_text"
SEARCH_INDEXES = [
    SearchIndexModel(name=VEC_INDEX, type="vectorSearch", definition={"fields": [
        {"type": "autoEmbed", "modality": "text", "path": "summary", "model": "voyage-4"},
        {"type": "filter", "path": "tool"},
        {"type": "filter", "path": "decision"},
    ]}),
    SearchIndexModel(name=TEXT_INDEX, type="search", definition={"mappings": {"dynamic": False, "fields": {
        "summary": {"type": "string"},
        "outcome_note": {"type": "string"},
        "tool": {"type": "token"},
        "decision": {"type": "token"},
    }}}),
]


def setup(db) -> list[str]:
    """Create or update everything. Returns notes about anything that could not be applied."""
    notes = []
    existing = set(db.list_collection_names())
    for name, validator in VALIDATED.items():
        if name in existing:
            db.command("collMod", name, validator=validator, validationAction="error")
        else:
            db.create_collection(name, validator=validator, validationAction="error")
    for name in PLAIN:
        if name not in existing:
            db.create_collection(name)

    db.identities.create_index("key_hash", unique=True, sparse=True)
    db.warrants.create_index([("run_id", ASCENDING), ("step", ASCENDING)], unique=True)
    # Unused warrants expire on their own. The gateway also checks expires_at at use time,
    # because the TTL monitor only runs about once a minute.
    db.warrants.create_index("expires_at", expireAfterSeconds=0,
                             partialFilterExpression={"status": "issued"}, name="ttl_unused")
    db.ledger.create_index([("run_id", ASCENDING), ("seq", ASCENDING)], unique=True)
    db.approvals.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
    db.sys_payments.create_index("idempotency_key", unique=True, sparse=True)

    for name in ("sys_payments", "sys_crm"):
        try:
            db.command("collMod", name, changeStreamPreAndPostImages={"enabled": True})
        except OperationFailure as e:
            notes.append(f"pre-images not enabled on {name}: {e.details.get('errmsg', e)}")

    have = {ix["name"] for ix in db.precedents.list_search_indexes()}
    for model in SEARCH_INDEXES:
        if model.document["name"] not in have:
            try:
                db.precedents.create_search_index(model)
            except OperationFailure as e:
                notes.append(f"search index {model.document['name']} not created: {e.details.get('errmsg', e)}")
    return notes


def search_status(db) -> dict:
    return {ix["name"]: ("READY" if ix.get("queryable") else ix.get("status", "?"))
            for ix in db.precedents.list_search_indexes()}
