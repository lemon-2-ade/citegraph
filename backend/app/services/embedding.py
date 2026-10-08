"""Compute and store paper embeddings (incremental, resumable by design)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.ai.embeddings import EmbeddingProvider, paper_text, text_hash
from app.core.logging import get_logger
from app.graph.client import GraphClient
from app.repositories.embeddings import EmbeddingRepository, SemanticUnavailableError

log = get_logger(__name__)


@dataclass
class EmbedStats:
    provider: str
    model: str
    dimensions: int
    scanned: int = 0
    embedded: int = 0
    unchanged: int = 0
    without_text: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


async def embed_papers(
    graph: GraphClient,
    provider: EmbeddingProvider,
    *,
    rebuild: bool = False,
    batch_size: int = 64,
) -> EmbedStats:
    """Embed every paper whose text or model changed since its stored vector.

    Safe to re-run: unchanged papers are skipped, and each batch is committed on its own, so
    an interrupted run resumes where it stopped. Changing the model needs ``rebuild`` because
    vectors from different models are not comparable.
    """
    repo = EmbeddingRepository(graph)
    config = await repo.config()
    if (
        config is not None
        and not rebuild
        and (config["model"] != provider.model or int(config["dimensions"]) != provider.dimensions)
    ):
        raise SemanticUnavailableError(
            f"Papers were embedded with {config['model']!r} ({config['dimensions']} "
            f"dimensions) but the configured model is {provider.model!r} "
            f"({provider.dimensions}). Run `researchgraph embed --rebuild` to re-embed "
            "everything with the new model."
        )
    if rebuild:
        await repo.reset()
    await repo.ensure_index(provider.dimensions)
    await repo.set_config(
        model=provider.model, dimensions=provider.dimensions, provider=provider.name
    )

    stats = EmbedStats(provider.name, provider.model, provider.dimensions)
    after = ""
    while True:
        batch = await repo.candidates(after, batch_size)
        if not batch:
            break
        after = batch[-1]["id"]
        stats.scanned += len(batch)
        pending: list[tuple[str, str, str]] = []
        for row in batch:
            text = paper_text(row["title"], row["abstract"], row["description"])
            if not text:
                stats.without_text += 1
                continue
            digest = text_hash(text)
            if row["has_vector"] and row["hash"] == digest and row["model"] == provider.model:
                stats.unchanged += 1
                continue
            pending.append((row["id"], text, digest))
        if pending:
            vectors = await provider.embed([text for _, text, _ in pending])
            await repo.store(
                [
                    {"id": pid, "vector": vector, "hash": digest}
                    for (pid, _, digest), vector in zip(pending, vectors, strict=True)
                ],
                provider.model,
            )
            stats.embedded += len(pending)
        log.info("embeddings.batch", scanned=stats.scanned, embedded=stats.embedded)
    return stats
