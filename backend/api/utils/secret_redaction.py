"""Best-effort secret redaction for text that will be sent to the AI model.

Applied by the text/code workspace processors before extracted content is
ever assembled into a Gemini prompt. This is defense-in-depth, not a
cryptographic guarantee — it catches common key/token/password shapes and
whole files that are obviously credential stores (.env, credentials.json,
*.pem, id_rsa, ...), and replaces the sensitive value with ``[REDACTED]``.
"""
from __future__ import annotations

import re

# Filenames that are almost always credential stores — their content is
# fully redacted rather than scanned line-by-line.
_SENSITIVE_FILENAME_PATTERNS = [
    re.compile(r"^\.env(\..+)?$", re.IGNORECASE),
    re.compile(r"credentials?\.(json|ya?ml|txt)$", re.IGNORECASE),
    re.compile(r"secrets?\.(json|ya?ml|txt)$", re.IGNORECASE),
    re.compile(r"^id_rsa$|^id_ed25519$|^id_ecdsa$", re.IGNORECASE),
    re.compile(r"\.pem$|\.pfx$|\.p12$|\.key$", re.IGNORECASE),
    re.compile(r"^\.npmrc$|^\.pypirc$|^\.netrc$", re.IGNORECASE),
]

# Common secret-shaped values: KEY=value / "key": "value" style assignments
# for names containing key/token/secret/password/credential, plus a handful
# of well-known provider key prefixes that are unambiguous even without a
# nearby variable name.
_ASSIGNMENT_RE = re.compile(
    r"""(?P<prefix>
        (?:^|[\s,{])
        ["']?(?:[A-Za-z0-9_.\-]*(?:api[_-]?key|secret|token|password|passwd|credential|access[_-]?key|private[_-]?key)[A-Za-z0-9_.\-]*)["']?
        \s*[:=]\s*
        ["']?
    )
    (?P<value>[A-Za-z0-9/+_\-.=]{6,})
    (?P<suffix>["']?)
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)

_KNOWN_PREFIX_RE = re.compile(
    r"\b(sk-[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{12,}|ghp_[A-Za-z0-9]{20,}|"
    r"AIza[0-9A-Za-z\-_]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,})\b"
)


def is_sensitive_filename(filename: str) -> bool:
    return any(p.search(filename) for p in _SENSITIVE_FILENAME_PATTERNS)


def redact_secrets(text: str, *, filename: str = "") -> tuple[str, bool]:
    """Return (redacted_text, was_redacted).

    If ``filename`` matches a known credential-store pattern, the entire
    content is replaced. Otherwise, secret-shaped assignments and known key
    prefixes are replaced value-by-value so the surrounding structure/text
    stays useful to the model.
    """
    if filename and is_sensitive_filename(filename):
        return (
            f"[REDACTED: {filename} appears to be a credential/secret file — "
            "its contents were withheld from the AI model]",
            True,
        )

    if not text:
        return text, False

    redacted = False

    def _sub_assignment(m: re.Match) -> str:
        nonlocal redacted
        redacted = True
        return f"{m.group('prefix')}[REDACTED]{m.group('suffix')}"

    out = _ASSIGNMENT_RE.sub(_sub_assignment, text)

    def _sub_prefix(m: re.Match) -> str:
        nonlocal redacted
        redacted = True
        return "[REDACTED]"

    out = _KNOWN_PREFIX_RE.sub(_sub_prefix, out)

    return out, redacted
