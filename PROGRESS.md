# Progress: Google Workspace MCP Fork

## Current Status: ⏳ WAITING FOR UPSTREAM PR

**Objective:** Fix multi-account credential isolation bug in workspace-mcp

---

## Summary

**Problem:** `WORKSPACE_MCP_CREDENTIALS_DIR` environment variable was completely ignored, causing all MCP instances to use the same default credentials directory.

**Solution:** Updated `credential_store.py`, `google_auth.py`, and `main.py` to check environment variables in this priority:
1. `WORKSPACE_MCP_CREDENTIALS_DIR` (preferred)
2. `GOOGLE_MCP_CREDENTIALS_DIR` (backward compatibility)
3. `~/.google_workspace_mcp/credentials` (default)

**Commit:** `e98bb71` - "fix: respect WORKSPACE_MCP_CREDENTIALS_DIR for multi-account support"

---

## Verification Results (2026-01-20)

### Credential Isolation ✅
| Directory | Account | Status |
|-----------|---------|--------|
| `credentials-jh/` | jh@cavort.de | ✅ Isolated |
| `credentials-info/` | info@cavort.de | ✅ Isolated |
| `credentials/` (default) | - | ✅ Empty |

### Different Data Returned ✅
| Account | Labels Count | Sample Unique Labels |
|---------|--------------|---------------------|
| jh@cavort.de (personal) | 43 | `Privat`, `thx4`, `Kunde/DMK` |
| info@cavort.de (work) | 111 | `ACHE`, `Sports360`, `Burresi`, `SONAR` |

---

## Tasks

### Phase 1: Code Analysis ✅
- [x] Find where `WORKSPACE_MCP_CREDENTIALS_DIR` is read
- [x] Find OAuth callback handler (where credentials are saved)
- [x] Find credential loading logic (where credentials are read)
- [x] Identify all hardcoded paths to default credentials directory

### Phase 2: Implementation ✅
- [x] Fix OAuth callback to use `WORKSPACE_MCP_CREDENTIALS_DIR`
- [x] Fix credential loading to use `WORKSPACE_MCP_CREDENTIALS_DIR`
- [x] Add logging to show which credentials directory is being used
- [x] Ensure `--single-user` mode respects the env var

### Phase 3: Testing ✅
- [x] Test `WORKSPACE_MCP_CREDENTIALS_DIR` is respected
- [x] Test `GOOGLE_MCP_CREDENTIALS_DIR` backward compatibility
- [x] Test priority (WORKSPACE wins over GOOGLE)
- [x] Test `os.path.expanduser()` handles `~` correctly
- [x] Test full OAuth flow with two accounts
- [x] Test with opencode configuration
- [x] Verify different accounts return different data

### Phase 4: Upstream Contribution ✅
- [x] Push to our fork (cvrt-gmbh/google_workspace_mcp)
- [x] Create PR to upstream repo: https://github.com/taylorwilsdon/google_workspace_mcp/pull/374
- [x] Reference issue #373

### Phase 5: Post-Merge Cleanup (TODO)
- [ ] Wait for PR #374 to be merged or declined
- [ ] If merged: Update opencode.json to use `uvx workspace-mcp` instead of local fork
- [ ] If merged: Move fork from `cvrt-gmbh/google_workspace_mcp` to `cvrt-jh/google_workspace_mcp` (single location)
- [ ] If merged: Delete `cvrt-gmbh/mcp/workspace-mcp/` local directory
- [ ] If declined: Keep fork in `cvrt-jh/` only, remove from `cvrt-gmbh/`

---

## Files Modified

| File | Changes |
|------|---------|
| `auth/credential_store.py` | Check WORKSPACE_MCP_CREDENTIALS_DIR first, add expanduser(), add logging |
| `auth/google_auth.py` | Same priority logic in get_default_credentials_dir() |
| `main.py` | Display credentials directory in startup config |

---

## Test Results (2026-01-20)

### Unit Tests

#### Test 1: WORKSPACE_MCP_CREDENTIALS_DIR
```
WORKSPACE_MCP_CREDENTIALS_DIR=~/.google_workspace_mcp/credentials-jh
Result: /Users/jh/.google_workspace_mcp/credentials-jh
Match: True
```

#### Test 2: GOOGLE_MCP_CREDENTIALS_DIR (backward compat)
```
GOOGLE_MCP_CREDENTIALS_DIR=~/.google_workspace_mcp/credentials-legacy
Result: /Users/jh/.google_workspace_mcp/credentials-legacy
Match: True
```

#### Test 3: Priority (both set)
```
WORKSPACE_MCP_CREDENTIALS_DIR=~/.google_workspace_mcp/credentials-workspace
GOOGLE_MCP_CREDENTIALS_DIR=~/.google_workspace_mcp/credentials-google
Result: /Users/jh/.google_workspace_mcp/credentials-workspace (WORKSPACE wins)
Match: True
```

### Integration Test (Full OAuth + API Calls)

Both accounts authenticated successfully and return **different data**:
- `jh@cavort.de` → 43 Gmail labels (personal labels like `Privat`, `thx4`)
- `info@cavort.de` → 111 Gmail labels (business labels like `ACHE`, `Sports360`, `SONAR`)

---

## Configuration

### opencode.json (working configuration)

```json
"google": {
  "type": "local",
  "command": ["uv", "run", "--directory", "{env:HOME}/Git/cvrt-gmbh/mcp/workspace-mcp", "python", "-m", "main", "--single-user"],
  "environment": {
    "GOOGLE_OAUTH_CLIENT_ID": "{env:GOOGLE_CLIENT_ID}",
    "GOOGLE_OAUTH_CLIENT_SECRET": "{env:GOOGLE_CLIENT_SECRET}",
    "WORKSPACE_MCP_CREDENTIALS_DIR": "{env:HOME}/.google_workspace_mcp/credentials-jh",
    "WORKSPACE_MCP_PORT": "8000"
  },
  "enabled": true
},
"google-work": {
  "type": "local",
  "command": ["uv", "run", "--directory", "{env:HOME}/Git/cvrt-gmbh/mcp/workspace-mcp", "python", "-m", "main", "--single-user"],
  "environment": {
    "GOOGLE_OAUTH_CLIENT_ID": "{env:GOOGLE_WORK_CLIENT_ID}",
    "GOOGLE_OAUTH_CLIENT_SECRET": "{env:GOOGLE_WORK_CLIENT_SECRET}",
    "WORKSPACE_MCP_CREDENTIALS_DIR": "{env:HOME}/.google_workspace_mcp/credentials-info",
    "WORKSPACE_MCP_PORT": "8001"
  },
  "enabled": true
}
```

---

## Next Steps

1. ~~**Push to fork** - `git push origin main`~~ ✅ Done
2. ~~**Create upstream PR** - Submit fix to taylorwilsdon/google_workspace_mcp~~ ✅ Done: PR #374
3. ~~**Reference issue #373** in PR description~~ ✅ Done
4. **Wait for PR review** - Monitor https://github.com/taylorwilsdon/google_workspace_mcp/pull/374
5. **After merge/decline:** Consolidate fork to `cvrt-jh/` only (not `cvrt-gmbh/`)

---

## Related Links

- Upstream repo: https://github.com/taylorwilsdon/google_workspace_mcp
- Issue filed: https://github.com/taylorwilsdon/google_workspace_mcp/issues/373
- **Our PR:** https://github.com/taylorwilsdon/google_workspace_mcp/pull/374
- Our fork: https://github.com/cvrt-gmbh/google_workspace_mcp
- OpenCode issue: https://github.com/anomalyco/opencode/issues/9634

## Notes

**Fork Location:** Currently at `cvrt-gmbh/google_workspace_mcp` but should be moved to `cvrt-jh/` after PR is resolved. Personal forks belong in personal repo, not company repo.

---

## Session Log

### 2026-01-20 - Initial Setup
1. Discovered `WORKSPACE_MCP_CREDENTIALS_DIR` is ignored
2. Forked repo to `cvrt-gmbh/mcp/workspace-mcp`
3. Set up remotes (origin = our fork, upstream = original)
4. Created AGENTS.md, CLAUDE.md, PROGRESS.md

### 2026-01-20 - Implementation & Testing
1. Modified `auth/credential_store.py` - added env var priority logic
2. Modified `auth/google_auth.py` - same priority logic
3. Modified `main.py` - display credentials dir in startup
4. Tested all three scenarios (WORKSPACE, GOOGLE, priority)
5. Committed fix: `e98bb71`
6. Updated opencode.json to use local fork
7. Authenticated both accounts (jh@ and info@)
8. **Verified fix works:** Different accounts return different Gmail labels!
