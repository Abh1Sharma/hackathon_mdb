"""Policy evaluation. Pure functions over policy documents, no database access.

A policy matches when its tool and class match and every condition holds.
Precedence: deny beats step-up beats allow. If nothing matches, the answer is deny.
A condition about a fact that is missing does not hold.
"""

MISSING = object()

OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


def lookup(ctx: dict, path: str):
    node = ctx
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node or node[part] is None:
            return MISSING
        node = node[part]
    return node


def holds(cond: dict, ctx: dict) -> bool:
    left = lookup(ctx, cond["field"])
    right = cond["value"]
    if isinstance(right, dict) and "ref" in right:
        right = lookup(ctx, right["ref"])
    if left is MISSING or right is MISSING:
        return False
    return OPS[cond["op"]](left, right)


def matches(policy: dict, ctx: dict) -> bool:
    match = policy["match"]
    if match["tool"] not in ("*", ctx["tool"]):
        return False
    if match.get("class") and match["class"] != ctx["identity"].get("class"):
        return False
    return all(holds(c, ctx) for c in policy["when"])


def uses_precedents(policy: dict, tool: str) -> bool:
    return policy["match"]["tool"] in ("*", tool) and any(c["field"].startswith("precedent.") for c in policy["when"])


def evaluate(policies: list, ctx: dict) -> dict:
    """Returns decision, the policies that produced it (id and version), and the rule to show the agent."""
    matched = [p for p in policies if p.get("status") == "active" and matches(p, ctx)]
    every = [{"id": p["_id"], "effect": p["effect"]} for p in matched]  # for the record: all rules that applied
    for effect, decision in (("deny", "deny"), ("step_up", "step_up"), ("allow", "allow")):
        hit = [p for p in matched if p["effect"] == effect]
        if hit:
            return {"decision": decision, "rule": hit[0]["_id"], "explanation": hit[0]["description"],
                    "policy_refs": [{"id": p["_id"], "version": p["version"]} for p in hit], "matched": every}
    return {"decision": "deny", "rule": "DEFAULT-DENY", "explanation": "No policy allows this call",
            "policy_refs": [], "matched": every}
