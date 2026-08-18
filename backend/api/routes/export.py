"""
Export Engine — generate printable HTML reports from any module's data.
All exports are self-contained HTML (no external CSS dependencies).
"""
from __future__ import annotations
import json
import logging
import re
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.middleware.auth import optional_auth

router = APIRouter(tags=["export"])

# ── Shared report styles ─────────────────────────────────────────────────────

REPORT_CSS = """
<style>
  :root { --primary: #2563eb; --text: #0f172a; --muted: #64748b; --border: #e2e8f0; --bg: #f8fafc; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: var(--text); background: white; font-size: 14px; line-height: 1.6; }
  .page { max-width: 900px; margin: 0 auto; padding: 48px 40px; }
  .header { border-bottom: 3px solid var(--primary); padding-bottom: 24px; margin-bottom: 32px; display: flex; justify-content: space-between; align-items: flex-start; }
  .logo { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; color: var(--primary); }
  .title { font-size: 28px; font-weight: 800; color: var(--text); margin-top: 8px; }
  .subtitle { font-size: 13px; color: var(--muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
  .meta { text-align: right; font-size: 12px; color: var(--muted); }
  .meta strong { display: block; color: var(--text); font-size: 13px; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
  .badge-clear { background: #dcfce7; color: #166534; }
  .badge-low { background: #fef9c3; color: #854d0e; }
  .badge-medium { background: #ffedd5; color: #9a3412; }
  .badge-high { background: #fee2e2; color: #991b1b; }
  .badge-critical { background: #dc2626; color: white; }
  .badge-primary { background: #dbeafe; color: #1e40af; }
  h2 { font-size: 15px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--primary); margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
  h3 { font-size: 13px; font-weight: 700; margin: 16px 0 8px; color: var(--text); }
  p { margin-bottom: 10px; color: #334155; }
  ul { margin: 8px 0 12px 20px; }
  li { margin-bottom: 4px; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }
  th { background: var(--bg); padding: 8px 12px; text-align: left; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); border: 1px solid var(--border); }
  td { padding: 8px 12px; border: 1px solid var(--border); vertical-align: top; }
  tr:nth-child(even) td { background: var(--bg); }
  .result-box { background: var(--bg); border: 2px solid var(--primary); border-radius: 8px; padding: 20px 24px; margin: 16px 0; }
  .result-value { font-size: 40px; font-weight: 900; color: var(--primary); font-family: 'Courier New', monospace; }
  .result-unit { font-size: 16px; color: var(--muted); margin-left: 8px; }
  .formula-box { background: #f0f4ff; border-left: 4px solid var(--primary); padding: 12px 16px; font-family: 'Courier New', monospace; font-size: 14px; color: #1e40af; margin: 12px 0; border-radius: 0 6px 6px 0; }
  .step { display: flex; gap: 12px; margin-bottom: 8px; align-items: flex-start; }
  .step-num { min-width: 24px; height: 24px; background: var(--primary); color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
  .step-text { font-family: 'Courier New', monospace; font-size: 12px; padding-top: 3px; color: #334155; }
  .warning { background: #fffbeb; border: 1px solid #f59e0b; border-radius: 6px; padding: 10px 14px; font-size: 12px; color: #92400e; margin: 8px 0; }
  .footer { margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--border); font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; }
  .findings-text { white-space: pre-wrap; font-size: 13px; line-height: 1.7; color: #334155; background: var(--bg); padding: 16px; border-radius: 6px; border: 1px solid var(--border); }
  .rec-item { display: flex; gap: 10px; margin-bottom: 8px; }
  .rec-num { min-width: 22px; height: 22px; background: #dbeafe; color: #1e40af; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; margin-top: 1px; }
    .paper-article { font-family: Georgia, 'Times New Roman', serif; }
    .paper-title { font-size: 28px; font-weight: 800; line-height: 1.2; letter-spacing: -0.02em; color: #0f172a; margin-bottom: 8px; }
    .paper-authors { font-size: 15px; font-weight: 700; color: #111827; margin-bottom: 2px; }
    .paper-affiliation { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
    .paper-meta { font-size: 12px; color: var(--muted); margin-bottom: 16px; }
    .paper-article h2 { text-transform: none; letter-spacing: 0; font-size: 18px; color: #111827; border-bottom: 1px solid #dbe3ee; margin-top: 24px; }
    .paper-article h3 { font-size: 15px; }
    .paper-article p { text-align: justify; }
  @media print { .page { padding: 24px; } .no-print { display: none; } }
</style>
"""


def _now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def _html_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — X-Ray Academy Report</title>
  {REPORT_CSS}
</head>
<body>
  <div class="page">
    {body}
    <div class="footer">
      <span>X-Ray Research Innovation Platform</span>
      <span>Generated {_now_str()} · Confidential</span>
    </div>
  </div>
  <div class="no-print" style="text-align:center;padding:20px;background:#f1f5f9;border-top:1px solid #e2e8f0;">
    <button onclick="window.print()" style="padding:10px 28px;background:#2563eb;color:white;border:none;border-radius:6px;font-weight:700;cursor:pointer;font-size:14px;">🖨 Print / Save PDF</button>
  </div>
</body>
</html>"""


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/export/research/{output_id}", response_class=HTMLResponse)
def export_research_report(
    output_id: str,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """Export a research output as a printable HTML report."""
    from api.db.models import ResearchOutput
    output = db.query(ResearchOutput).filter(ResearchOutput.id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Research output not found")

    from api.utils.docgen import _publication_mode_label, extract_paper_title, sanitize_export_filename, _strip_offer_footer
    from api.utils.research_quality import score_publication_quality, generate_publication_readiness_report

    mode_label = _publication_mode_label(output.mode)
    stripped_content = _strip_offer_footer(output.content or "")
    paper_title = extract_paper_title(stripped_content, fallback=output.topic or "Research Report")

    # The 0-100 aggregate score below stays informational-only (an arbitrary
    # bar is easy to miss for reasons that don't matter). Export instead
    # blocks on the named, specific acceptance-test defects: thin/unverified
    # reference base, title-content mismatch, leaked citation placeholders or
    # Mermaid source, unrendered figures, and unsupported claims.
    readiness_meta = getattr(output, "readiness_meta", None) or {}
    readiness = generate_publication_readiness_report(
        stripped_content,
        mode=output.mode,
        reference_meta=readiness_meta.get("reference_meta"),
        has_real_experiment=bool(readiness_meta.get("has_real_experiment", False)),
    )
    if readiness.critical_issues:
        log.info(
            "HTML export blocked for research output %s: refs=%d peer_reviewed_ratio=%.2f alignment=%.2f issues=%s",
            output.id, readiness.reference_count, readiness.peer_reviewed_ratio,
            readiness.title_content_alignment, readiness.critical_issues,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "not_publication_ready",
                "message": "This draft isn't ready for export yet. Try regenerating the paper, or rephrase the topic to be more specific.",
            },
        )

    quality = score_publication_quality(stripped_content, mode=output.mode)
    quality_warning_html = ""
    if quality.score < 95:
        issues_html = "".join(f"<li>{issue}</li>" for issue in quality.issues)
        quality_warning_html = f"""
        <div class="warning">
          <strong>Draft quality score: {quality.score}/100</strong> (publication-ready threshold: 95)
          <ul style="margin-top:6px;">{issues_html}</ul>
        </div>
        """

    # Convert markdown-ish content to basic HTML (strip any GPT offer-footers first)
    content_html = _md_to_html(stripped_content)

    body = f"""
    <div class="header">
      <div>
        <div class="logo">X-Ray Academy · Research Intelligence</div>
                <div class="title">{paper_title}</div>
        <div class="subtitle">{mode_label}</div>
      </div>
      <div class="meta">
        <strong>{_now_str()}</strong>
        Report ID: {output.id[:8].upper()}<br>
        Words: {output.word_count or len((output.content or '').split())}
      </div>
    </div>
        <div class="paper-article">
            <div class="paper-title">{paper_title}</div>
            <div class="paper-authors">Mohamed Noaman</div>
            <div class="paper-affiliation">X-Ray Academy Research Intelligence Platform</div>
            <div class="paper-meta">{mode_label} · Publication quality score {quality.score}/100</div>
            {quality_warning_html}
            <div>{content_html}</div>
        </div>
    """
    from api.utils.filename_helper import content_disposition
    filename = sanitize_export_filename(paper_title, ".html")
    return Response(
        content=_html_page(paper_title, body),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/export/analysis/{analysis_id}", response_class=HTMLResponse)
def export_analysis_report(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """Export an X-ray analysis as a printable security report."""
    from api.db.models import XrayAnalysis
    analysis = db.query(XrayAnalysis).filter(XrayAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    threat = (analysis.threat_level or "unknown").lower()
    badge_class = f"badge-{threat}" if threat in ("clear", "low", "medium", "high", "critical") else "badge-primary"
    recs = analysis.recommendations or []
    if isinstance(recs, str):
        try:
            recs = json.loads(recs)
        except Exception:
            recs = [recs]

    recs_html = "".join(
        f'<div class="rec-item"><div class="rec-num">{i+1}</div><div>{r}</div></div>'
        for i, r in enumerate(recs)
    )

    body = f"""
    <div class="header">
      <div>
        <div class="logo">X-Ray Academy · Threat Analysis Report</div>
        <div class="title">X-Ray Security Assessment</div>
        <div class="subtitle">{analysis.filename} · {analysis.scanner_type} Scanner</div>
      </div>
      <div class="meta">
        <strong><span class="badge {badge_class}">{threat.upper()} THREAT</span></strong>
        {analysis.created_at.strftime('%Y-%m-%d %H:%M UTC') if analysis.created_at else _now_str()}<br>
        Report ID: {analysis.id[:8].upper()}
      </div>
    </div>

    <h2>Scan Information</h2>
    <table>
      <tr><th>Field</th><th>Value</th></tr>
      <tr><td>Filename</td><td>{analysis.filename}</td></tr>
      <tr><td>Scanner Type</td><td>{analysis.scanner_type}</td></tr>
      <tr><td>Threat Assessment</td><td><span class="badge {badge_class}">{threat.upper()}</span></td></tr>
      <tr><td>Analysis Date</td><td>{analysis.created_at.strftime('%Y-%m-%d %H:%M UTC') if analysis.created_at else 'N/A'}</td></tr>
      <tr><td>Report ID</td><td>{analysis.id}</td></tr>
    </table>

    <h2>Detailed Findings</h2>
    <div class="findings-text">{analysis.findings or 'No findings recorded.'}</div>

    <h2>Recommended Protocols</h2>
    {'<div>' + recs_html + '</div>' if recs else '<p>No specific protocols recommended.</p>'}

    <h2>Legal Disclaimer</h2>
    <p>This report is generated by an AI-assisted analysis system and is intended as a decision-support tool only.
    All threat assessments must be confirmed by a qualified security operator. This report does not constitute
    an official security clearance or regulatory finding.</p>
    """
    return HTMLResponse(_html_page(f"Analysis: {analysis.filename}", body))


@router.get("/export/education/{content_type}", response_class=HTMLResponse)
def export_education_template(content_type: str, topic: str = "X-Ray Technology"):
    """Export an education module template shell as a printable document."""
    body = f"""
    <div class="header">
      <div>
        <div class="logo">X-Ray Academy · Education Studio</div>
        <div class="title">{topic}</div>
        <div class="subtitle">{content_type.replace('_', ' ').title()}</div>
      </div>
      <div class="meta"><strong>{_now_str()}</strong>Education Document</div>
    </div>
    <p style="color:#64748b;font-style:italic">This document was generated by the X-Ray Academy Education Studio AI. Review and customise before official distribution.</p>
    <p>Content generated in platform — open document in Education Studio for full markdown rendering.</p>
    """
    return HTMLResponse(_html_page(topic, body))


# ── Markdown → HTML helper ─────────────────────────────────────────────────

_MD_IMAGE_RE = re.compile(r'^!\[(.*?)\]\((.+?)\)$')
_MIME_BY_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}


def _image_to_data_uri(path: str) -> Optional[str]:
    """Read a figure file from disk and inline it as a base64 data URI so the
    exported HTML stays fully self-contained (no external file references)."""
    import base64
    import os as _os
    raw = (path or "").strip().strip('"').strip("'")
    if raw.lower().startswith("file://"):
        from urllib.parse import unquote, urlparse
        raw = unquote(urlparse(raw).path.lstrip("/"))
    if not raw or not _os.path.isfile(raw):
        return None
    ext = _os.path.splitext(raw)[1].lower()
    mime = _MIME_BY_EXT.get(ext, "application/octet-stream")
    try:
        with open(raw, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except Exception:
        return None


def _md_to_html(text: str) -> str:
    """Lightweight markdown → HTML converter (no external deps)."""
    import re
    lines = text.split("\n")
    html_lines = []
    in_list = False
    in_code = False
    code_lang = ""
    code_buf: list[str] = []
    in_table = False
    table_rows: list[list[str]] = []

    def _flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return
        data_rows = [r for r in table_rows if not all(set(c) <= set("-: ") for c in r)]
        if not data_rows:
            table_rows = []
            in_table = False
            return
        ncols = max(len(r) for r in data_rows)
        padded = [r + [""] * (ncols - len(r)) for r in data_rows]
        html_lines.append("<table>")
        html_lines.append("<tr>" + "".join(f"<th>{_inline_md(c)}</th>" for c in padded[0]) + "</tr>")
        for row in padded[1:]:
            html_lines.append("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in row) + "</tr>")
        html_lines.append("</table>")
        table_rows = []
        in_table = False

    for line in lines:
        if line.startswith("```"):
            if in_code:
                in_code = False
                # Figures are rendered as real images and referenced via
                # markdown image syntax (handled below) — a mermaid fence
                # must never survive into the exported HTML as literal text.
                if code_lang != "mermaid" and code_buf:
                    html_lines.append('<pre style="background:#f1f5f9;padding:12px;border-radius:6px;font-size:12px;overflow-x:auto"><code>')
                    html_lines.extend(c.replace("<", "&lt;").replace(">", "&gt;") for c in code_buf)
                    html_lines.append("</code></pre>")
                code_buf = []
                code_lang = ""
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                if in_table:
                    _flush_table()
                in_code = True
                code_lang = line[3:].strip().lower()
            continue

        if in_code:
            code_buf.append(line)
            continue

        img_match = _MD_IMAGE_RE.match(line.strip())
        if img_match:
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_table: _flush_table()
            alt_text = img_match.group(1).strip() or "Figure"
            data_uri = _image_to_data_uri(img_match.group(2))
            if data_uri:
                html_lines.append(f'<img src="{data_uri}" alt="{_inline_md(alt_text)}" style="max-width:100%;height:auto;margin:8px 0;">')
                html_lines.append(f'<p style="font-size:12px;color:#64748b;text-align:center;">{_inline_md(alt_text)}</p>')
            continue

        if line.strip().startswith("|") and "|" in line.strip():
            if in_list: html_lines.append("</ul>"); in_list = False
            in_table = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            table_rows.append(cells)
            continue
        elif in_table:
            _flush_table()

        # Headers
        if line.startswith("#### "):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<h3>{_inline_md(line[5:])}</h3>")
        elif line.startswith("### "):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<h2>{_inline_md(line[4:])}</h2>")
        elif line.startswith("## "):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<h2>{_inline_md(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<h2 style='font-size:20px'>{_inline_md(line[2:])}</h2>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline_md(line[2:])}</li>")
        elif re.match(r"^\d+\. ", line):
            if in_list: html_lines.append("</ul>"); in_list = False
            content = re.sub(r"^\d+\. ", "", line)
            html_lines.append(f"<p>{_inline_md(content)}</p>")
        elif line.strip() == "":
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append("<br>")
        elif line.startswith("---"):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append("<hr style='border:none;border-top:1px solid #e2e8f0;margin:16px 0'>")
        else:
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<p>{_inline_md(line)}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_table:
        _flush_table()
    if in_code and code_buf and code_lang != "mermaid":
        html_lines.append('<pre style="background:#f1f5f9;padding:12px;border-radius:6px;font-size:12px;overflow-x:auto"><code>')
        html_lines.extend(c.replace("<", "&lt;").replace(">", "&gt;") for c in code_buf)
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)


def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, code) to HTML."""
    import re
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r'<code style="background:#f1f5f9;padding:1px 5px;border-radius:3px;font-size:12px">\1</code>', text)
    return text
