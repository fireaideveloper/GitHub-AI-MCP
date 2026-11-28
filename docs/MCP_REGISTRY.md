# MCP Registry publishing

This distribution is the local Python CLI, not the standalone Windows executable. It requires Python 3.12+, Git and an OS credential vault; private Git operations need gh. Initialize the local config with `uvx github-ai-mcp==1.0.2 init` before connecting a client using `uvx github-ai-mcp==1.0.2 serve`. Default access is READ_ONLY with an empty allowlist. Do not expose loopback HTTP or private tunnels.

Before publishing:
1. Confirm ownership/availability of the PyPI name github-ai-mcp. Configure a pending trusted publisher on PyPI for fireaideveloper/GitHub-AI-MCP, workflow mcp-registry.yml, environment pypi.
2. Configure protected GitHub environments pypi and mcp-registry with main-only deployments and reviewer approval where supported.
3. Review the official registry publisher release and verify its Linux amd64 archive SHA-256 independently. Set MCP_PUBLISHER_TAG and MCP_PUBLISHER_SHA256 in the mcp-registry environment. Check the actual release asset name.
4. Keep pyproject.toml and both version fields in server.json synchronized. Run the workflow without publishing and review both OS jobs before publishing.
5. On main, dispatch the workflow with publish=true. PyPI must succeed before MCP Registry publication. No PAT or tunnel credential is required by publishing.
6. If PyPI succeeded but the registry failed, do not overwrite the PyPI release; resolve the problem and use the official publisher CLI with GitHub authentication to publish the same server.json.

References: https://github.com/modelcontextprotocol/registry and https://docs.pypi.org/trusted-publishers/ .
