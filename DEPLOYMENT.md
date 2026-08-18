# Deployment guide — Translation Studio

How to take this clone from the local domain to a public Linux server.

## 0. What already works (local)

- Single-origin app served by FastAPI: `http://translate.localhost:8001`
  (built SPA + `/api`). Dev UI with HMR: `http://translate.localhost:5174`.
- All translation fixes active (already-Arabic skip, `<a:cs>` Arabic font, RTL
  brackets, reconstructed rebuild path, PPTX crash guard, review timeout).
- Isolated DB `translation_studio.db`. Native MS-Office COM path is OFF
  (`NATIVE_OFFICE_TRANSLATE` default false) so local output == Linux output.

## 1. Server prerequisites (Linux)

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libreoffice tesseract-ocr \
  tesseract-ocr-ara tesseract-ocr-eng tesseract-ocr-fra tesseract-ocr-spa \
  tesseract-ocr-rus fonts-noto fonts-amiri
# Node 20+ and pnpm for building the frontend
```

- **LibreOffice is required** for DOCX finalize + DOCX/PPTX→PDF export
  (`api/utils/libreoffice_finalizer.py`). Verify: `soffice --version`.
- Arabic fonts (Amiri/Noto) improve LibreOffice PDF rendering of Arabic.

## 2. Build & install

```bash
# backend
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements-translation.txt

# frontend (from repo root)
pnpm install
cd artifacts/xray-academy && node node_modules/vite/bin/vite.js build   # -> dist/public
```

## 3. Environment (`backend/.env`)

```ini
# Runtime
DATABASE_URL=sqlite:///./translation_studio.db     # or postgresql://... for scale
PORT=8000
XRAY_RUNTIME_ENV=production
NODE_ENV=production

# Auth — TODO before public launch (currently deferred; dev bypass is DEV-only)
DISABLE_AUTH=false                                 # MUST be false in production
SESSION_SECRET=<generate a long random 48+ char secret>

# Translation providers (set the ones you use)
ANTHROPIC_API_KEY=...            # ai_provider=claude
# OPENAI_API_KEY=...             # gpt-4o-mini default + engineering review
# GEMINI_API_KEY=...

# Cost & abuse ceilings (server-enforced — see api/utils/cost_guard.py)
# ⚠️ GOTCHA: DISABLE_AUTH=true makes cost_guard assume "dev mode" and DISABLE all
# ceilings. For an open/free public launch (no auth) you MUST force them on:
DEVELOPMENT_MODE=false
TRANSLATION_LOCALHOST_UNLIMITED=false
DISABLE_TRANSLATION_RATE_LIMIT=false
DISABLE_HOURLY_QUOTA=false
DISABLE_DAILY_QUOTA=false
DISABLE_MONTHLY_QUOTA=false

TRANSLATION_ENABLED=true                 # kill switch: set false to stop all jobs
OPENAI_TRANSLATION_MODEL=gpt-4o-mini     # cheapest; ≈2–3¢/doc
OPENAI_REVIEW_MODEL=gpt-4o-mini          # cheap review (vs gpt-4o = 16× pricier)
MAX_FILE_SIZE_MB=200
MAX_SEGMENTS_PER_JOB=1500
MAX_CHARS_PER_JOB=200000
MAX_REQUESTS_PER_USER_PER_HOUR=40
MAX_CONCURRENT_TRANSLATIONS=2
MAX_COST_PER_JOB_USD=0.50                # free-launch caps (raise later)
MAX_DAILY_API_COST_USD=3
MAX_MONTHLY_API_COST_USD=40
CONFIRM_SEGMENTS_THRESHOLD=200
CONFIRM_CHARS_THRESHOLD=60000
ENGINEERING_REVIEW_TIMEOUT_S=120

# Keep native MS-Office OFF on Linux (no COM there anyway); LibreOffice is used.
NATIVE_OFFICE_TRANSLATE=false

# Admin access (unlock the full control panel at /admin). CHANGE THIS.
ADMIN_KEY=<your-own-strong-secret>

# Auto-delete uploaded projects + files after N hours (storage hygiene/privacy).
PROJECT_RETENTION_HOURS=24

# Inbound rate limits (raise for a browser SPA; the default auth budget of 15/min
# is too tight because each page load makes several /api/auth checks).
RATE_LIMIT_REQUESTS=600
RATE_LIMIT_WINDOW_S=60
RATE_LIMIT_AUTH_REQUESTS=120
RATE_LIMIT_AUTH_WINDOW_S=60
```

> Production refuses to start with an insecure config (short SESSION_SECRET,
> DISABLE_AUTH=true) — see `main.py` `validate_production_secrets`.

## 4. Run

```bash
cd backend && ./.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```
FastAPI serves the built SPA + API on one origin.

## 5. Reverse proxy + TLS (Caddy — clean domain, HTTPS)

`/etc/caddy/Caddyfile`:
```
translate.example.com {
    reverse_proxy 127.0.0.1:8000
}
```
`sudo systemctl reload caddy` — Caddy auto-provisions HTTPS.

## Pre-launch checklist

- [ ] **Auth**: implement real login (deferred) and set `DISABLE_AUTH=false`.
- [ ] Long random `SESSION_SECRET`; secrets only in env, never in git.
- [ ] `soffice --version` works; test a real Arabic DOCX/PPTX export end-to-end
      **against LibreOffice** (not Word) — confirm fonts/RTL/brackets.
- [ ] Cost ceilings reviewed for expected volume; `TRANSLATION_ENABLED` kill
      switch tested.
- [ ] File-upload limits verified (size/type); consider malware scanning for
      public uploads.
- [ ] Backups for `translation_studio.db` (or move to managed PostgreSQL).
