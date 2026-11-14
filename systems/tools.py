"""Mock business systems: orders, payments, CRM and an email outbox.

Plain functions over the sys_* collections. They enforce nothing. All policy
lives in the gateway, which is the only caller.
"""

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from gateway.canonical import now


def orders_get(db, order_id: str):
    return db.sys_orders.find_one({"_id": order_id})


def _payment(db, doc: dict) -> dict:
    """Insert once per idempotency key. A retry returns the original record."""
    try:
        db.sys_payments.insert_one(doc)
        return doc
    except DuplicateKeyError:
        return db.sys_payments.find_one({"idempotency_key": doc["idempotency_key"]})


def payments_refund(db, order_id: str, amount_cents: int, idempotency_key: str,
                    destination: str = "original") -> dict:
    """Refund an order. `destination` is "original" (the payment method used) or another card."""
    return _payment(db, {"_id": f"rf_{idempotency_key[:16]}", "type": "refund", "order_id": order_id,
                         "amount_cents": amount_cents, "destination": destination, "status": "settled",
                         "idempotency_key": idempotency_key, "created_at": now()})


def payments_reverse(db, refund_id: str, idempotency_key: str) -> dict:
    """Compensation for a refund: a reversal entry, and the refund is marked reversed."""
    refund = db.sys_payments.find_one({"_id": refund_id, "type": "refund"})
    if not refund:
        raise ValueError(f"no refund {refund_id}")
    reversal = _payment(db, {"_id": f"rv_{idempotency_key[:16]}", "type": "reversal", "reverses": refund_id,
                             "order_id": refund["order_id"], "amount_cents": refund["amount_cents"],
                             "status": "settled", "idempotency_key": idempotency_key, "created_at": now()})
    db.sys_payments.update_one({"_id": refund_id}, {"$set": {"status": "reversed"}})
    return reversal


def payments_transfer(db, account: str, amount_cents: int, idempotency_key: str) -> dict:
    return _payment(db, {"_id": f"tr_{idempotency_key[:16]}", "type": "transfer", "account": account,
                         "amount_cents": amount_cents, "status": "settled",
                         "idempotency_key": idempotency_key, "created_at": now()})


def crm_update_contact(db, customer_id: str, fields: dict) -> dict:
    after = db.sys_crm.find_one_and_update({"_id": customer_id}, {"$set": fields},
                                           return_document=ReturnDocument.AFTER)
    if not after:
        raise ValueError(f"no customer {customer_id}")
    return after


def email_send(db, customer_id: str, subject: str, body: str, idempotency_key: str) -> dict:
    doc = {"_id": f"em_{idempotency_key[:16]}", "customer_id": customer_id, "subject": subject, "body": body,
           "sent_at": now()}
    try:
        db.sys_outbox.insert_one(doc)
    except DuplicateKeyError:
        pass
    return doc


# reversible: True (can be compensated), False (cannot be undone), None (read only).
# resource: which record policy needs facts from, and the argument that names it.
TOOLS = {
    "orders.get": {"fn": orders_get, "reversible": None, "resource": ("sys_orders", "order_id")},
    "payments.refund": {"fn": payments_refund, "reversible": True, "resource": ("sys_orders", "order_id")},
    "payments.transfer": {"fn": payments_transfer, "reversible": False, "resource": None},
    "crm.update_contact": {"fn": crm_update_contact, "reversible": True, "resource": ("sys_crm", "customer_id")},
    "email.send": {"fn": email_send, "reversible": False, "resource": ("sys_crm", "customer_id")},
}
