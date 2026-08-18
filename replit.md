# X-Ray Research & Innovation Assistant

ADVANCED RESEARCH PLATFORM

An AI-powered assistant for X-ray physics, security screening, academic research, and detector technology. Provides expert chat support, scientific research generation, physics calculations, patent analysis, and technical report generation — all powered by a pluggable AI provider system.

## Run & Operate

- `artifacts/api-server: API Server` workflow — runs the Python FastAPI backend (port 8080)
- `artifacts/xray-academy: web` workflow — runs the React frontend (port 23500)
- `pnpm --filter @workspace/api-spec run codegen` — regenerate React Query hooks from OpenAPI spec
- `pnpm run typecheck` — full typecheck across all packages

## Stack

- **Frontend**: React + Vite, TailwindCSS, TanStack React Query, Wouter routing
- **Backend**: Python 3.13 + FastAPI + Uvicorn (virtual env at `backend/.venv`)
- **AI Providers**: MockProvider (built-in), OpenAI, Ollama, Microsoft Copilot/Azure OpenAI
- **Monorepo**: pnpm workspaces, Node.js 24, TypeScript 5.9
- **API codegen**: Orval (from `lib/api-spec/openapi.yaml`)

## Where things live

- `backend/` — Python FastAPI backend (source of truth for API logic)
  - `backend/main.py` — FastAPI app entry point
  - `backend/api/routes/` — route handlers (chat, linkedin, upload, providers)
  - `backend/api/services/ai_providers/` — AI provider implementations
  - `backend/api/services/xray_knowledge.py` — domain knowledge base & system prompts
  - `backend/api/services/store.py` — in-memory data store (replace with DB for persistence)
  - `backend/api/config.py` — environment variable configuration
- `artifacts/xray-academy/src/` — React frontend
- `lib/api-spec/openapi.yaml` — OpenAPI contract (source of truth for types)
- `lib/api-client-react/src/generated/` — generated React Query hooks (do not edit)

## Architecture decisions

- **Python FastAPI over Node.js**: User requirement; FastAPI auto-generates OpenAPI docs at `/api/docs`
- **Provider abstraction**: `BaseAIProvider` abstract class allows swapping OpenAI/Ollama/Copilot without touching routes
- **MockProvider default**: App works fully out-of-the-box with curated X-ray domain knowledge, no API key required
- **In-memory store**: Simple dict-based store for initial build; replace `backend/api/services/store.py` with SQLAlchemy/PostgreSQL for persistence
- **`uv` for Python packages**: Nix environment requires a venv; packages live at `backend/.venv/`

## Product

- **Security Chat** — AI-powered Q&A on baggage/cargo/vehicle scanners, radiation safety, image interpretation, maintenance, and troubleshooting
- **X-Ray Analysis** — Upload an X-ray image (base64), choose scanner type, receive AI findings with threat level and recommendations
- **LinkedIn Post Generator** — Generate professional posts by topic, tone (professional/educational/thought leadership/case study/tips), and length
- **Provider Settings** — Switch between built-in knowledge base, OpenAI GPT-4o, Ollama (local), or Microsoft Copilot

## User preferences

---

## COST CONTROL & DEVELOPMENT GOVERNANCE POLICY

**Daily budget:** USD 15 | **Per-task target:** USD 1 | **Hard approval threshold:** USD 2

### Default Mode: ECONOMY MODE
- Minimum file reading — read only directly relevant files, start with the smallest likely set
- No parallel analysis unless explicitly requested
- Targeted tests only (modified file/function + one smoke test)
- No large-file tests without approval; use small test fixtures for debugging
- No repository-wide work without explicit authorization
- No optional enhancements or speculative refactoring
- One active task, one objective, one test cycle at a time

### Pre-Task Approval Gate (MANDATORY)
Before every task, show this card:
```
Task:
Requested outcome:
Files to read:
Files to change:
Tests to run:
Estimated duration:
Cost risk (Low / Medium / High):
Cheaper alternative (if any):
Approval required: Yes / No
```
- If cost risk may exceed USD 2: STOP, explain, propose cheaper alternative, wait for approval.
- Do not claim an exact cost is guaranteed — estimates only.
- Do not continue automatically with expensive tasks.

### Cost Guard States
| State | Daily spend | Rule |
|---|---|---|
| GREEN | $0–5 | Normal targeted work permitted |
| YELLOW | $5–10 | Warn before medium-complexity work |
| ORANGE | $10–13 | Essential targeted fixes only |
| RED | $13–15 | Every task needs approval |
| BUDGET REACHED | $15 | No new tasks without explicit override |

### Repository Access Policy
- Never scan or analyze the entire repository unless explicitly authorized.
- Never use instructions like "review the entire project", "inspect all files", "refactor the whole system".
- Read only directly relevant files. State which additional file is needed before opening it.
- Never reread unchanged files. Reuse existing project understanding, prior findings, logs, and memory.
- Expand scope only when evidence proves it is necessary.

### No Uncontrolled Parallel Work
- No broad parallel file reads. No multiple simultaneous repair branches.
- One active development task. One objective. One test cycle.
- Finish, report, wait — then start the next task only on approval.
- Do not automatically execute queued prompts after finishing the current task.

### Queue Control (default: PAUSED after each task)
After each task: stop → summarize result → report files changed + tests run + unresolved issues → wait for approval.

### Targeted Testing Only
- Unit test for the modified function; tests for the modified file; one smoke test for the affected feature.
- Full regression testing only: before a production release, after a major architectural change, or when explicitly requested.
- Never repeatedly translate large PPTX files to test a small code change — use the small test fixtures in `backend/tests/fixtures/`.

### Test Fixture Policy
Use lightweight fixtures in `backend/tests/fixtures/` for all routine debugging:
- `test_basic.pptx` — 2-slide basic deck
- `test_arabic_rtl.pptx` — Arabic RTL text slide
- `test_mixed.pptx` — mixed Arabic/English slide
- `test_image_caption.pptx` — image and caption slide
- `test_table.pptx` — table slide
- `test_groups.pptx` — grouped instructional objects slide
- `test_smartart.pptx` — SmartArt test slide
- `test_template.pptx` — template-style slide
Large-file testing (>5 MB) requires explicit approval.

### Change Protection
- Identify exact root cause and smallest safe change before modifying code.
- Never replace whole files when a targeted patch is sufficient.
- Preserve: existing working features, DB records, translation memory, learned styles, knowledge-base content, uploaded documents, existing APIs, user settings.

### Retry Limits
- Network request: 2 retries max
- Background job: 1 retry
- AI provider call: 1 retry
- File parsing: 1 controlled retry
- Translation job: no automatic full restart after partial success
After limit: stop, show exact error, preserve completed work, request approval.

### Job Time Limits
- Small code investigation: 5 min | Targeted coding task: 15 min | Targeted test: 5 min
- Repository-wide investigation: prohibited without approval
- Large PPTX test: prohibited without approval
If a task exceeds its expected time: pause, report what is consuming time, ask whether to continue.

### AI Model Cost Routing (cheapest first)
1. Deterministic local code → 2. Cached result → 3. Metadata lookup → 4. Translation memory → 5. Glossary → 6. Low-cost model → 7. Premium model (only when necessary) → 8. Vision model (only for actual visual analysis)
Never invoke a vision model because text contains "image", "picture", "screenshot", etc.
Never send images to a paid model when no image understanding is required.
Do not run OCR when editable PPTX text already exists.

### Agent Work Policy
The agent must not: reanalyze the whole project per prompt, rewrite working modules unnecessarily, generate large planning docs before small fixes, perform speculative refactoring, add unrequested features, continue working after the requested fix is done, run repeated compilations without new changes, restart services repeatedly without cause, make visual/architectural changes outside the requested scope.

---

## Gotchas

- Python packages must be installed via `uv pip install --python backend/.venv/bin/python -r backend/requirements.txt`; do NOT use `pip install --system` (blocked by Nix PEP 668)
- The API server workflow runs from `artifacts/api-server/` directory, so the `backend/` path in the dev command must be absolute: `/home/runner/workspace/backend`
- After any OpenAPI spec change, run codegen before using the updated hooks in the frontend
- The in-memory store resets on server restart — all conversations and posts are lost

## GitHub Backup Workflow

This repository is the primary backup for the project. Every completed task must be committed and pushed to `main` automatically after successful completion.

### Agent backup process (after each completed task)

1. Stage only the changes related to the completed task.
2. Commit with a clear, task-specific message: `Task: <short description>`.
3. Push to `origin/main` using the authenticated GitHub connection.
4. Do not push if tests are failing, if the task is incomplete, or if the work is broken.

### Automated backup tag

The GitHub Action in `.github/workflows/backup.yml` runs on every push to `main` and creates a timestamped backup tag (`backup-YYYYMMDD-HHMMSS-<short-sha>`). This keeps an immutable, chronological backup of every backed-up state without creating extra branches.

## Pointers

- Backend docs: `backend/README.md`
- Add a new AI provider: subclass `BaseAIProvider`, implement 3 methods, register in `backend/api/services/ai_providers/registry.py`
- API interactive docs: http://localhost:80/api/docs (when running)
