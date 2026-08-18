# Translation Studio — production image (single origin: FastAPI serves the built
# SPA + the /api backend). Includes LibreOffice for DOCX/PPTX finalize + PDF
# export on Linux, and tesseract + Arabic fonts.

# ---------- Stage 1: build the React SPA ----------
# Pin to bookworm: the bare `-slim` tag floats to the newest Debian, whose apt
# package names drift and break the runtime install below. Node 22: the pinned
# pnpm (11.x) imports a builtin module that doesn't exist in Node 20
# (ERR_UNKNOWN_BUILTIN_MODULE), so it needs the Node 22 runtime.
FROM node:22-bookworm-slim AS frontend
RUN corepack enable
WORKDIR /app
COPY . .
# esbuild's build script is approved via pnpm-workspace.yaml (allowBuilds).
RUN pnpm install --frozen-lockfile || pnpm install
RUN cd artifacts/xray-academy && node node_modules/vite/bin/vite.js build

# ---------- Stage 2: Python runtime ----------
# Pin to bookworm (Debian 12): libreoffice-*, tesseract-ocr-*, fonts-noto-core
# and fonts-amiri all exist under these exact names here. The floating `-slim`
# tag pointed at trixie, where the apt install failed (exit 100).
FROM python:3.11-slim-bookworm AS runtime

# LibreOffice (Writer/Impress/Calc) = the Linux document-finalize + PDF engine.
# tesseract + language packs = OCR for scanned PDFs. fonts-noto-core provides
# Noto Arabic (Sans/Naskh), which covers Arabic shaping; LibreOffice substitutes
# it for any requested Arabic font. (fonts-amiri isn't packaged on bookworm.)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-writer libreoffice-impress libreoffice-calc \
      tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng \
      tesseract-ocr-fra tesseract-ocr-spa tesseract-ocr-rus \
      fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Install Python deps first (better layer caching).
COPY backend/requirements-translation.txt backend/requirements-translation.txt
RUN pip install --no-cache-dir -r backend/requirements-translation.txt

# App code + the SPA build from stage 1.
COPY backend ./backend
COPY --from=frontend /app/artifacts/xray-academy/dist ./artifacts/xray-academy/dist

WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
# Config comes from the host's environment variables (Render/Fly dashboard),
# not a committed .env. main.py's load_dotenv is a no-op when no .env exists.
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
