"""Precedents: past decisions the gateway can search. Retrieval is added in the search spike."""


def money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def summary(tool: str, amount_cents: int | None = None, region: str | None = None,
            reason: str = "", note: str = "") -> str:
    """Deterministic one-paragraph description of a request. This is the text Atlas embeds.

    It describes only what was asked and on what basis, never the outcome, so a new
    request and a past one are compared like for like.
    """
    head = tool
    if amount_cents:
        head += f" of {money(amount_cents)}"
    if region:
        head += f" for an order in {region}"
    parts = [head + "."]
    if reason:
        parts.append(f"Agent reason: {reason}")
    if note:
        parts.append(f"Customer note: {note}")
    return " ".join(parts)
