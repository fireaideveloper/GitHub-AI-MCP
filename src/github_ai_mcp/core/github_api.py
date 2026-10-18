import time
from urllib.parse import quote

import httpx

from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.auth_github import get_token


class GitHub:
    def __init__(self, token: str | None = None, transport=None):
        self._token = token
        self.transport = transport

    def request(self, method: str, path: str, data=None):
        if not path.startswith("/") or ".." in path or "?" in path or ":" in path:
            raise AppError("UNSAFE_URL", "Invalid GitHub API path")
        token = self._token or get_token()
        with httpx.Client(base_url="https://api.github.com", follow_redirects=False,
                          transport=self.transport, timeout=20,
                          headers={"Authorization": "Bearer " + token,
                                   "Accept": "application/vnd.github+json",
                                   "X-GitHub-Api-Version": "2022-11-28"}) as client:
            for attempt in range(3):
                try:
                    r = client.request(method, path, json=data)
                except httpx.HTTPError:
                    raise AppError("RETRYABLE_ERROR", "GitHub network request failed; inspect remote before retrying writes") from None
                if r.status_code in {429, 502, 503, 504} or (
                    r.status_code == 403 and ("retry-after" in r.headers or r.headers.get("x-ratelimit-remaining") == "0")
                ):
                    if method != "GET" or attempt == 2:
                        raise AppError("RATE_LIMITED", "GitHub rate limit; retry later")
                    try:
                        delay = min(5.0, max(0.1, float(r.headers.get("retry-after", 1))))
                    except ValueError:
                        delay = 1.0
                    time.sleep(delay)
                    continue
                if r.status_code == 401:
                    raise AppError("AUTH_REQUIRED", "GitHub credential expired or invalid")

                if (r.status_code == 403 and method == "GET"
                        and path.startswith("/repos/") and "/rules/branches/" in path):
                    try:
                        error_message = r.json().get("message", "")
                    except (ValueError, AttributeError):
                        error_message = ""
                    if error_message == (
                        "Upgrade to GitHub Pro or make this repository public to enable this feature."
                    ):
                        raise AppError("RULESETS_UNAVAILABLE", "GitHub plan does not provide branch rulesets")
                if r.status_code in {403, 404}:
                    raise AppError("PERMISSION_DENIED", "GitHub resource unavailable or permission denied")
                if r.is_error:
                    raise AppError("GITHUB_ERROR", f"GitHub rejected request ({r.status_code})")
                if len(r.content) > 2_000_000:
                    raise AppError("LIMIT_EXCEEDED", "GitHub response too large")
                return r.json() if r.content else {}
        raise AppError("RETRYABLE_ERROR", "GitHub retries exhausted")

    def identity(self, email: str):
        user = self.request("GET", "/user")
        status = "unverified"
        try:
            emails = self.request("GET", "/user/emails")
            status = "verified" if any(e["email"].casefold() == email.casefold() and e["verified"]
                                         for e in emails) else "unverified"
        except AppError:
            status = "unknown"
        return {"actor": user["login"], "email_association": status}

    def info(self, repository: str):
        meta = self.request("GET", "/repos/" + repository)
        branch = quote(meta["default_branch"], safe="")
        result = {k: meta.get(k) for k in ["full_name", "default_branch", "fork", "private", "permissions", "html_url"]}
        for key, endpoint in [("rules", f"/repos/{repository}/rules/branches/{branch}"),
                              ("protection", f"/repos/{repository}/branches/{branch}/protection")]:
            try:
                result[key] = self.request("GET", endpoint)
            except AppError:
                result[key] = "unknown"
        return result
