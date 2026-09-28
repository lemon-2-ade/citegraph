from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import ScriptedGraph

PAPER_ROW = {
    "paper": {
        "id": "paper:1",
        "title": "Attention Is All You Need",
        "abstract": None,
        "description": "Introduces the Transformer.",
        "year": 2017,
        "doi": None,
        "openalex_id": None,
        "arxiv_id": "1706.03762",
        "url": None,
        "language": None,
        "citation_count": None,
        "authors_complete": True,
        "is_stub": False,
        "sources": ["seed"],
        "pagerank": 1.7,
        "betweenness": None,
        "in_degree": 3,
        "out_degree": 2,
        "community_id": "c1",
        "publication_date": None,
    },
    "authors": [
        {"id": "author:1", "name": "Ashish Vaswani", "orcid": None, "position": 1},
    ],
    "venues": [{"id": "venue:neurips", "name": "NeurIPS", "type": "conference"}],
    "topics": [{"id": "topic:transformers", "name": "Transformers", "score": 1.0}],
    "keywords": ["self-attention"],
    "cited_by_in_graph": 3,
    "references_in_graph": 2,
}


def _client(graph: ScriptedGraph) -> TestClient:
    app = create_app(Settings(app_env="test", log_json=False))
    app.state.graph = graph
    return TestClient(app)


def test_get_paper_maps_graph_row() -> None:
    body = _client(ScriptedGraph({"papers.get": [PAPER_ROW]})).get("/api/papers/paper:1").json()
    assert body["title"] == "Attention Is All You Need"
    assert body["authors"][0]["name"] == "Ashish Vaswani"
    assert body["venue"]["name"] == "NeurIPS"
    assert body["metrics"] == {
        "pagerank": 1.7,
        "betweenness": None,
        "in_degree": 3,
        "out_degree": 2,
        "community_id": "c1",
    }
    assert body["citation_count"] is None


def test_missing_paper_returns_404() -> None:
    response = _client(ScriptedGraph()).get("/api/papers/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_papers_passes_filters_and_pagination() -> None:
    graph = ScriptedGraph(
        {
            "papers.list.pagerank": [
                {
                    "id": "paper:1",
                    "title": "T",
                    "year": 2017,
                    "doi": None,
                    "arxiv_id": None,
                    "citation_count": None,
                    "pagerank": 0.5,
                    "is_stub": False,
                    "cited_by_in_graph": 1,
                    "venue": None,
                    "authors": ["A"],
                }
            ],
            "papers.count": [{"total": 41}],
        }
    )
    response = _client(graph).get(
        "/api/papers", params={"page": 3, "page_size": 10, "year_from": 2015, "sort": "pagerank"}
    )
    body = response.json()
    assert body["total"] == 41
    assert body["page"] == 3
    _, _, params = graph.calls[0]
    assert params["skip"] == 20
    assert params["limit"] == 10
    assert params["year_from"] == 2015


def test_list_papers_rejects_invalid_sort() -> None:
    assert _client(ScriptedGraph()).get("/api/papers", params={"sort": "evil"}).status_code == 422


def test_citations_of_unknown_paper_is_404() -> None:
    assert _client(ScriptedGraph()).get("/api/papers/x/citations").status_code == 404
