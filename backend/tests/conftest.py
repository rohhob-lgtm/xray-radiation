"""Test-session environment defaults.

api.db.base raises at import time if DATABASE_URL is unset, so every test
module that imports `main`/`api.*` needs it configured before that import
happens. Uses setdefault so a developer's own DATABASE_URL (real Postgres/
sqlite dev DB) is never overridden — this only fills the gap when nothing is
configured, so the suite is runnable out of the box.
"""
import os

_TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "_test_scratch.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB_PATH}")
os.environ.setdefault("ACTIVE_PROVIDER", "mock")
os.environ.setdefault("DISABLE_AUTH", "true")
# Phase 2B.0: api.services.research_brain.local_extraction (and
# research_agent.ingestion's Ollama embedding path) call out to a local
# Ollama server as part of the normal Free Mode code path — including from
# tests that don't mention Ollama at all (e.g. Phase 1's crawler tests,
# transitively, via graph_extraction.extract_and_version). Point at a port
# that fails instantly (connection refused) rather than the real default
# port 11434, which — depending on what's listening/intercepting on a given
# dev machine — can hang for the full request timeout instead of failing
# fast. This exercises the real graceful-degrade code path (a real httpx
# call, a real exception), just against a guaranteed-unreachable target, so
# the suite never depends on network state or a multi-second timeout.
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:1")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _ensure_tables():
    """Belt-and-braces table creation — don't rely on ASGI lifespan/startup
    events firing under every TestClient usage pattern in the suite."""
    from api.db.base import create_all_tables
    create_all_tables()
