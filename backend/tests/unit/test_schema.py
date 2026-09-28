from app.graph.schema import CONSTRAINTS, INDEXES


def test_all_schema_statements_are_idempotent() -> None:
    for statement in (*CONSTRAINTS, *INDEXES):
        assert "IF NOT EXISTS" in statement, statement


def test_schema_names_are_unique() -> None:
    names = [
        s.split()[2] if "FULLTEXT" not in s else s.split()[3] for s in (*CONSTRAINTS, *INDEXES)
    ]
    assert len(names) == len(set(names))


def test_external_identifiers_are_unique_constraints() -> None:
    joined = " ".join(CONSTRAINTS)
    for prop in ("n.doi", "n.openalex_id", "n.arxiv_id", "n.orcid"):
        assert f"REQUIRE {prop} IS UNIQUE" in joined
