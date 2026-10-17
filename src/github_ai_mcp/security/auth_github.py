import keyring

from github_ai_mcp.exceptions import AppError

SERVICE = "GitHub-AI-MCP"


def vault():
    try:
        backend = keyring.get_keyring()
        candidates = getattr(backend, "backends", [backend])
        allowed = ("keyring.backends.Windows", "keyring.backends.macOS", "keyring.backends.SecretService",
                   "keyring.backends.kwallet", "keyring.backends.libsecret")
        for candidate in candidates:
            if type(candidate).__module__.startswith(allowed) and candidate.priority > 0:
                return candidate
    except Exception:
        pass
    raise AppError("AUTH_REQUIRED", "OS credential vault unavailable; use Windows Credential Manager")


def get_secret(name: str) -> str:
    try:
        token = vault().get_password(SERVICE, name)
    except AppError:
        raise
    except Exception:
        raise AppError("AUTH_REQUIRED", "OS credential vault access failed") from None
    if not token:
        raise AppError("AUTH_REQUIRED", "Credential not configured in the local OS vault")
    return token


def get_token() -> str:
    return get_secret("github")


def store_secret(name: str, token: str) -> None:
    try:
        vault().set_password(SERVICE, name, token)
    except AppError:
        raise
    except Exception:
        raise AppError("AUTH_REQUIRED", "OS credential vault write failed") from None


def store_token(token: str) -> None:
    store_secret("github", token)


def logout() -> None:
    try:
        vault().delete_password(SERVICE, "github")
    except AppError:
        raise
    except Exception:
        raise AppError("AUTH_REQUIRED", "No stored GitHub credential to delete") from None


def remove_secret(name: str) -> None:
    try:
        vault().delete_password(SERVICE, name)
    except AppError:
        raise
    except Exception:
        raise AppError("AUTH_REQUIRED", "Credential removal failed / Не удалось удалить ключ") from None
