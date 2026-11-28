# GitHub-AI-MCP

Local GitHub MCP server with explicit review and repository policies.

Requires Python 3.12+, Git, and an OS credential vault. GitHub CLI is needed for private Git operations. Install the optional GUI extra only for desktop use.

Initialize locally using `github-ai-mcp init`, configure the repository allowlist, and start with `github-ai-mcp serve` (stdio). Default configuration is READ_ONLY with no repositories or grants. Use `github-ai-mcp login` locally for authentication; never put tokens in MCP configuration.

See the [setup guide](https://github.com/fireaideveloper/GitHub-AI-MCP/blob/main/docs/MCP_CONNECTION.md) and [security model](https://github.com/fireaideveloper/GitHub-AI-MCP/blob/main/docs/SECURITY_MODEL.md).

<!-- mcp-name: io.github.fireaideveloper/github-ai-mcp -->
