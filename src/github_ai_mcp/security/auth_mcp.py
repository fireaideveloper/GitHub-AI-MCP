import hmac
import time
from collections import deque

from starlette.responses import JSONResponse


class LocalAuth:
    def __init__(self, app, token: str, port: int):
        self.app, self.token, self.port = app, token, port
        self.requests: deque[float] = deque()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"").decode()
        origin = headers.get(b"origin", b"").decode()
        allowed = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        if host not in allowed or (origin and origin not in {"http://" + h for h in allowed}):
            return await JSONResponse({"error": "INVALID_ORIGIN"}, 403)(scope, receive, send)
        supplied = headers.get(b"authorization", b"").decode()
        if not hmac.compare_digest(supplied, "Bearer " + self.token):
            return await JSONResponse({"error": "AUTH_REQUIRED"}, 401)(scope, receive, send)
        now = time.monotonic()
        while self.requests and self.requests[0] < now - 60:
            self.requests.popleft()
        if len(self.requests) >= 120:
            return await JSONResponse({"error": "RATE_LIMITED"}, 429)(scope, receive, send)
        self.requests.append(now)
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = 10_000_000
        if length > 2_000_000:
            return await JSONResponse({"error": "PAYLOAD_TOO_LARGE"}, 413)(scope, receive, send)
        return await self.app(scope, receive, send)
