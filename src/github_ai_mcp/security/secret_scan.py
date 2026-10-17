import re

from github_ai_mcp.exceptions import AppError

PATTERNS = [rb"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", rb"gh[pousr]_[A-Za-z0-9]{20,}", rb"github_pat_[A-Za-z0-9_]{20,}",
            rb"AKIA[0-9A-Z]{16}", rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            rb"(?i)(?:password|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[^\s'\"]{12,}"]


def has_secret(content: bytes) -> bool:
    return any(re.search(p, content) for p in PATTERNS)


def scan(content: bytes) -> None:
    if has_secret(content):
        raise AppError("SECRET_DETECTED", "Credential indicator detected; content withheld")


def redact(content: str) -> str:
    raw = content.encode("utf-8", "replace")
    for pattern in PATTERNS:
        raw = re.sub(pattern, b"[REDACTED]", raw)
    return raw.decode("utf-8", "replace")
