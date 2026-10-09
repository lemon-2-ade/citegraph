# ADR-003: Graph-aware retrieval for question answering

Status: Accepted

## Context

Phase 9 answers research questions from the graph with citations. Plain vector retrieval
finds papers whose wording is close to the question, but a good answer often also needs papers
that those papers cite or are cited by (the earlier method, the follow-up that fixes it). The
graph already stores those links. Separately, an answer is only useful if each claim can be
traced to a source that really exists and says it.

## Decision

**Pipeline.** (1) Hybrid search (BM25 + embeddings, rank-fused; ADR-006) returns the top `k`
papers. (2) One citation hop out from them, ranked by how many retrieved papers each candidate
touches and then by PageRank, adds up to `expand` more. (3) The prompt lists numbered sources
(title, authors, year, abstract excerpt) and the `cites` links among them. (4) The model answers
in JSON with `answer` and `answerable`, citing with `[n]`. (5) The server verifies the answer.

**Verification, not trust.** Markers that do not name a real source number are removed; an
answer that cites nothing is returned with `grounded: false` and shown as unverified; the model
may declare the question unanswerable and the UI says so. If retrieval finds nothing, or none
of the sources has text, the LLM is not called at all.

**Sources are abstracts.** The graph holds titles and abstracts, not full text, so the unit of
retrieval is the paper. There are therefore no passage chunks, and Qdrant, which was reserved
for chunk-level vectors, is **not** added in this phase. If full-text ingestion is added later,
chunk vectors can go behind a `VectorStore`-style interface at that point; paper-level
retrieval stays in Neo4j.

**Safety.** Source text is untrusted and delimited; the system prompt forbids following it and
forbids outside knowledge. Answers are rendered as plain text. The endpoint spends LLM budget,
so it uses the admin dependency like other cost-bearing operations.

## Alternatives considered

- Vector-only retrieval: simpler, but misses structurally related papers.
- Multi-hop agentic retrieval: more recall, much more cost and nondeterminism; revisit after the evaluation work in Phase 14.
- Asking the model to emit citations as structured spans: harder for models to follow reliably across providers; marker verification is simpler and checkable.

## Consequences

- A citation proves the source exists and was in the context, not that it supports the claim; the UI shows the excerpt so users can check. Faithfulness is measured in Phase 14.
- Latency is one search, two graph queries and one LLM call.
- No streaming yet.
