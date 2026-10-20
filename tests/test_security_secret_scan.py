import pytest

from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.secret_scan import has_secret, redact, scan


@pytest.mark.parametrize(
    "payload",
    [
        b"ghp_" + b"a" * 30,
        b"github_pat_" + b"A" * 40,
        b"Bearer " + b"abc123" * 5,
        b"AKIA" + b"A" * 16,
        b"password=" + b"longsecretvalue123",
        b"-----BEGIN " + b"RSA PRIVATE KEY-----",
    ],
)
def test_sensitive_patterns_are_detected(payload: bytes):
    assert has_secret(payload)
    with pytest.raises(AppError) as error:
        scan(payload)
    assert error.value.code == "SECRET_DETECTED"


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"print('hello')",
        b"token = os.environ.get('ACCESS_TOKEN')",
        b"password = 'redacted'",
        b"api_key = None",
    ],
)
def test_ordinary_code_passes_detection(payload: bytes):
    assert not has_secret(payload)
    scan(payload)


def test_redaction_preserves_safe_surrounding_text():
    fake_token = "ghp_" + "a" * 30
    original = "prefix " + fake_token + " suffix"
    result = redact(original)
    assert fake_token not in result
    assert result == "prefix [REDACTED] suffix"


def test_redaction_handles_non_ascii_text():
    token = "Bearer " + "B" * 24
    result = redact("До " + token + " после")
    assert result == "До [REDACTED] после"
