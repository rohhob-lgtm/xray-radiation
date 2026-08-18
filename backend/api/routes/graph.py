"""Knowledge Graph — extract concepts from documents and build a visual graph."""
from __future__ import annotations
import json
import re
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.db import get_db
from api.db.crud import list_rag_documents
from api.middleware.auth import optional_auth
from api.services.ai_providers.registry import provider_registry

router = APIRouter(tags=["graph"])


def _slugify(text: str) -> str:
    """Make a URL-safe node ID from text."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower().strip()).strip("_")[:40]


CONCEPT_CATEGORIES = {
    "scanner": ["zbv", "scanner", "cargo", "baggage", "detector", "beam", "source", "generator"],
    "physics": ["x-ray", "photon", "attenuation", "energy", "dose", "radiation", "hvl", "tvl", "scatter", "bremsstrahlung"],
    "detection": ["threat", "ied", "weapon", "detection", "atr", "algorithm", "classification", "segmentation"],
    "engineering": ["maintenance", "calibration", "alignment", "component", "circuit", "mechanical", "electrical"],
    "safety": ["safety", "shielding", "protection", "regulatory", "iaea", "alara", "dose"],
    "software": ["software", "firmware", "image", "processing", "neural", "network", "ai", "algorithm"],
}


def _categorize_concept(concept: str) -> str:
    lower = concept.lower()
    for cat, keywords in CONCEPT_CATEGORIES.items():
        if any(kw in lower for kw in keywords):
            return cat
    return "general"


@router.get("/graph/data")
async def get_graph_data(
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """
    Return the knowledge graph.
    Uses the persistent KnowledgeNode/KnowledgeEdge store when populated,
    with a dynamic fallback for documents not yet studied.
    """
    from api.db.models import RagDocument, KnowledgeNode, KnowledgeEdge

    docs = db.query(RagDocument).order_by(RagDocument.created_at).all()

    # ── Persistent graph path ──────────────────────────────────────────────
    kg_nodes = db.query(KnowledgeNode).filter(KnowledgeNode.approved == True).limit(500).all()
    kg_edges = db.query(KnowledgeEdge).filter(KnowledgeEdge.approved == True).limit(1000).all()

    if kg_nodes:
        node_ids = {n.id for n in kg_nodes}
        # Also add document nodes
        doc_nodes = []
        for doc in docs:
            doc_nodes.append({
                "id": f"doc_{doc.id[:8]}",
                "type": "document",
                "label": doc.filename.replace(".pdf", "").replace("_", " ")[:35],
                "filename": doc.filename,
                "word_count": doc.word_count or 0,
                "doc_type": doc.document_type or "other",
                "size": 28,
            })

        persistent_nodes = [
            {
                "id": n.id,
                "type": n.node_type.lower(),
                "label": n.label,
                "description": n.description or "",
                "weight": n.weight,
                "size": max(10, min(28, int(n.weight * 14))),
                "source_doc_id": n.source_doc_id,
            }
            for n in kg_nodes
        ]
        persistent_edges = [
            {
                "id": e.id,
                "source": e.from_node_id,
                "target": e.to_node_id,
                "weight": e.weight,
                "relationship": e.relationship,
            }
            for e in kg_edges
            if e.from_node_id in node_ids and e.to_node_id in node_ids
        ]

        all_nodes = doc_nodes + persistent_nodes
        all_edges = persistent_edges

        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "stats": {
                "documents": len(docs),
                "concepts": len(kg_nodes),
                "connections": len(kg_edges),
            },
            "source": "persistent",
        }

    if not docs:
        return {"nodes": [], "edges": [], "stats": {"documents": 0, "concepts": 0, "connections": 0}, "source": "empty"}

    provider = provider_registry.get_active()
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    concept_registry: Dict[str, str] = {}  # label → node_id

    # ── Document nodes ─────────────────────────────────────
    for doc in docs:
        doc_node_id = f"doc_{doc.id[:8]}"
        nodes.append({
            "id": doc_node_id,
            "type": "document",
            "label": doc.filename.replace(".pdf", "").replace("_", " ")[:35],
            "filename": doc.filename,
            "word_count": doc.word_count or 0,
            "doc_type": doc.document_type or "other",
            "size": 28,
        })

    # ── Extract concepts using content keyword analysis (no LLM call for speed) ──
    # Parse document content for X-ray domain concepts
    domain_concepts = [
        ("ZBV Scanner", "scanner"),
        ("Dual Energy X-ray", "physics"),
        ("Backscatter Imaging", "physics"),
        ("Threat Detection", "detection"),
        ("Automatic Target Recognition", "detection"),
        ("Radiation Safety", "safety"),
        ("Image Processing", "software"),
        ("Photon Counting", "physics"),
        ("Material Discrimination", "detection"),
        ("Detector Array", "scanner"),
        ("X-ray Source", "scanner"),
        ("Shielding", "safety"),
        ("Beer-Lambert Law", "physics"),
        ("HVL/TVL", "physics"),
        ("Calibration", "engineering"),
        ("Maintenance", "engineering"),
        ("Neural Network", "software"),
        ("AI Classification", "software"),
        ("Cargo Inspection", "scanner"),
        ("IED Detection", "detection"),
        ("Operator Training", "general"),
        ("Safety Protocols", "safety"),
    ]

    # Check which concepts appear in each document
    for concept_label, category in domain_concepts:
        concept_id = f"concept_{_slugify(concept_label)}"
        appears_in = []
        for doc in docs:
            doc_text = (doc.content or "").lower()
            search_terms = concept_label.lower().split()
            if all(term in doc_text for term in search_terms[:2]):
                appears_in.append(doc)

        if appears_in:
            if concept_id not in concept_registry:
                concept_registry[concept_id] = concept_label
                nodes.append({
                    "id": concept_id,
                    "type": "concept",
                    "category": category,
                    "label": concept_label,
                    "size": 14 + min(len(appears_in) * 4, 16),
                    "doc_count": len(appears_in),
                })

            for doc in appears_in:
                doc_node_id = f"doc_{doc.id[:8]}"
                edges.append({
                    "id": f"e_{doc_node_id}_{concept_id}",
                    "source": doc_node_id,
                    "target": concept_id,
                    "weight": 1,
                })

    # ── Cross-document similarity edges ─────────────────────────────
    # Connect documents that share many concepts
    doc_concepts: Dict[str, set] = {f"doc_{d.id[:8]}": set() for d in docs}
    for edge in edges:
        if edge["source"].startswith("doc_") and edge["target"].startswith("concept_"):
            doc_concepts[edge["source"]].add(edge["target"])

    doc_ids = [f"doc_{d.id[:8]}" for d in docs]
    for i in range(len(doc_ids)):
        for j in range(i + 1, len(doc_ids)):
            shared = doc_concepts[doc_ids[i]] & doc_concepts[doc_ids[j]]
            if len(shared) >= 3:  # at least 3 shared concepts
                edges.append({
                    "id": f"e_{doc_ids[i]}_{doc_ids[j]}",
                    "source": doc_ids[i],
                    "target": doc_ids[j],
                    "weight": len(shared),
                    "type": "similarity",
                })

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "documents": len(docs),
            "concepts": len(concept_registry),
            "connections": len(edges),
        },
    }


@router.get("/graph/concepts")
async def search_concepts(
    q: str = "",
    db: Session = Depends(get_db),
):
    """Search for specific concepts across documents."""
    from api.db.models import RagDocument
    from api.services.rag_service import retrieve_chunks

    if not q.strip():
        return {"results": []}

    chunks = await retrieve_chunks(q, db, top_k=6)
    return {
        "results": [
            {
                "text": c.get("text", "")[:300],
                "source": c.get("source", ""),
                "page_num": c.get("page_num"),
                "score": c.get("score", 0),
            }
            for c in chunks
        ]
    }
