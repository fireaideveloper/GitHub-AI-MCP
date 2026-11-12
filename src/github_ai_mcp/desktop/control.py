"""Local lifecycle routes protected by bearer auth and a private per-instance nonce."""
import hmac
import hashlib
import os

from starlette.responses import JSONResponse


class ControlRoutes:
    def __init__(self, app, instance, runner):
        self.app, self.instance, self.runner = app, instance, runner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/_local/health":
            return await JSONResponse({"application": "GitHub-AI-MCP", "pid": os.getpid(),
                                       "instance": hashlib.sha256(self.instance.encode()).hexdigest()})(scope, receive, send)
        if scope["type"] == "http" and scope["path"] == "/_local/shutdown":
            headers = dict(scope.get("headers", []))
            valid = self.instance and hmac.compare_digest(
                headers.get(b"x-local-control", b"").decode(), self.instance)
            if scope["method"] != "POST" or not valid:
                return await JSONResponse({"error": "FORBIDDEN"}, 403)(scope, receive, send)
            await JSONResponse({"stopping": True})(scope, receive, send)
            self.runner.should_exit = True
            return
        return await self.app(scope, receive, send)
