from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import app
from app.core.config import get_settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def sqlite_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("init", "seed", "ingest", "jobs", "analyze"):
        assert command in result.output


def test_jobs_with_empty_database() -> None:
    result = runner.invoke(app, ["jobs"])
    assert result.exit_code == 0, result.output
    assert "no jobs yet" in result.output


def test_ingest_requires_query_or_resume() -> None:
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code != 0
    assert "--query or --resume" in result.output


def test_ingest_validates_params_before_touching_services() -> None:
    result = runner.invoke(app, ["ingest", "--query", "x"])
    assert result.exit_code != 0
    assert "at least 2 characters" in result.output


def test_analyze_validates_options() -> None:
    result = runner.invoke(app, ["analyze", "--backend", "spark"])
    assert result.exit_code != 0
    assert "backend must be" in result.output
