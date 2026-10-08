# ADR-006: Embedding providers and the vector store

Status: Accepted

## Context

Phase 7 adds search by meaning. That needs (1) a way to turn paper text into vectors and
(2) somewhere to index and query them. The system already runs Neo4j 5.26, which has native
vector indexes (HNSW), and the later RAG and recommendation phases want to combine vector
similarity with graph traversal in one query.

## Decision

**Provider.** Embeddings come from a small `EmbeddingProvider` interface with three
implementations: OpenAI (`text-embedding-3-small`, used when `OPENAI_API_KEY` is set), a local
CPU model (`BAAI/bge-small-en-v1.5` through fastembed/ONNX, the fallback), and a deterministic
hashed bag-of-words provider that exists only so tests and demos run offline.
`EMBEDDING_PROVIDER=auto` picks OpenAI when a key exists and the local model otherwise; an
explicit provider is never silently replaced.

**Vector store.** Vectors are stored on `Paper.embedding` with a Neo4j vector index
(`paper_embedding`, cosine). Papers are embedded from title plus abstract (or description).
Qdrant is deliberately deferred to Phase 9, where passage-level chunks for RAG may reach a
scale and filtering workload that justify a dedicated store; the paper-level vectors here stay
in Neo4j so that graph-aware queries need no second system.

**Model bookkeeping.** Vectors from different models are not comparable even at equal size.
An `(:EmbeddingConfig {id: 'paper'})` node records the model and dimensions; `researchgraph
embed` and search both refuse to mix models, and a model change needs `embed --rebuild`.
Re-running `embed` is incremental: unchanged papers (same text hash and model) are skipped.

**Ranking.** Keyword search is Lucene full-text (BM25). Hybrid search merges the keyword and
semantic rankings with reciprocal rank fusion (k = 60) because BM25 scores and cosine
similarities are on different scales. Hybrid degrades to keyword results, with a visible note,
when embeddings are unavailable.

## Consequences

- Works offline and without an API key (local model), and improves with OpenAI when a key is set.
- Switching providers or models re-embeds the whole corpus; the cost is small at this size.
- With OpenAI, titles and abstracts are sent to a third party; the local model keeps them on
  the machine.
- The first local run downloads the model (about 130 MB) from Hugging Face; a Docker volume
  caches it.
- Moving vectors to Qdrant or pgvector later means a new adapter behind the same repository
  methods, not an API or UI change.
