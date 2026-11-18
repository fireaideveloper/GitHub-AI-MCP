"""Read-only official SDK client using a configured local stdio process."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters


async def main():
    config = Path(sys.argv[1] if len(sys.argv) > 1 else "config/config.json").resolve()
    async with Client(StdioServerParameters(command=sys.executable,
                                            args=["-m", "github_ai_mcp", "--config", str(config), "serve"])) as client:
        tools = await client.list_tools()
        print("Tools:", len(tools.tools))
        result = await client.call_tool("github_mcp.health_check", {})
        print(json.dumps(result.structured_content, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
