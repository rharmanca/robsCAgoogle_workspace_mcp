# Connecting to Google Workspace MCP on Railway

This guide explains how to connect to the Railway-hosted Google Workspace MCP server with semantic caching.

## Server Information

| Property | Value |
|----------|-------|
| **Server URL** | `https://google-workspace-mcp-production-76d5.up.railway.app` |
| **MCP Endpoint** | `/mcp` |
| **Health Check** | `/health` |
| **Transport** | Streamable HTTP |
| **Version** | 1.6.2 |

## First-Time Setup: Google Authentication

Before connecting any client, you must authenticate with Google:

1. **Visit the auth endpoint** in your browser:
   ```
   https://google-workspace-mcp-production-76d5.up.railway.app/auth
   ```

2. Complete the Google OAuth flow to authorize access to your workspace account

3. Your credentials are stored on the Railway volume and persist across restarts

---

## Connection Methods

### Claude Desktop

Add to your `claude_desktop_config.json`:

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`  
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://google-workspace-mcp-production-76d5.up.railway.app/mcp"
      ]
    }
  }
}
```

**Prerequisites:**
- Node.js installed (for npx)
- `mcp-remote` will be auto-installed on first run

---

### Claude Code (CLI)

```bash
claude mcp add --transport http google-workspace https://google-workspace-mcp-production-76d5.up.railway.app/mcp
```

---

### VS Code MCP Extension

Add to your VS Code MCP settings:

```json
{
  "servers": {
    "google-workspace": {
      "url": "https://google-workspace-mcp-production-76d5.up.railway.app/mcp/",
      "type": "http"
    }
  }
}
```

---

### OpenCode / Other MCP Clients

For any MCP client that supports HTTP transport:

```
URL: https://google-workspace-mcp-production-76d5.up.railway.app/mcp
Transport: streamable-http
```

---

### Direct HTTP Requests (API Integration)

You can call tools directly via HTTP POST:

```bash
# List available tools
curl -X POST https://google-workspace-mcp-production-76d5.up.railway.app/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'

# Call a specific tool (example: list calendars)
curl -X POST https://google-workspace-mcp-production-76d5.up.railway.app/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "list_calendars",
      "arguments": {}
    },
    "id": 2
  }'
```

---

### Python Client

```python
import httpx
import json

MCP_URL = "https://google-workspace-mcp-production-76d5.up.railway.app/mcp"

def call_mcp_tool(tool_name: str, arguments: dict = None):
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {}
        },
        "id": 1
    }
    
    response = httpx.post(MCP_URL, json=payload)
    return response.json()

# Example: List calendars
result = call_mcp_tool("list_calendars")
print(json.dumps(result, indent=2))

# Example: Search Gmail
result = call_mcp_tool("search_gmail_messages", {
    "query": "is:unread",
    "max_results": 10
})
print(json.dumps(result, indent=2))
```

---

### JavaScript/TypeScript Client

```typescript
const MCP_URL = "https://google-workspace-mcp-production-76d5.up.railway.app/mcp";

async function callMcpTool(toolName: string, args: Record<string, any> = {}) {
  const response = await fetch(MCP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      method: "tools/call",
      params: { name: toolName, arguments: args },
      id: 1
    })
  });
  return response.json();
}

// Example usage
const calendars = await callMcpTool("list_calendars");
console.log(calendars);

const emails = await callMcpTool("search_gmail_messages", {
  query: "from:boss@company.com",
  max_results: 5
});
console.log(emails);
```

---

## Available Tools

This server includes tools for:

| Service | Examples |
|---------|----------|
| **Gmail** | `search_gmail_messages`, `send_gmail_message`, `get_gmail_message_content` |
| **Calendar** | `list_calendars`, `get_events`, `create_event`, `modify_event` |
| **Drive** | `search_drive_files`, `get_drive_file_content`, `create_drive_file` |
| **Docs** | `get_doc_content`, `create_doc`, `modify_doc_text` |
| **Sheets** | `read_sheet_values`, `modify_sheet_values`, `create_spreadsheet` |
| **Slides** | `create_presentation`, `get_presentation` |
| **Forms** | `create_form`, `get_form`, `list_form_responses` |
| **Tasks** | `list_tasks`, `create_task`, `update_task` |

To get a full list of available tools, call the `tools/list` method.

---

## Semantic Caching

This deployment includes semantic caching powered by:

- **Qdrant** - Vector database for semantic similarity matching
- **Redis** - Fast exact-match caching

Benefits:
- Faster responses for similar queries
- Reduced API calls to Google services
- Lower latency for repeated operations

---

## Health Check

Verify the server is running:

```bash
curl https://google-workspace-mcp-production-76d5.up.railway.app/health
```

Expected response:
```json
{"status":"healthy","service":"workspace-mcp","version":"1.6.2","transport":"streamable-http"}
```

---

## Troubleshooting

### "Unauthorized" or authentication errors
- Visit `/auth` endpoint in browser to re-authenticate
- Credentials may have expired; complete the OAuth flow again

### Connection refused
- Check server health at `/health` endpoint
- Verify Railway deployment is running

### Tool not found
- Call `tools/list` to see available tools
- Tool names are case-sensitive

### Slow first response
- Initial requests may be slower as semantic cache warms up
- Subsequent similar queries will be faster

---

## Environment Details

This Railway deployment is configured with:

- **Single-user mode**: Pre-configured for `rharman@collegiateacademies.org`
- **Legacy OAuth**: `OAUTH2_ENABLE_LEGACY_AUTH=true`
- **Persistent credentials**: Stored on Railway volume at `/data/store_creds`
