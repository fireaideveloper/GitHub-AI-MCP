# Version 1.0.1 update

For a complete first-time setup, follow the [English quickstart](QUICKSTART_EN.md) or [Russian quickstart](QUICKSTART_RU.md).

Use [current setup guide](USER_GUIDE_EN.md) for secure vault and profile repair. Historical manual examples below are optional and are not the normal startup workflow.

# Packaged stdio and source compatibility

The packaged command is the absolute `GitHub-AI-MCP.exe`, with internal server dispatch before GUI initialization. Example for a local client:

```json
{"mcpServers":{"github-ai-mcp":{"command":"C:/Users/USER/Downloads/Папка с пробелами/GitHub-AI-MCP/GitHub-AI-MCP.exe","args":["--internal-server","--config","C:/Users/USER/AppData/Local/GitHub-AI-MCP/config.json","serve"]}}}
```

Argument arrays preserve spaces/Unicode; JSON backslashes must be escaped or replaced with `/`. The Setup dialog also shows an editable absolute local stdio command; adapt it to your client's argument syntax. Use “Use current application command” and “Repair MCP command” to update the selected YAML after moving or rebuilding the EXE. Repair is local and does not require a key or network; runtime validation still runs before launch. Source mode still uses Python `-m github_ai_mcp`; the source stdio tests have actually run. Packaged Windows stdio has NOT RUN here; CI uses a raw initialization/list-tools/structured-health wire test and rejects non-JSON stdout. Logging stays on stderr or controller logs.

For your existing authorized vendor profile, configure its stdio command using its documented command syntax. The process command, in PowerShell notation, is:

```powershell
& 'C:\Users\USER\Downloads\Папка с пробелами\GitHub-AI-MCP\GitHub-AI-MCP.exe' --internal-server --config 'C:\Users\USER\AppData\Local\GitHub-AI-MCP\config.json' serve
```

The `&` is PowerShell syntax, not a literal tunnel executable argument. If the provider accepts argv, supply executable and arguments separately. If it accepts a command string, apply that provider's documented quoting rules; this project does not implement its parser or invent additional flags. Existing profile creation/authentication remains vendor-managed. GUI HTTP supervision launches the same executable with `--internal-server` with `serve --transport streamable-http`, CREATE_NO_WINDOW and preserved pipes. The source controller keeps Python module dispatch. The GUI can separately supervise an existing vendor process, but cannot certify its remote connection.

> Current desktop setup: use Setup to generate/reuse the MCP token and select the existing official tunnel client/profile. See [Windows instructions](USER_GUIDE_RU.md). Legacy manual CLI examples below remain optional.

# Connecting MCP clients and ChatGPT

Checked against official SDK and OpenAI documentation on 2026-10-09. Client interfaces and permissions can change; the references below are authoritative. A running server process is required. This application does not include an LLM or need an OpenAI API key for local Git/MCP work.

## Local stdio client (working, wire-tested)

Use your client's local MCP server configuration:

```json
{
  "mcpServers": {
    "github-ai-mcp": {
      "command": "C:/PATH/GitHub-AI-MCP/.venv/Scripts/python.exe",
      "args": ["-m", "github_ai_mcp", "--config", "C:/PATH/GitHub-AI-MCP/config/config.json", "serve"]
    }
  }
}
```

Replace PATH with the extracted project path. Python paths must be absolute; JSON backslashes must be escaped or replaced by forward slashes. This is a common stdio configuration shape, not a guarantee that every client uses the same settings file. Select stdio/local process in your client. Do not launch the Windows interactive menu as an MCP process: it prints prompts instead of protocol messages.

Claude Desktop and other clients with local stdio support can start this executable. Consult the client's current MCP setup instructions. Local process credentials are controlled by the OS user. `examples/mcp_client_example.py` is an actual official SDK v2 client; run it with the path to your configuration to list tools and call health_check.

## Local Streamable HTTP (working, authenticated)

1. Run `github-ai-mcp auth-mcp` locally, or use Setup to generate/copy the local MCP token; securely copy the generated token into your client's secret store. This is not the GitHub PAT.
2. Run `github-ai-mcp serve --transport streamable-http` or GUI Start MCP.
3. Configure the client's Streamable HTTP URL as `http://127.0.0.1:8766/mcp` and its Authorization header as `Bearer <MCP token>`.
4. Call `github_mcp.health_check` and `github_mcp.list_repositories` before writes. Missing bearer token returns 401. A GET without proper MCP headers is not a health check.

The server is loopback-only with Host/Origin checks. A client that cannot supply Authorization headers should use stdio. It is not an OAuth discovery server. Don't tunnel this HTTP endpoint publicly as a substitute for OAuth.

## ChatGPT through the official private Secure MCP Tunnel

A ChatGPT cloud connection cannot ordinarily reach a Windows localhost URL directly. Current official OpenAI documentation provides an outbound-only Secure MCP Tunnel for supported products. This source supervises an existing official client/profile and stores its runtime key in an approved OS vault. The source checkout does not contain the vendor client; the Windows build embeds the developer-supplied official client. The application does not create cloud tunnels. Live ChatGPT integration has not been tested here.

Prerequisites: access to Platform tunnel settings, the appropriate Tunnels Read/Manage/Use roles, a tunnel associated with your target ChatGPT workspace, and permission to add custom MCP servers. Your subscription alone is not a guarantee of these permissions. A tunnel-client runtime API key is separate from both application credentials.

1. Create/manage the tunnel in [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels), following current documentation.
2. Download `tunnel-client` from the link in settings or the official [openai/tunnel-client](https://github.com/openai/tunnel-client) release. Verify its publisher and run `tunnel-client help quickstart`.
3. Configure the private **stdio** command to start the packaged executable above, or (developers) this app's Python module with its full `--config` path. The official guide's stdio flow uses:

```powershell
tunnel-client init --sample sample_mcp_stdio_local --profile github-ai-local --tunnel-id YOUR_TUNNEL_ID --mcp-command "C:/PATH/GitHub-AI-MCP/.venv/Scripts/python.exe -m github_ai_mcp --config C:/PATH/GitHub-AI-MCP/config/config.json serve"
tunnel-client doctor --profile github-ai-local --explain
tunnel-client run --profile github-ai-local
```

For paths containing spaces, follow tunnel-client's current command quoting rules. Configure the runtime control-plane API key using its official secure setup; never put a real key in this repository, the JSON config, screenshots or a shared transcript. Version 1.0.1 manages that runtime key through Setup and the OS vault; use the current user guide.

4. In ChatGPT Plugins, choose plus → Add custom MCP server → Connection: Tunnel, select the associated tunnel or provide its tunnel ID. Configure authentication as supported by the actual product/tunnel, review the risk warning and create the plugin. UI labels/availability depend on the account and workspace.
5. Keep tunnel-client running; start with this app in READ_ONLY. Confirm health_check and allowlisted reads.
6. Keep local commit/push approvals in the GUI/CLI. A ChatGPT confirmation does not automatically grant the app's local policy.

The tunnel controls access through organization/workspace permissions; the stdio subprocess runs within your trusted host boundary. This is distinct from deploying a public HTTP server. Do not claim OAuth is implemented in this application. If the tunnel option is unavailable, use a local stdio client rather than an unauthenticated public tunnel.

Official sources:
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- https://py.sdk.modelcontextprotocol.io/
