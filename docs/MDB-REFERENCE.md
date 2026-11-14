# MongoDB reference (verified against mongodb.com/docs on build day)

Sandbox: Atlas project in org "Agents in Context Toronto", cluster `Cluster0`, tier M10, MongoDB 9.0.7, AWS. Markdown versions of any docs page: append `.md` to the URL. Index: https://www.mongodb.com/docs/llms.txt

## Automated Embedding (Vector Search index, type `autoEmbed`)

Atlas generates and stores embeddings for a text field (Voyage models hosted by MongoDB) and embeds the query text at query time. Embedding is asynchronous, driven by change streams. Embeddings live in an internal database `__mdb_internal_search` (do not touch). An org resource policy can forbid it.

```json
{ "fields": [
    { "type": "autoEmbed", "modality": "text", "path": "summary", "model": "voyage-4" },
    { "type": "filter", "path": "tool" },
    { "type": "filter", "path": "decision" }
] }
```

Models: `voyage-4` (recommended), `voyage-4-large`, `voyage-4-lite`, `voyage-code-4`. Optional: `numDimensions` 256/512/1024/2048, `quantization`, `similarity`.

Query (text in, no vector):

```json
{ "$vectorSearch": { "index": "precedents_vec", "path": "summary",
    "query": { "text": "..." }, "filter": { "tool": "payments.refund" },
    "numCandidates": 100, "limit": 10 } }
```

Score: `{ "$meta": "vectorSearchScore" }`.

## Hybrid search

`$rankFusion` (8.0+, reciprocal rank fusion) or `$scoreFusion` (8.3+). All sub-pipelines must run against the same collection, they run serially, and there is no pagination. Give each sub-pipeline a `$limit`.

```json
{ "$rankFusion": {
    "input": { "pipelines": {
        "semantic": [ { "$vectorSearch": { } } ],
        "lexical":  [ { "$search": { "index": "precedents_text", "text": { "query": "...", "path": ["summary", "reason", "note"] } } }, { "$limit": 10 } ]
    } },
    "combination": { "weights": { "semantic": 1, "lexical": 1 } },
    "scoreDetails": true } }
```

## Native reranking: `$rerank` (new in 9.0)

```json
{ "$rerank": { "query": { "text": "..." }, "path": "summary", "numDocsToRerank": 10, "model": "rerank-3" } }
```

- Needs MongoDB 9.0+. `rerank-3` and `rerank-3-lite` need M10+. `rerank-2.5` also exists.
- Must be switched on: Project Settings, toggle "Native Reranking: $rerank in the Aggregation Pipeline". Needs Project Owner.
- Cannot be used inside `$rankFusion` input pipelines. Use it after the fusion stage.
- Fails if `path` is missing on any input document.
- It replaces `$meta: "score"`. Copy the fusion score into a named field with `$addFields` before `$rerank` to keep both.

## Atlas Agent Engine (public preview) and how Warrant differs

Agent Engine has a Policy Engine (`AUTHORIZED_TOOLS`, `AUTHORIZED_MODELS`, per-execution and per-session caps), human-in-the-loop built on LangGraph `interrupt()`, content guardrails and traces. Documented limits that Warrant covers:

| Agent Engine Policy Engine | Warrant |
|---|---|
| Tool-name allowlists and numeric budgets | Rules over arguments, resource data and ledger history |
| No policy means no restriction | Default deny |
| Policy changes do not affect in-flight executions, about 1 minute to propagate | Kill takes effect on the next call, re-checked inside the decision transaction |
| Denial halts the execution | Structured refusal, the agent continues with the next ticket |
| No identity of the human the agent acts for | Agent identity plus on-behalf-of on every call |
| No undo | Rollback from captured before-images |

We are not building on Agent Engine today (preview, deploy overhead). Position Warrant as the fine-grained layer beside it.

## Core database features we rely on

| Need | Feature | Note |
|---|---|---|
| Strict ledger | `$jsonSchema` validator, `validationAction: "error"` | Bad insert fails with code 121 |
| Decision + warrant + ledger together | Multi-document transaction (`session.with_transaction`) | M10 replica set supports it |
| Kill switch, live timeline | Change streams (`collection.watch()`) | Keep the resume token |
| Rollback evidence | `collMod` with `changeStreamPreAndPostImages: { enabled: true }` | Gateway-captured before-images stay the primary source |
| Single-use, expiring warrants | Unique compound index, TTL index | |
| Append-only ledger | Custom role with `insert` and `find` only | Created in Atlas UI (Database Access, Custom Roles), not with `createRole` |
