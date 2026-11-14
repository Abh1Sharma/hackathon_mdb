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
                      "amount_cents": 1, "fusion_score": 1, "rerank_score": 1}},
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


def facts(result: dict, min_score: float) -> dict:
    """What policy sees. `denied_match` is the only field that can change a decision."""
    if not result["hits"]:
        return {"nearest_decision": None, "denied_match": False, "mode": result["mode"]}
    top = result["hits"][0]
    score = top.get("rerank_score")
    confident = score is None or score >= min_score  # fusion mode has no calibrated score, so rank decides
    return {"nearest_id": top["_id"], "nearest_decision": top["decision"], "score": score,
            "mode": result["mode"], "min_score": min_score,
            "denied_match": top["decision"] == "denied" and confident}


def refs(result: dict) -> list:
    """Compact citations for the ledger."""
    return [{"id": h["_id"], "decision": h["decision"],
             "score": round(h.get("rerank_score", h.get("fusion_score", 0.0)), 4)} for h in result["hits"]]
