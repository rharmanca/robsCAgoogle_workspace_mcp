# Railway Deployment Guide

This guide walks you through deploying the Google Workspace MCP server to Railway, including the Gmail Indexing & Semantic Search capability.

---

## Quick Start

1. Connect your GitHub repository to Railway
2. Set required environment variables
3. Deploy - Railway will auto-build from the Dockerfile
4. Connect Claude Code to your Railway endpoint

---

## Prerequisites

- **Railway account** - [railway.app](https://railway.app)
- **GitHub repository** - Contains this MCP server code
- **Google OAuth credentials** - Client ID and Secret from Google Cloud Console
- **Synthetic API key** - For email embeddings (gmail_index feature) - https://synthetic.new

---

## Step 1: Connect Repository to Railway

1. Go to [railway.app](https://railway.app) and sign in
2. Click **New Project** → **Deploy from GitHub repo**
3. Select or create a GitHub repository with this code
4. Choose the `production` branch
5. Railway will auto-detect the Dockerfile and build settings

---

## Step 2: Configure Environment Variables

After connecting your repo, add the following environment variables:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth client ID | `995112842480-4stp5...` |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth client secret | `GOCSPX-Sbkd23prJAlZggBUqSiK34...` |
| `USER_GOOGLE_EMAIL` | Default email for single-user mode | `user@example.com` |

### Email Indexing Variables (Optional - for gmail_index tools)

| Variable | Description | Example |
|----------|-------------|---------|
| `SYNTHETIC_API_KEY` | API key for vector embeddings | `syn_abc123def456...` |
| `EMAIL_INDEX_DATA_DIR` | Directory for SQLite + ChromaDB data | `/data/store_creds/email_index` |

### OAuth Configuration Variables (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_OAUTH_REDIRECT_URI` | OAuth callback URL | Auto-constructed |
| `WORKSPACE_MCP_BASE_URI` | Base server URI | Auto-detected |
| `MCP_SINGLE_USER_MODE` | Enable single-user mode | `true` |
| `OAUTH_LEGACY_AUTH` | Use legacy authentication | `true` |

### Database Variables (Auto-set by Railway)

Railway automatically sets these for linked services:
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `QDRANT_HOST`, `QDRANT_PORT`
- `RAILWAY_VOLUME_MOUNT_PATH`

---

## Step 3: Configure Persistent Storage

Railway limits services to **one volume each**. The MCP server uses the volume for:
- OAuth token storage (`/data/store_creds/`)
- Email index data (`/data/store_creds/email_index/`)

To enable the volume:

1. Go to your service in Railway dashboard
2. Click **Settings** → **Volumes**
3. Add a volume with mount path: `/data/store_creds`
4. Volume size: 5GB (expandable up to 50GB free tier)

**⚠️ Important**: Railway only allows one volume per service. The email index data will be stored at `/data/store_creds/email_index/` as a subdirectory.

---

## Step 4: Deployment

Once configured, Railway will automatically build and deploy:

1. **Build**: Uses the Dockerfile (Python 3.12 + uv)
2. **Health Check**: Endpoint `/health` serves as health check
3. **Auto-Deploy**: Connected GitHub (production branch) triggers rebuilds on push

Expected deployment time: 2-3 minutes

**Health Check URL**: Replace `YOUR-PROJECT` with your Railway project name
```
https://google-workspace-mcp-production-YOUR-PROJECT.up.railway.app/health
```

---

## Step 5: Connect Claude Code

Once deployed, add the Railway MCP server to Claude Code:

### Option A: Manual Configuration

Edit `~/.claude/settings.local.json` (or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ca-railway-google-workspace": {
      "type": "http",
      "url": "https://your-project-name.up.railway.app/mcp",
      "disabled": false
    }
  }
}
```

### Option B: Claude Code CLI

```bash
claude mcp add --transport http railway-google-workspace https://your-project-name.up.railway.app/mcp
```

### Option C: Claude Desktop Configuration

```json
{
  "mcpServers": {
    "google-workspace-railway": {
      "type": "http",
      "url": "https://your-project-name.up.railway.app/mcp"
    }
  }
}
```

**Important**: Restart Claude Code/Desktop after adding the MCP server.

---

## Available Tools After Connection

Once connected, you'll have access to all Google Workspace tools:

### Core Tools
- **Gmail**: `search_gmail_messages`, `send_gmail_message`, `get_gmail_message_content`, etc.
- **Drive**: `search_drive_files`, `get_drive_file_content`, `create_drive_file`, etc.
- **Calendar**: `list_calendars`, `get_events`, `create_event`, etc.
- **Docs**: `get_doc_content`, `create_doc`, `modify_doc_text`, etc.
- **Sheets**: `read_sheet_values`, `modify_sheet_values`, `create_spreadsheet`, etc.

### Gmail Indexing Tools (if SYNTHETIC_API_KEY is set)

| Tool | Description |
|------|-------------|
| `index_gmail_inbox` | Bulk index emails with embeddings |
| `sync_gmail_index` | Incremental updates using Gmail History API |
| `search_gmail_fts` | Fast keyword search (SQLite FTS5) |
| `search_gmail_semantic` | Semantic search (ChromaDB + embeddings) |
| `search_gmail_hybrid` | Combined search with RRF ranking |
| `get_gmail_index_stats` | Index status and statistics |

---

## First-Time Authentication

1. Call any Google Workspace tool from Claude
2. The Railway server will return an authorization URL
3. Open the URL in your browser
4. Authorize the application
5. Railway stores the token in the persistent volume

The token persists across redeployments (stored in `/data/store_creds/`).

---

## Using Gmail Indexing

**Initial Index**:
```
index_gmail_inbox(
  user_google_email="your.email@domain.com",
  max_messages=5000
)
```

**Incremental Sync** (run periodically to get new emails):
```
sync_gmail_index(user_google_email="your.email@domain.com")
```

**Keyword Search**:
```
search_gmail_fts(
  query="budget planning",
  user_google_email="your.email@domain.com"
)
```

**Semantic Search**:
```
search_gmail_semantic(
  query="documents about financial planning",
  user_google_email="your.email@domain.com"
)
```

**Hybrid Search** (recommended - combines both):
```
search_gmail_hybrid(
  query="transportation scheduling",
  user_google_email="your.email@domain.com"
)
```

---

## Troubleshooting

### Server Not Responding

Check the health endpoint:
```bash
curl https://your-project-name.up.railway.app/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "workspace-mcp",
  "version": "1.6.2",
  "transport": "streamable-http"
}
```

### MCP Tools Not Available

1. Verify Railway MCP server URL is correct
2. Check `disabled: false` in settings
3. Restart Claude Code/Desktop
4. Check Railway logs for errors

### Email Indexing Errors

**Check index stats**:
```
get_gmail_index_stats(user_google_email="your.email@domain.com")
```

**Common issues**:
- Ensure `SYNTHETIC_API_KEY` is set and valid
- Check volume mount path is `/data/store_creds`
- Verify `EMAIL_INDEX_DATA_DIR` is `/data/store_creds/email_index`
- If embeddings fail, your Synthetic API key may be invalid

### OAuth Fails

1. Verify OAuth credentials are correct
2. Check Google Cloud Console allows the domain/redirect URI
3. Ensure volume is mounted for token persistence

---

## Railway CLI Reference

Using the Railway CLI can be helpful for managing your deployment:

```bash
# Login
railway login

# Link to project
railway link

# Deploy latest code
railway up --detach

# View variables
railway variables

# Set a variable
railway variables --set "KEY=value"

# View logs
railway logs

# Check status
railway status
```

---

## Storage Management

| Storage Type | Location | Purpose |
|--------------|----------|---------|
| OAuth Tokens | `/data/store_creds/*.json` | User authentication tokens |
| SQLite DB | `/data/store_creds/email_index/email_index.db` | Email index + FTS5 |
| ChromaDB | `/data/store_creds/email_index/chroma/` | Vector embeddings |

The volume storage is **persistent** - data survives redeployments.

---

## Cost Estimation

### Railway Pricing (as of 2025)

| Service | Cost | Included Free Tier |
|---------|------|-------------------|
| Standard Service | $0.000067/second | $5/month credit |
| Volume Storage | $0.09/GB | 5GB included |
| Bandwidth | Free (up to limit) | 1GB outbound included |

**Example**: A lightly used MCP server (~200MB storage, occasional tool calls) costs **well under $5/month** with the free tier credits.

---

## Security Notes

- **Never commit secrets** to GitHub - use Railway environment variables
- OAuth tokens are stored in the persistent volume
- Railway provides HTTPS automatically
- Consider enabling Railway's domain protection

---

## Advanced Configuration

### Selective Tool Loading

You can configure which services to load by setting environment variable:

```bash
TOOLS="gmail,drive,calendar"  # Load only these services
```

Or set `TOOL_TIER`:
```bash
TOOL_TIER=core      # Essential tools only
TOOL_TIER=extended  # Core + extras
TOOL_TIER=complete  # All tools
```

### OAuth 2.1 Multi-User Mode

For production environments with multiple users:

```bash
MCP_ENABLE_OAUTH21=true
MCP_SINGLE_USER_MODE=false
```

---

## Support

- **Railway Docs**: https://docs.railway.app
- **MCP Protocol**: https://modelcontextprotocol.io
- **This Project**: https://github.com/taylorwilsdon/google_workspace_mcp/issues

---

## Summary Checklist

- [ ] GitHub repository connected to Railway
- [ ] `GOOGLE_OAUTH_CLIENT_ID` + `SECRET` set
- [ ] `USER_GOOGLE_EMAIL` configured
- [ ] `SYNTHETIC_API_KEY` set (for email indexing)
- [ ] `EMAIL_INDEX_DATA_DIR` set to `/data/store_creds/email_index`
- [ ] Volume mounted at `/data/store_creds`
- [ ] Deployment successful (health check passing)
- [ ] Claude Code/Desktop connected to Railway MCP URL
- [ ] First-time authentication completed
- [ ] Email indexing tested (optional)
