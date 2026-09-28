import networkx as nx
import pytest

from app.analytics.algorithms import (
    betweenness,
    communities,
    jaccard_neighbours,
    modularity,
    pagerank,
    top_k,
)


def citation_star() -> nx.DiGraph:
    """Five papers all citing 'hub'; 'hub' cites 'root'."""
    g = nx.DiGraph()
    for i in range(5):
        g.add_edge(f"p{i}", "hub")
    g.add_edge("hub", "root")
    return g


def two_clusters_with_bridge() -> nx.Graph:
    g = nx.Graph()
    left = [f"a{i}" for i in range(5)]
    right = [f"b{i}" for i in range(5)]
    for group in (left, right):
        for i, u in enumerate(group):
            for v in group[i + 1 :]:
                g.add_edge(u, v)
    g.add_edge("a0", "bridge")
    g.add_edge("bridge", "b0")
    return g


def test_pagerank_flows_to_cited_papers() -> None:
    scores = pagerank(citation_star())
    assert sum(scores.values()) == pytest.approx(1.0)
    # 'root' is cited by the most-cited paper, so it inherits its importance.
    assert scores["root"] > scores["hub"] > scores["p0"]
    assert scores["p0"] == pytest.approx(scores["p4"])


def test_personalized_pagerank_concentrates_near_source() -> None:
    g = citation_star()
    g.add_edge("x", "y")  # disconnected component
    scores = pagerank(g, personalization={"p0": 1.0})
    assert scores["x"] == pytest.approx(0.0, abs=1e-9)
    assert scores["y"] == pytest.approx(0.0, abs=1e-9)
    assert scores["hub"] > 0


def test_betweenness_identifies_bridge() -> None:
    scores = betweenness(two_clusters_with_bridge())
    assert max(scores, key=scores.__getitem__) == "bridge"
    assert scores["a3"] == pytest.approx(0.0)


def test_betweenness_sampling_is_deterministic() -> None:
    g = two_clusters_with_bridge()
    assert betweenness(g, sample_size=4) == betweenness(g, sample_size=4)


@pytest.mark.parametrize("algorithm", ["louvain", "leiden"])
def test_communities_split_clusters(algorithm: str) -> None:
    g = two_clusters_with_bridge()
    assignment = communities(g, algorithm=algorithm)  # type: ignore[arg-type]
    assert assignment["a1"] == assignment["a4"]
    assert assignment["b1"] == assignment["b4"]
    assert assignment["a1"] != assignment["b1"]
    assert modularity(g, assignment) > 0.3


def test_communities_are_ordered_by_size_and_stable() -> None:
    g = two_clusters_with_bridge()
    g.add_edges_from([("c0", "c1")])  # a small separate component
    first = communities(g)
    assert first == communities(g)
    sizes = {}
    for c in first.values():
        sizes[c] = sizes.get(c, 0) + 1
    assert [sizes[i] for i in sorted(sizes)] == sorted(sizes.values(), reverse=True)


def test_bibliographic_coupling_and_cocitation() -> None:
    g = nx.DiGraph()
    g.add_edges_from([("a", "r1"), ("a", "r2"), ("a", "r3"), ("b", "r1"), ("b", "r2"), ("c", "r9")])
    coupled = jaccard_neighbours(g, "a", direction="out")
    assert [(s.node, s.shared) for s in coupled] == [("b", 2)]
    assert coupled[0].score == pytest.approx(2 / 3)

    cocited = jaccard_neighbours(g, "r1", direction="in")
    assert cocited[0].node == "r2"  # both cited by a and b
    assert cocited[0].score == pytest.approx(1.0)


def test_empty_inputs() -> None:
    assert pagerank(nx.DiGraph()) == {}
    assert betweenness(nx.Graph()) == {}
    assert communities(nx.Graph()) == {}
    assert jaccard_neighbours(nx.DiGraph(), "missing") == []


def test_top_k_excludes_and_breaks_ties_by_id() -> None:
    assert top_k({"b": 1.0, "a": 1.0, "c": 0.5}, 2) == [("a", 1.0), ("b", 1.0)]
    assert top_k({"b": 1.0, "a": 1.0}, 5, exclude=["a"]) == [("b", 1.0)]
