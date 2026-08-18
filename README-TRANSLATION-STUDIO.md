# Translation Studio (standalone clone)

A standalone clone of the **Translation** feature from the X-Ray Expert
Assistant platform, prepared to run on a local domain and — after testing on
many real files — to be published as a web translation service.

> **This is a CLONE.** It was copied from the main platform and is fully
> isolated from it. Work here **does not affect** the translation feature in the
> main platform.

## Isolation guarantees

- **Separate database.** Uses its own SQLite file `translation_studio.db`
  (see `backend/.env`, `DATABASE_URL`), a distinct name that can never collide
  with the platform's `xray_local.db`. Runs from the clone's own `backend/`
  directory.
- **No shared services.** The heavy background jobs of the main platform
  (research agent, ColPali visual pre-warm, connector sync/health, workspace
  index sweep, source-trust worker) are disabled in `backend/main.py`.
- **Secrets are gitignored.** `backend/.env` (API keys) is excluded from git.

## What was kept vs. removed (Phase 0–1)

Decision: **pure translation product** — `learning-hub` was dropped.

**Frontend (`artifacts/xray-academy/src`)** — routed pages in `App.tsx`:
- `/` and `/translation` → Translation Studio
- `/translation-dictionary` → Glossary & translation memory
- `/translation/cost` → Cost & usage
- `/translation/images/:id` → In-image translation editor
- `/settings`

All other platform pages still exist in `src/pages/` but are **not routed**.
The Translation Studio's PPTX "layout style profile" dropdown calls
`/api/learning/styles`; that endpoint is not wired in this clone, and the UI
degrades gracefully to an empty list (layout mode defaults to "original").

**Backend (`api/routes/__init__.py`)** — only these routers are registered:
`health`, `auth`, `providers`, `img_translation`, `translation`. Every other
router module still exists in `api/routes/` but is not wired. Heavy startup
schedulers were also removed from `main.py`.

## Cross-platform document export (Phase 2 — done)

Document finalization/export now picks its engine at runtime via
`api/utils/document_finalizer.py`:

| Operation | Windows (this machine) | Linux (deployment) |
|-----------|------------------------|--------------------|
| DOCX finalize | Microsoft Word COM | LibreOffice headless |
| DOCX/PPTX → PDF | Word/PowerPoint COM | LibreOffice headless |
| PPTX rebuild | python-pptx (RTL-aware) | same |
| XLSX / PDF(build) | pure Python | same |

- New: `api/utils/libreoffice_finalizer.py` (headless LibreOffice engine),
  `api/utils/document_finalizer.py` (Word/PPT-COM → LibreOffice → error dispatcher).
- `_word_finalize_or_503` and the SSE pipeline's finalize step both route through
  the dispatcher, so no code path is hard-wired to Windows-only Office any more.
- **Linux server requirement:** install LibreOffice (`apt-get install -y
  libreoffice`) or set `LIBREOFFICE_PATH` to the `soffice` binary.
- ⚠️ **Still to quality-test:** LibreOffice's DOCX round-trip and PDF output
  against real files (esp. Arabic RTL, fonts, tables). Test against LibreOffice —
  NOT local Word — so tested quality matches the Linux production output.

## Pending

1. **Dependency install + first run** (not done yet): `pnpm install`, create the
   Python venv, verify the backend imports and the frontend builds/runs.
2. **Quality testing** on many real files against the LibreOffice engine.
3. Local domain (hosts + Caddy) and pre-publish hardening (auth, cost ceilings).

## Running locally (verified working)

Runs on **isolated ports 8001 (backend) / 5174 (frontend)** so it never collides
with the main platform's 8000 / 5173.

```bash
# 1) Backend deps (lean set — excludes torch/colpali/playwright/etc.)
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-translation.txt

# 2) Frontend deps (from repo root)
pnpm install    # exit-1 on "ignored builds" is harmless; esbuild binary is present

# 3) Run backend (port 8001; loads backend/.env automatically)
cd backend && ./.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001

# 4) Run frontend (port 5174, proxies /api -> 8001)
cd artifacts/xray-academy
FRONTEND_PORT=5174 PORT=5174 BACKEND_PORT=8001 \
  node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174 --strictPort
# open http://127.0.0.1:5174
```

Notes:
- `.claude/launch.json` has `backend` + `frontend` configs on these ports.
- Local dev auth: `backend/.env` sets `DISABLE_AUTH=true`; the frontend
  auto-creates a dev session via `POST /api/auth/mock` in `vite dev`
  (`import.meta.env.DEV`). Production builds keep the real auth gate.
- `.env` is gitignored (holds API keys). Set `ACTIVE_PROVIDER` and provider keys
  there for real translations; the default is the free `mock` provider.
