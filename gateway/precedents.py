"""Precedents: past decisions, searched with one native Atlas aggregation.

    $rankFusion( $vectorSearch on an autoEmbed index , $search )  ->  $rerank

Atlas embeds the documents and the query text itself (Voyage models), so there
is no embedding code here. Search only supplies facts to the policy engine. It
never decides, and it can only make a decision stricter (see P-009).
"""

import time

from pymongo.errors import OperationFailure

from gateway.schema import TEXT_INDEX, VEC_INDEX

RERANK_MODEL = "rerank-2.5"
_rerank_available = True  # flips to False if the project setting is off


def money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def summary(tool: str, amount_cents: int | None = None, region: str | None = None,
            reason: str = "", note: str = "") -> str:
    """The basis of a request: the agent's stated reason and the untrusted text behind it.

    This is the text Atlas embeds and the text a new request is compared with. Tool, amount
    and region are deliberately left out. They are structured fields (the tool is a filter),
    and when they were part of the text a plain $480 credit looked like a refused $480 request
    just because the amounts matched. The outcome is left out too, so requests are compared
    like for like.
    """
    parts = []
    if reason:
        parts.append(f"Agent reason: {reason}")
    if note:
        parts.append(f"Customer note: {note}")
    return " ".join(parts) or f"{tool} request with no stated basis"


def pipeline(text: str, tool: str | None = None, k: int = 3, rerank: bool = True, candidates: int = 10) -> list:
    vector = {"index": VEC_INDEX, "path": "summary", "query": {"text": text},
              "numCandidates": 100, "limit": candidates}
    lexical = {"index": TEXT_INDEX, "text": {"query": text, "path": "summary"}}
    if tool:
        vector["filter"] = {"tool": tool}
        lexical = {"index": TEXT_INDEX, "compound": {
            "must": [{"text": {"query": text, "path": "summary"}}],
            "filter": [{"equals": {"path": "tool", "value": tool}}]}}
    stages = [
        {"$rankFusion": {
            "input": {"pipelines": {
                "semantic": [{"$vectorSearch": vector}],
                "lexical": [{"$search": lexical}, {"$limit": candidates}]}},
            "combination": {"weights": {"semantic": 1, "lexical": 1}}}},
        {"$limit": candidates},
        {"$addFields": {"fusion_score": {"$meta": "score"}}},
    ]
    if rerank:
        stages += [
            {"$rerank": {"query": {"text": text}, "path": "summary",
                         "numDocsToRerank": candidates, "model": RERANK_MODEL}},
            {"$addFields": {"rerank_score": {"$meta": "score"}}},
        ]
    stages += [
        {"$limit": k},
        {"$project": {"tool": 1, "decision": 1, "summary": 1, "decided_by": 1, "outcome_note": 1,
                      "amount_cents": 1, "seeded": 1, "created_at": 1, "fusion_score": 1, "rerank_score": 1}},
    ]
    return stages


def search(db, text: str, tool: str | None = None, k: int = 3) -> dict:
    """Top-k precedents for a request. Returns {"mode", "hits", "ms"}.

    mode is "rerank" when the native reranker ran, "fusion" when the project has it
    switched off. Any other failure is raised, and the gateway fails closed.
    """
    global _rerank_available
    t0 = time.time()
    if _rerank_available:
        try:
            hits = list(db.precedents.aggregate(pipeline(text, tool, k, rerank=True)))
            return {"mode": "rerank", "hits": hits, "ms": int((time.time() - t0) * 1000)}
        except OperationFailure as e:
            if "$rerank" not in str(e):
                raise
            _rerank_available = False
    hits = list(db.precedents.aggregate(pipeline(text, tool, k, rerank=False)))
    return {"mode": "fusion", "hits": hits, "ms": int((time.time() - t0) * 1000)}


def facts(result: dict, min_score: float, min_margin: float = 0.1) -> dict:
    """What policy sees. `denied_match` is the only field that can change a decision.

    A request resembles a refusal only if the closest precedent is a denial, its rerank score
    clears `min_score`, and it beats the closest approved precedent by `min_margin`. The last
    condition keeps a request that looks equally like an approval from being escalated.
    """
    base = {"mode": result["mode"], "ms": result["ms"], "min_score": min_score, "min_margin": min_margin}
    hits = result["hits"]
    if not hits:
        return {**base, "nearest_decision": None, "denied_match": False}
    top = hits[0]
    score = top.get("rerank_score")
    approved = [h["rerank_score"] for h in hits if h["decision"] == "approved" and "rerank_score" in h]
    margin = round(score - max(approved), 4) if score is not None and approved else None
    confident = score is None or score >= min_score  # fusion mode has no calibrated score, so rank decides
    clear = margin is None or margin >= min_margin
    return {**base, "nearest_id": top["_id"], "nearest_decision": top["decision"], "score": score,
            "margin": margin, "denied_match": top["decision"] == "denied" and confident and clear}


def refs(result: dict) -> list:
    """Compact citations for the ledger."""
    return [{"id": h["_id"], "decision": h["decision"],
             "score": round(h.get("rerank_score", h.get("fusion_score", 0.0)), 4)} for h in result["hits"]]


def wait_until_searchable(db, precedent: dict, timeout: float = 90) -> float | None:
    """Seconds until Atlas has embedded and indexed a new precedent, or None on timeout.

    Automated Embedding is asynchronous: Atlas picks the insert up from a change stream,
    embeds the summary and updates the index. This measures that delay from the outside.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        hits = search(db, precedent["summary"], tool=precedent["tool"], k=5)["hits"]
        if any(h["_id"] == precedent["_id"] for h in hits):
            return round(time.time() - t0, 1)
        time.sleep(0.7)
    return None


def wait_until_unsearchable(db, removed: list, timeout: float = 30) -> bool:
    """After deleting precedents, wait until Atlas has dropped them from the index too.

    Without this, a ruling deleted by `reset` can still be found for a few seconds and
    would tighten a request it should no longer affect.
    """
    pending = list(removed)
    deadline = time.time() + timeout
    while pending and time.time() < deadline:
        pending = [p for p in pending
                   if any(h["_id"] == p["_id"] for h in search(db, p["summary"], tool=p["tool"], k=5)["hits"])]
        if pending:
            time.sleep(0.7)
    return not pending
