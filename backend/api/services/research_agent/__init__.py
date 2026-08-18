"""Autonomous Radiation & X-Ray Research Agent — Phase 1.

A self-directed research "mission": generate queries from a mission
statement, discover candidate sources (free academic APIs + curated trusted
domains), crawl them via api.services.web_crawler.crawl(), score/dedupe, and
ingest accepted content as ordinary RagDocument rows so the existing shared
retrieve_chunks() path (rag_service.py, already used by chat and every other
platform section) picks it up with zero changes to retrieval itself.
"""
