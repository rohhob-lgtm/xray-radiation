"""
Server-side figure rendering for Research Studio manuscripts.

Replaces Mermaid fenced code blocks (which every export format — DOCX, PDF,
and HTML — previously dumped as literal, unrendered text) with real
high-resolution raster images produced by matplotlib. Figures are written to
disk and referenced via standard markdown image syntax (``![alt](path)``),
which the existing DOCX/PDF/HTML embedding code already understands.

No new dependency: matplotlib is already installed for this project.
"""
from __future__ import annotations

import os
import re
import tempfile
import uuid

import matplotlib
matplotlib.use("Agg")  # headless — no display server available on the backend
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrow, FancyBboxPatch

_FIGURE_DPI = 200


def figures_dir(run_id: str) -> str:
    path = os.path.join(tempfile.gettempdir(), "xray_research_figures", run_id or "shared")
    os.makedirs(path, exist_ok=True)
    return path


def _new_path(run_id: str, name: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:60]
    return os.path.join(figures_dir(run_id), f"{safe_name}_{uuid.uuid4().hex[:8]}.png")


def render_source_type_pie(counts: dict[str, int], run_id: str) -> str:
    """Pie chart of evidence source-type distribution. Returns the saved PNG path."""
    labels = list(counts.keys()) or ["No verified sources"]
    values = list(counts.values()) or [1]
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    ax.pie(values, labels=labels, autopct=lambda p: f"{p:.0f}%" if p > 0 else "", startangle=90)
    ax.set_title("Source-Type Distribution")
    ax.axis("equal")
    path = _new_path(run_id, "source_type_pie")
    fig.savefig(path, dpi=_FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def render_year_bar(counts: dict[str, int], run_id: str) -> str:
    """Bar chart of evidence publication-year distribution. Returns the saved PNG path."""
    years = sorted(counts.keys())
    values = [counts[y] for y in years]
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    ax.bar(years, values, color="#2563eb")
    ax.set_xlabel("Publication Year")
    ax.set_ylabel("Reference Count")
    ax.set_title("Publication-Year Distribution")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    path = _new_path(run_id, "year_bar")
    fig.savefig(path, dpi=_FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def render_flow_diagram(title: str, stages: list[str], run_id: str, name: str, horizontal: bool = False) -> str:
    """Simple box-and-arrow pipeline/architecture/taxonomy diagram.

    Draws each entry in `stages` as a labeled box connected by arrows to the
    next — enough to cover architecture, workflow, pipeline, and taxonomy
    figures without a diagramming dependency. Text wraps automatically at the
    box width.
    """
    n = max(1, len(stages))
    fig_w, fig_h = (max(8.0, n * 2.0), 2.5) if horizontal else (7.0, max(3.0, n * 1.3))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")
    ax.set_title(title, fontsize=13, fontweight="bold", pad=14)

    box_w, box_h = (1.7, 0.9) if horizontal else (5.5, 0.8)
    gap = 0.6

    for i, label in enumerate(stages):
        if horizontal:
            x, y = i * (box_w + gap), 0
        else:
            x, y = 0, -i * (box_h + gap)
        box = FancyBboxPatch(
            (x, y), box_w, box_h,
            boxstyle="round,pad=0.08,rounding_size=0.08",
            linewidth=1.4, edgecolor="#1e40af", facecolor="#dbeafe",
        )
        ax.add_patch(box)
        ax.text(
            x + box_w / 2, y + box_h / 2, label,
            ha="center", va="center", fontsize=9.5, wrap=True, color="#0f172a",
        )
        if i > 0:
            if horizontal:
                ax.add_patch(FancyArrow(
                    x - gap, y + box_h / 2, gap - 0.1, 0,
                    width=0.02, head_width=0.18, head_length=0.12, color="#334155",
                ))
            else:
                ax.add_patch(FancyArrow(
                    x + box_w / 2, y + box_h + gap - 0.1, 0, -(gap - 0.15),
                    width=0.02, head_width=0.18, head_length=0.12, color="#334155",
                ))

    if horizontal:
        ax.set_xlim(-0.3, n * (box_w + gap))
        ax.set_ylim(-0.5, box_h + 0.5)
    else:
        ax.set_xlim(-0.3, box_w + 0.3)
        ax.set_ylim(-(n * (box_h + gap)), box_h + 0.5)
    ax.set_aspect("equal" if False else "auto")

    path = _new_path(run_id, name)
    fig.savefig(path, dpi=_FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    return path
