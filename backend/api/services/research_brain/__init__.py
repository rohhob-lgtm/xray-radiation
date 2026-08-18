"""Knowledge Evolution Engine — Sub-Phase 2A.

Plans a research mission into a ranked topic tree BEFORE any discovery/crawl
happens (planner.py), versions the existing KnowledgeNode/KnowledgeEdge graph
as evidence accumulates rather than overwriting facts (knowledge_versioning.py),
tracks per-topic coverage (gap_detector.py), and exposes versioned facts to
the same shared retrieval path chat already uses (graph_query.py).

Built entirely on top of Phase 1 (api.services.research_agent) and the
pre-existing KnowledgeNode/KnowledgeEdge graph (api.services.study_service) —
neither is replaced, both are extended.
"""
