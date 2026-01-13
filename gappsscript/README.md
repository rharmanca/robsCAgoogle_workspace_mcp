# Google Apps Script MCP Tools

This module provides Model Context Protocol (MCP) tools for interacting with Google Apps Script API, enabling AI agents to create, manage, and execute Apps Script projects programmatically.

## Overview

Google Apps Script allows automation and extension of Google Workspace applications. This MCP integration provides 11 tools across core and extended tiers for complete Apps Script lifecycle management.

## Features

### Project Management
- List all Apps Script projects
- Get complete project details including all files
- Create new standalone or bound script projects
- Update script content (add/modify JavaScript files)

### Execution
- Execute functions with parameters
- Development mode for testing latest code
- Production deployment execution
- View execution history and status

### Deployment Management
- Create new deployments
- List all deployments for a project
- Update deployment configurations
- Delete outdated deployments

### Monitoring
- View recent script executions
- Check execution status and results
- Monitor for errors and failures

## Prerequisites

### 1. Enable Apps Script API

Visit Google Cloud Console and enable the Apps Script API:
[Enable Apps Script API](https://console.cloud.google.com/flows/enableapi?apiid=script.googleapis.com)

### 2. OAuth Scopes

The following OAuth scopes are required:

```
https://www.googleapis.com/auth/script.projects
https://www.googleapis.com/auth/script.projects.readonly
https://www.googleapis.com/auth/script.deployments
https://www.googleapis.com/auth/script.deployments.readonly
```

These are automatically requested when using the appscript tool tier.

## Tool Tiers

### Core Tier
Essential operations for reading, writing, and executing scripts:

- `list_script_projects`: List accessible projects
- `get_script_project`: Get full project with all files
- `get_script_content`: Get specific file content
- `create_script_project`: Create new project
- `update_script_content`: Modify project files
- `run_script_function`: Execute functions

### Extended Tier
Advanced deployment and monitoring:

- `create_deployment`: Create new deployment
- `list_deployments`: List all deployments
- `update_deployment`: Update deployment config
- `delete_deployment`: Remove deployment
- `list_script_processes`: View execution history

## Usage Examples

### List Projects

```python
# List all Apps Script projects
uv run main.py --tools appscript
# In MCP client: "Show me my Apps Script projects"
```

Example output:
```
Found 3 Apps Script projects:
- Email Automation (ID: abc123) Created: 2025-01-10 Modified: 2026-01-12
- Sheet Processor (ID: def456) Created: 2025-06-15 Modified: 2025-12-20
- Form Handler (ID: ghi789) Created: 2024-11-03 Modified: 2025-08-14
```

### Create New Project

```python
# Create a new Apps Script project
# In MCP client: "Create a new Apps Script project called 'Data Sync'"
```

Example output:
```
Created Apps Script project: Data Sync
Script ID: new123
Edit URL: https://script.google.com/d/new123/edit
```

### Get Project Details

```python
# Get complete project with all files
# In MCP client: "Show me the code for script abc123"
```

Example output:
```
Project: Email Automation (ID: abc123)
Creator: user@example.com
Created: 2025-01-10
Modified: 2026-01-12

Files:
1. Code.gs (SERVER_JS)
   function sendDailyEmail() {
     var sheet = SpreadsheetApp.getActiveSpreadsheet();
     // ... email logic
   }

2. appsscript.json (JSON)
   {"timeZone": "America/New_York", "dependencies": {}}
```

### Update Script Content

```python
# Update script files
# In MCP client: "Update my email script to add error handling"
```

The AI will:
1. Read current code
2. Generate improved version
3. Call `update_script_content` with new files

### Run Script Function

```python
# Execute a function
# In MCP client: "Run the sendDailyEmail function in script abc123"
```

Example output:
```
Execution successful
Function: sendDailyEmail
Result: Emails sent to 5 recipients
```

### Create Deployment

```python
# Deploy script for production
# In MCP client: "Deploy my email automation to production"
```

Example output:
```
Created deployment for script: abc123
Deployment ID: AKfy...xyz
Description: Production release
```

## Common Workflows

### 1. Create and Deploy New Automation

```
1. "Create a new Apps Script called 'Sales Report Generator'"
2. "Add code that generates a weekly sales report from Sheet X"
3. "Run the generateReport function to test it"
4. "Create a production deployment"
```

### 2. Debug Existing Script

```
1. "Show me the code for my expense tracker script"
2. "What errors occurred in recent executions?"
3. "Fix the error in the calculateTotal function"
4. "Run calculateTotal to verify the fix"
```

### 3. Version Management

```
1. "List all deployments for script abc123"
2. "Create a new deployment with description 'Bug fix v1.1'"
3. "Update the production deployment to use the latest version"
```

## File Types

Apps Script projects support three file types:

- **SERVER_JS**: Google Apps Script code (.gs files)
- **HTML**: HTML files for custom UIs
- **JSON**: Manifest file (appsscript.json)

## API Limitations

### Execution Timeouts
- Simple triggers: 30 seconds
- Custom functions: 30 seconds
- Script execution via API: 6 minutes

### Quota Limits
- Script executions per day: varies by account type
- URL Fetch calls: 20,000 per day (consumer accounts)

See [Apps Script Quotas](https://developers.google.com/apps-script/guides/services/quotas) for details.

### Cannot Execute Arbitrary Code
The `run_script_function` tool can only execute functions that are defined in the script. You cannot run arbitrary JavaScript code directly. To run new code:

1. Add function to script via `update_script_content`
2. Execute the function via `run_script_function`
3. Optionally remove the function after execution

## Error Handling

Common errors and solutions:

### 404: Script not found
- Verify script ID is correct
- Ensure you have access to the project

### 403: Permission denied
- Check OAuth scopes are authorized
- Verify you own or have access to the project

### Execution timeout
- Script exceeded 6-minute limit
- Optimize code or split into smaller functions

### Script authorization required
- Function needs additional permissions
- User must manually authorize in script editor

## Security Considerations

### OAuth Scopes
Scripts inherit the OAuth scopes of the MCP server. Functions that access other Google services (Gmail, Drive, etc.) will only work if those scopes are authorized.

### Script Permissions
Scripts run with the permissions of the script owner, not the user executing them. Be cautious when:
- Running scripts you did not create
- Granting additional permissions to scripts
- Executing functions that modify data

### Code Review
Always review code before executing, especially for:
- Scripts from unknown sources
- Functions that access sensitive data
- Operations that modify or delete data

## Testing

### Unit Tests
Run unit tests with mocked API responses:

```bash
uv run pytest tests/gappsscript/test_apps_script_tools.py
```

### Manual Testing
Test against real Apps Script API:

```bash
python tests/gappsscript/manual_test.py
```

Note: Manual tests create real projects in your account. Delete test projects after running.

## API Reference

Full API documentation:
- [Apps Script API Overview](https://developers.google.com/apps-script/api)
- [REST API Reference](https://developers.google.com/apps-script/api/reference/rest)
- [OAuth Scopes](https://developers.google.com/apps-script/api/how-tos/authorization)

## Troubleshooting

### "Apps Script API has not been used in project"
Enable the API in Google Cloud Console

### "Insufficient Permission"
- Verify OAuth scopes are authorized
- Re-authenticate if needed

### "Function not found"
- Check function name spelling
- Verify function exists in the script
- Ensure function is not private

### "Invalid project structure"
- Ensure at least one .gs file exists
- Verify JSON files are valid JSON
- Check file names don't contain invalid characters

## Contributing

When adding new Apps Script tools:

1. Follow existing patterns in `apps_script_tools.py`
2. Add comprehensive docstrings
3. Include unit tests
4. Update this README with examples
5. Test against real API before submitting

## License

MIT License - see project root LICENSE file
