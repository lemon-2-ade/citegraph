# Evaluation

ResearchGraph ships a harness that measures its own search, question answering and
natural-language querying on small hand-labelled gold sets (`data/eval/*.json`). **This document
contains no scores on purpose**: results depend on your embedding model, LLM and graph contents,
so they must come from running the harness on your setup.

```bash
docker compose exec backend researchgraph eval retrieval --out /tmp/retrieval.md
docker compose exec backend researchgraph eval nlquery
docker compose exec backend researchgraph eval rag --judge
```

Each command prints JSON; `--out` also writes a Markdown summary. They need a seeded graph
(`seed`, `analyze`, `embed`); `nlquery` and `rag` also need a configured LLM and spend tokens
(`--judge` adds about one extra call per answer).

## What each suite measures

**Retrieval** (`retrieval.json`, 22 queries). For keyword, semantic and hybrid search: recall@5,
recall@10, hit@5, mean reciprocal rank and nDCG@10, overall and split by query style (`lexical`
queries reuse words from the papers; `paraphrase` queries do not). The split shows whether
semantic search earns its place over BM25. Relevance judgements are the seed keys listed per
query.

**NL → Cypher** (`nlquery.json`, 8 questions). Execution accuracy: the model's validated query is
run and its rows must equal the rows of a hand-written gold query, as a multiset of values,
ignoring column names and order. Also reported: how often a query was produced at all and how
often the first draft passed validation.

**RAG** (`rag.json`, 8 questions). Grounded rate (answer cites at least one real source), mean
citations, source recall (do the expected papers appear among the sources), abstention on the
unanswerable question, and with `--judge` a faithfulness rate from an LLM judge that sees only the
answer and the cited excerpts.

## Limits to keep in mind

- The gold sets are small and were labelled by the project author, who also knows the system.
  Differences of a few points are noise; use them to catch regressions and gross failures, not to
  rank models finely.
- The seed corpus has 105 papers and curated descriptions instead of abstracts, so absolute numbers
  will not transfer to a large OpenAlex ingest. Add your own cases to the JSON files for your data.
- Citation validity is enforced by construction (invalid markers are removed), so "grounded" says
  the answer cites something real, not that the cited paper supports the claim. Faithfulness needs
  the judge, and an LLM judge has its own errors; spot-check its verdicts.
- Retrieval metrics depend on the embedding model recorded by `researchgraph embed`; re-run after
  changing it.
