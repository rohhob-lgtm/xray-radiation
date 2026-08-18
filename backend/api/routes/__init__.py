"""Register route modules under the shared router.

TRANSLATION STUDIO CLONE — only the routers the translation feature needs are
registered here. The main platform's other routers (chat, rag, research,
education, study, gallery, training, connectors, orchestrator, research_agent,
knowledge_*, book, capabilities, …) still exist in this package but are
intentionally NOT wired, to keep the API surface and startup cost minimal.

Kept:
  • health          — liveness/readiness
  • auth            — session auth (require_auth); bypassed when DISABLE_AUTH=true
  • providers       — AI provider list/status (sidebar indicator)
  • img_translation — in-image (diagram/label) translation
  • translation     — core pipeline, projects, dictionary, memory, settings,
                      cost (/translation/cost/*), admin usage, export
"""
from fastapi import APIRouter

from .health import router as health_router
from .auth import router as auth_router
from .providers import router as providers_router
from .img_translation import router as img_translation_router
from .translation import router as translation_router
from .chat_tutor import router as chat_tutor_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(providers_router)
router.include_router(chat_tutor_router)
# img_translation must register before translation: its specific /export/zip and
# /export/quality-report routes must win over translation's parameterised
# /export/{fmt}.
router.include_router(img_translation_router)
router.include_router(translation_router)
