"""FastAPI dependencies that expose shared resources stored on ``app.state``."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.graph.client import GraphClient


def get_graph(request: Request) -> GraphClient:
    graph: GraphClient = request.app.state.graph
    return graph


GraphDep = Annotated[GraphClient, Depends(get_graph)]
