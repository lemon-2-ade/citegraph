# ADR-009: Natural-language to Cypher with layered read-only guarantees

Status: Accepted

## Context

Phase 10 lets users ask structural questions ("who collaborates most with X?") in plain
English. That means executing a query written by a language model against the production graph.
The model can be wrong, can be manipulated by text it has seen, and can emit writes, expensive
queries or procedure calls. A prompt saying "only write read queries" is not a control.

## Decision

Execute nothing the model wrote until three independent layers agree, none of which relies on
the model behaving:

1. **Static validator** (`app/graph/cypher_guard.py`). An allow-list: a single statement that
   starts with a read clause; no `CREATE/MERGE/SET/DELETE/REMOVE/LOAD/FOREACH/UNION/...`; no
   comments, backticks or parameters; `CALL` only for `db.index.fulltext.queryNodes` on three
   named indexes; labels, relationship types and properties must exist in the schema (embedding
   vectors and cached model output are not exposed); variable-length paths bounded to 4 hops;
   `LIMIT` required, at most 100 (50 appended when missing). String literals are masked before
   scanning so keywords inside text neither pass nor fail the check.
2. **Neo4j `EXPLAIN`**. The database parses the query without running it and must classify it as
   read-only (`query_type == "r"`). This catches anything the validator's patterns miss.
3. **Constrained execution**. A read transaction (the server rejects writes), a 10 second
   server-side timeout, a hard row cap, and cell size limits with vectors stripped.

A rejection at layer 1 or 2 is fed back to the model once as a short, schema-level message, and
the repaired draft goes through all layers again. Two failures return HTTP 422. Execution errors
return a generic message; server details stay in the logs.

The response always includes the Cypher that ran so the result can be audited, and the model may
decline with `can_answer: false`. Few-shot examples live in code as constants, are linted against
Neo4j's grammar in CI, and are checked by tests against both the validator and (in integration
tests) a real database.

## Alternatives considered

- Parameterised templates only: safest, but cannot answer open-ended questions.
- Database role with read-only privileges: stronger still, and recommended for production
  (create a `reader` user); the application layers do not require Enterprise features.
- A full Cypher parser in Python: more precise than regexes, but no maintained library was
  available; `EXPLAIN` provides the authoritative parse.

## Consequences

- The allow-list will reject some valid queries (procedures, `UNION`, unknown properties); the
  repair loop and rephrasing cover most of these.
- Correct but irrelevant queries are still possible; showing the Cypher is the mitigation.
- Answer quality (execution accuracy on a question set) is evaluated in Phase 14.
