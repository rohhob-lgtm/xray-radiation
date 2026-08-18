"""
Book Authoring Studio — compile chapters into one document and export it.

DOCX/PDF export delegates to api.services.workspace_agent.doc_builder's
plain python-docx/reportlab builders — Microsoft Word COM is never a
dependency here (it may only be reused later as an optional finalization
backend, not for creating the book).

HTML export is a small, self-contained markdown → HTML converter — not
imported from routes/export.py, whose _md_to_html/_image_to_data_uri are
private helpers in a file this module must not touch or depend on.
"""
from __future__ import annotations

import base64
import html as html_mod
import os
import re
from datetime import datetime, timezone


def compile_book(project, chapters, references, figures, tables) -> str:
    """Assemble approved chapter content (+ references/figures/tables) into
    one Markdown document, in chapter order."""
    parts: list[str] = [f"# {project.title}\n"]
    if project.topic:
        parts.append(f"*{project.topic}*\n")

    figures_by_chapter: dict[str | None, list] = {}
    for fig in figures:
        figures_by_chapter.setdefault(fig.chapter_id, []).append(fig)
    tables_by_chapter: dict[str | None, list] = {}
    for tbl in tables:
        tables_by_chapter.setdefault(tbl.chapter_id, []).append(tbl)

    for chapter in sorted(chapters, key=lambda c: c.chapter_number):
        parts.append(f"\n## Chapter {chapter.chapter_number}: {chapter.title}\n")
        parts.append(chapter.content or "*(not yet generated)*")

        for fig in sorted(figures_by_chapter.get(chapter.id, []), key=lambda f: f.order_index):
            parts.append(f"\n![{fig.caption}]({fig.storage_path})\n")
        for tbl in sorted(tables_by_chapter.get(chapter.id, []), key=lambda t: t.order_index):
            parts.append(f"\n**Table: {tbl.caption}**\n\n{_render_md_table(tbl.table_data)}\n")

    book_wide_figures = sorted(figures_by_chapter.get(None, []), key=lambda f: f.order_index)
    book_wide_tables = sorted(tables_by_chapter.get(None, []), key=lambda t: t.order_index)
    if book_wide_figures or book_wide_tables:
        parts.append("\n## Additional Figures & Tables\n")
        for fig in book_wide_figures:
            parts.append(f"\n![{fig.caption}]({fig.storage_path})\n")
        for tbl in book_wide_tables:
            parts.append(f"\n**Table: {tbl.caption}**\n\n{_render_md_table(tbl.table_data)}\n")

    if references:
        parts.append("\n## References\n")
        for i, ref in enumerate(sorted(references, key=lambda r: r.order_index), start=1):
            suffix = f" — {ref.source_url}" if ref.source_url else ""
            parts.append(f"{i}. {ref.citation_text}{suffix}")

    return "\n".join(parts)


def _render_md_table(table_data: dict) -> str:
    headers = table_data.get("headers") or []
    rows = table_data.get("rows") or []
    if not headers:
        return ""
    lines = ["| " + " | ".join(str(h) for h in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def export_docx(title: str, markdown_body: str, lang: str = "en") -> bytes:
    from api.services.workspace_agent.doc_builder import build_word_document
    return build_word_document(title, markdown_body, lang=lang)


def export_pdf(title: str, markdown_body: str, lang: str = "en") -> bytes:
    from api.services.workspace_agent.doc_builder import build_pdf_document
    return build_pdf_document(title, markdown_body, lang=lang)


# ── Minimal self-contained Markdown → HTML (book export only) ──────────────

_MD_IMAGE_RE = re.compile(r'^!\[(.*?)\]\((.+?)\)$')
_MIME_BY_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}


def _image_to_data_uri(path: str) -> str | None:
    raw = (path or "").strip().strip('"').strip("'")
    if not raw or not os.path.isfile(raw):
        return None
    ext = os.path.splitext(raw)[1].lower()
    mime = _MIME_BY_EXT.get(ext, "application/octet-stream")
    try:
        with open(raw, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except Exception:
        return None


def _inline_md(text: str) -> str:
    text = html_mod.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def _md_to_html_body(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    in_list = False
    in_table = False
    table_rows: list[list[str]] = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return
        data_rows = [r for r in table_rows if not all(set(c) <= set("-: ") for c in r)]
        if data_rows:
            ncols = max(len(r) for r in data_rows)
            padded = [r + [""] * (ncols - len(r)) for r in data_rows]
            out.append("<table>")
            out.append("<tr>" + "".join(f"<th>{_inline_md(c)}</th>" for c in padded[0]) + "</tr>")
            for row in padded[1:]:
                out.append("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in row) + "</tr>")
            out.append("</table>")
        table_rows = []
        in_table = False

    for line in lines:
        stripped = line.strip()
        img = _MD_IMAGE_RE.match(stripped)
        if img:
            if in_list: out.append("</ul>"); in_list = False
            if in_table: flush_table()
            data_uri = _image_to_data_uri(img.group(2))
            if data_uri:
                out.append(f'<img src="{data_uri}" alt="{_inline_md(img.group(1))}" style="max-width:100%;">')
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            if in_list: out.append("</ul>"); in_list = False
            in_table = True
            table_rows.append([c.strip() for c in stripped.strip("|").split("|")])
            continue
        elif in_table:
            flush_table()

        if line.startswith("### "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h3>{_inline_md(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h2>{_inline_md(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h1>{_inline_md(line[2:])}</h1>")
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline_md(stripped[2:])}</li>")
        elif re.match(r"^\d+\. ", stripped):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<p>{_inline_md(re.sub(r'^\d+\. ', '', stripped))}</p>")
        elif stripped == "":
            if in_list: out.append("</ul>"); in_list = False
        else:
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<p>{_inline_md(line)}</p>")

    if in_list:
        out.append("</ul>")
    if in_table:
        flush_table()
    return "\n".join(out)


def export_html(title: str, markdown_body: str) -> bytes:
    body_html = _md_to_html_body(markdown_body)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html_mod.escape(title)}</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 860px; margin: 0 auto; padding: 48px 32px; line-height: 1.7; color: #1a1a1a; }}
  h1 {{ font-size: 32px; }} h2 {{ font-size: 24px; margin-top: 40px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  .footer {{ margin-top: 48px; font-size: 12px; color: #888; }}
</style>
</head>
<body>
{body_html}
<div class="footer">Generated {now}</div>
</body>
</html>"""
    return html.encode("utf-8")
