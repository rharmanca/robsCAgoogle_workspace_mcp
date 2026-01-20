# Google Workspace MCP - Fork

**Repository:** cvrt-gmbh/workspace-mcp  
**Upstream:** taylorwilsdon/google_workspace_mcp  
**Purpose:** Fix multi-account credential isolation bug  
**Last Updated:** 2026-01-20

---

## Overview

This is a fork of the `workspace-mcp` package to fix a critical bug where the `WORKSPACE_MCP_CREDENTIALS_DIR` environment variable is ignored, making it impossible to run multiple instances with different Google accounts.

## The Problem

When running two MCP server instances (e.g., one for `jh@cavort.de` and one for `info@cavort.de`):

1. **OAuth callback ignores `WORKSPACE_MCP_CREDENTIALS_DIR`** - Credentials always save to the default `~/.google_workspace_mcp/credentials/` directory
2. **Credential loading ignores the env var too** - Both instances read from the same default directory
3. **Result:** Both instances use the same account, regardless of configuration

## The Fix Required

Ensure `WORKSPACE_MCP_CREDENTIALS_DIR` is respected in:
1. OAuth callback handler (where credentials are saved after authentication)
2. Credential loading logic (where credentials are read at startup)
3. Any other file operations related to credentials

## Project Structure

```
workspace-mcp/
├── src/
│   └── workspace_mcp/
│       ├── __init__.py
│       ├── server.py          # Main MCP server
│       ├── auth.py            # OAuth handling (likely needs fixes)
│       ├── credentials.py     # Credential management (likely needs fixes)
│       └── ...
├── pyproject.toml
├── AGENTS.md                   # This file
├── CLAUDE.md                   # Identical to AGENTS.md
└── PROGRESS.md                 # Task tracking
```

## Development Setup

```bash
# Create virtual environment
cd ~/Git/cvrt-gmbh/mcp/workspace-mcp
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Run locally for testing
python -m workspace_mcp --single-user
```

## Testing the Fix

### Test Configuration

Two MCP instances configured in `~/.config/opencode/opencode.json`:

```json
"google": {
  "command": ["python", "-m", "workspace_mcp", "--single-user"],
  "environment": {
    "WORKSPACE_MCP_CREDENTIALS_DIR": "~/.google_workspace_mcp/credentials-jh"
  }
},
"google-work": {
  "command": ["python", "-m", "workspace_mcp", "--single-user"],
  "environment": {
    "WORKSPACE_MCP_CREDENTIALS_DIR": "~/.google_workspace_mcp/credentials-info"
  }
}
```

### Test Steps

1. Clear all credentials:
   ```bash
   rm -rf ~/.google_workspace_mcp/credentials*
   mkdir -p ~/.google_workspace_mcp/credentials-jh
   mkdir -p ~/.google_workspace_mcp/credentials-info
   ```

2. Start first instance, authenticate with `jh@cavort.de`
3. Verify credential saved to `credentials-jh/jh@cavort.de.json`
4. Start second instance, authenticate with `info@cavort.de`
5. Verify credential saved to `credentials-info/info@cavort.de.json`
6. Verify each instance only reads its own credentials

### Success Criteria

- [ ] `credentials-jh/` contains ONLY `jh@cavort.de.json`
- [ ] `credentials-info/` contains ONLY `info@cavort.de.json`
- [ ] Default `credentials/` directory is NOT used when env var is set
- [ ] Each MCP instance returns data from the correct account
- [ ] Gmail search on `google` returns jh@ emails
- [ ] Gmail search on `google-work` returns info@ emails

## Git Workflow

```bash
# Keep upstream in sync
git fetch upstream
git merge upstream/main

# Push fixes to our fork
git push origin main

# Create PR to upstream when ready
gh pr create --repo taylorwilsdon/google_workspace_mcp
```

## Related Issues

- GitHub Issue (upstream): https://github.com/taylorwilsdon/google_workspace_mcp/issues/373
- OpenCode Issue: https://github.com/anomalyco/opencode/issues/9634

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret |
| `WORKSPACE_MCP_CREDENTIALS_DIR` | **THE KEY ONE** - Where to store/read credentials |
| `WORKSPACE_MCP_PORT` | Port for OAuth callback server |

## Contact

- **Maintainer:** Jay Herzog (jh@cavort.de)
- **Company:** CAVORT Konzepte GmbH
