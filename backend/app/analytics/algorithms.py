"""Graph algorithms on in-memory NetworkX projections.

Pure functions over ``networkx`` graphs: no I/O, deterministic (fixed seeds), and used by
the NetworkX analytics backend. The Neo4j GDS backend implements the same operations
inside the database.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

import networkx as nx

CommunityAlgorithm = Literal["louvain", "leiden"]

DEFAULT_SEED = 42


def pagerank(
    graph: nx.DiGraph | nx.Graph,
    *,
    damping: float = 0.85,
    personalization: Mapping[str, float] | None = None,
    weight: str | None = None,
) -> dict[str, float]:
    """PageRank; with ``personalization`` it is Personalized PageRank.

    On the citation graph (citing -> cited), score flows from citing to cited papers, so
    a paper ranks highly when it is cited by papers that are themselves highly ranked.
    That measures *structural influence within this graph*, not research quality.
    """
    if graph.number_of_nodes() == 0:
        return {}
    scores: dict[str, float] = nx.pagerank(
        graph,
        alpha=damping,
        personalization=dict(personalization) if personalization else None,
        weight=weight,
        max_iter=200,
        tol=1e-08,
    )
    return scores


def betweenness(
    graph: nx.Graph | nx.DiGraph,
    *,
    sample_size: int | None = None,
    seed: int = DEFAULT_SEED,
    weight: str | None = None,
) -> dict[str, float]:
    """Normalised betweenness centrality computed on the *undirected* view.

    Bridges between research areas are what we want to surface, and citation direction is
    irrelevant for that. Exact betweenness is O(V·E); pass ``sample_size`` to estimate it
    from ``k`` source nodes (Brandes' sampling) on large graphs.
    """
    undirected = graph.to_undirected(as_view=True) if graph.is_directed() else graph
    n = undirected.number_of_nodes()
    if n == 0:
        return {}
    k = sample_size if sample_size is not None and sample_size < n else None
    result: dict[str, float] = nx.betweenness_centrality(
        undirected, k=k, seed=seed, normalized=True, weight=weight
    )
    return result


def communities(
    graph: nx.Graph | nx.DiGraph,
    *,
    algorithm: CommunityAlgorithm = "louvain",
    resolution: float = 1.0,
    seed: int = DEFAULT_SEED,
    weight: str | None = "weight",
) -> dict[str, int]:
    """Community assignment ``node -> community index`` (0 = largest community).

    Runs on the undirected view. Indices are ordered by community size (then by the
    smallest member ID) so results are stable for a fixed graph and seed.
    """
    undirected = graph.to_undirected() if graph.is_directed() else graph
    if undirected.number_of_nodes() == 0:
        return {}
    if algorithm == "louvain":
        parts: Iterable[set[str]] = nx.community.louvain_communities(
            undirected, weight=weight, resolution=resolution, seed=seed
        )
    elif algorithm == "leiden":
        parts = nx.community.leiden_communities(
            undirected, weight=weight, resolution=resolution, seed=seed, metric="modularity"
        )
    else:  # pragma: no cover - guarded by Literal type
        raise ValueError(f"unknown community algorithm {algorithm!r}")
    ordered = sorted((sorted(p) for p in parts), key=lambda members: (-len(members), members[0]))
    return {node: index for index, members in enumerate(ordered) for node in members}


def modularity(graph: nx.Graph | nx.DiGraph, assignment: Mapping[str, int]) -> float:
    undirected = graph.to_undirected() if graph.is_directed() else graph
    groups: dict[int, set[str]] = {}
    for node, community in assignment.items():
        groups.setdefault(community, set()).add(node)
    if not groups:
        return 0.0
    return float(nx.community.modularity(undirected, groups.values()))


@dataclass(frozen=True)
class Similar:
    node: str
    score: float
    shared: int


def jaccard_neighbours(
    graph: nx.DiGraph,
    node: str,
    *,
    direction: Literal["out", "in"] = "out",
    top_k: int = 10,
) -> list[Similar]:
    """Jaccard similarity of neighbour sets.

    ``direction="out"`` compares reference lists (bibliographic coupling);
    ``direction="in"`` compares sets of citing papers (co-citation).
    """
    if node not in graph:
        return []
    neighbours = graph.successors if direction == "out" else graph.predecessors
    reverse = graph.predecessors if direction == "out" else graph.successors
    mine = set(neighbours(node))
    if not mine:
        return []
    candidates = {other for n in mine for other in reverse(n)} - {node}
    results = []
    for other in candidates:
        theirs = set(neighbours(other))
        shared = len(mine & theirs)
        union = len(mine | theirs)
        if shared:
            results.append(Similar(node=other, score=shared / union, shared=shared))
    results.sort(key=lambda s: (-s.score, -s.shared, s.node))
    return results[:top_k]


def top_k(
    scores: Mapping[str, float], k: int, *, exclude: Iterable[str] = ()
) -> list[tuple[str, float]]:
    skip = set(exclude)
    ranked = sorted(
        ((n, s) for n, s in scores.items() if n not in skip), key=lambda x: (-x[1], x[0])
    )
    return ranked[:k]
