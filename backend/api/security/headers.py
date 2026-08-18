"""Security response-header middleware.

Adds the standard hardening headers to every response:

  - Content-Security-Policy   (configurable; a strict API default)
  - Strict-Transport-Security (HSTS — only over HTTPS / in production)
  - X-Frame-Options: DENY     (clickjacking)
  - X-Content-Type-Options: nosniff
  - Referrer-Policy, Permissions-Policy, X-Permitted-Cross-Domain-Policies
  - Cross-Origin-Opener-Policy / -Resource-Policy

The interactive docs routes (Swagger UI / ReDoc) need to load their assets and
run inline scripts, so the restrictive CSP is skipped for those paths only —
everywhere else the strict policy applies. Docs are disabled in production
anyway.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.config import settings

# Paths that render HTML needing a relaxed CSP (Swagger UI / ReDoc assets).
_DOCS_PREFIXES = ("/api/docs", "/api/redoc", "/api/openapi.json")

# A permissive CSP just for the docs UI (jsdelivr CDN + inline styles/scripts
# that Swagger UI/ReDoc require). Not used for API/data responses.
_DOCS_CSP = (
    "default-src 'self'; img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:; frame-ancestors 'none'"
)

# CSP for the bundled single-page app when FastAPI serves it (see main.py's SPA
# mount). The strict API default (`default-src 'none'`) blocks the app's own
# JS/CSS/fonts, so app (non-/api, non-docs) responses get this SPA-appropriate
# policy instead. Same-origin scripts, inline styles (Tailwind/React), Google
# Fonts, data:/https: images, and same-origin fetch/SSE.
_SPA_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        self._apply(request, response)
        return response

    @staticmethod
    def _apply(request: Request, response: Response) -> None:
        headers = response.headers
        path = request.url.path
        is_docs = path.startswith(_DOCS_PREFIXES)
        is_api = path.startswith("/api")

        if is_docs:
            _csp = _DOCS_CSP
        elif is_api:
            _csp = settings.content_security_policy  # strict API default
        else:
            _csp = _SPA_CSP  # bundled SPA served by FastAPI
        headers.setdefault("Content-Security-Policy", _csp)
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-site")

        # HSTS: only meaningful over TLS. Emit in production, or whenever the
        # request itself arrived over HTTPS (covers TLS-terminating proxies via
        # X-Forwarded-Proto).
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        is_https = request.url.scheme == "https" or forwarded_proto == "https"
        if settings.is_production or is_https:
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age}; includeSubDomains; preload",
            )
