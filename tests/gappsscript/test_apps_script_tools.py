"""
Unit tests for Google Apps Script MCP tools

Tests all Apps Script tools with mocked API responses
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio


@pytest.mark.asyncio
async def test_list_script_projects():
    """Test listing Apps Script projects"""
    from gappsscript.apps_script_tools import list_script_projects

    mock_service = Mock()
    mock_response = {
        "projects": [
            {
                "scriptId": "test123",
                "title": "Test Project",
                "createTime": "2025-01-10T10:00:00Z",
                "updateTime": "2026-01-12T15:30:00Z",
            },
            {
                "scriptId": "test456",
                "title": "Another Project",
                "createTime": "2025-06-15T12:00:00Z",
                "updateTime": "2025-12-20T09:45:00Z",
            },
        ]
    }

    mock_service.projects().list().execute.return_value = mock_response

    result = await list_script_projects(
        service=mock_service, user_google_email="test@example.com", page_size=50
    )

    assert "Found 2 Apps Script projects" in result
    assert "Test Project" in result
    assert "test123" in result
    assert "Another Project" in result
    assert "test456" in result

    mock_service.projects().list.assert_called_once_with(pageSize=50)


@pytest.mark.asyncio
async def test_list_script_projects_empty():
    """Test listing projects when none exist"""
    from gappsscript.apps_script_tools import list_script_projects

    mock_service = Mock()
    mock_service.projects().list().execute.return_value = {"projects": []}

    result = await list_script_projects(
        service=mock_service, user_google_email="test@example.com"
    )

    assert result == "No Apps Script projects found."


@pytest.mark.asyncio
async def test_list_script_projects_with_pagination():
    """Test listing projects with pagination token"""
    from gappsscript.apps_script_tools import list_script_projects

    mock_service = Mock()
    mock_response = {
        "projects": [{"scriptId": "test123", "title": "Test"}],
        "nextPageToken": "token123",
    }

    mock_service.projects().list().execute.return_value = mock_response

    result = await list_script_projects(
        service=mock_service,
        user_google_email="test@example.com",
        page_token="prev_token",
    )

    assert "Next page token: token123" in result
    mock_service.projects().list.assert_called_once_with(
        pageSize=50, pageToken="prev_token"
    )


@pytest.mark.asyncio
async def test_get_script_project():
    """Test retrieving complete project details"""
    from gappsscript.apps_script_tools import get_script_project

    mock_service = Mock()
    mock_response = {
        "scriptId": "test123",
        "title": "Test Project",
        "creator": {"email": "creator@example.com"},
        "createTime": "2025-01-10T10:00:00Z",
        "updateTime": "2026-01-12T15:30:00Z",
        "files": [
            {"name": "Code.gs", "type": "SERVER_JS", "source": "function test() {}"},
            {
                "name": "appsscript.json",
                "type": "JSON",
                "source": '{"timeZone": "America/New_York"}',
            },
        ],
    }

    mock_service.projects().get().execute.return_value = mock_response

    result = await get_script_project(
        service=mock_service, user_google_email="test@example.com", script_id="test123"
    )

    assert "Project: Test Project (ID: test123)" in result
    assert "Creator: creator@example.com" in result
    assert "Code.gs" in result
    assert "appsscript.json" in result

    mock_service.projects().get.assert_called_once_with(scriptId="test123")


@pytest.mark.asyncio
async def test_get_script_content():
    """Test retrieving specific file content"""
    from gappsscript.apps_script_tools import get_script_content

    mock_service = Mock()
    mock_response = {
        "scriptId": "test123",
        "files": [
            {
                "name": "Code.gs",
                "type": "SERVER_JS",
                "source": "function sendEmail() {\n  // code here\n}",
            },
            {"name": "Other.gs", "type": "SERVER_JS", "source": "function other() {}"},
        ],
    }

    mock_service.projects().get().execute.return_value = mock_response

    result = await get_script_content(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        file_name="Code.gs",
    )

    assert "File: Code.gs" in result
    assert "function sendEmail()" in result

    mock_service.projects().get.assert_called_once_with(scriptId="test123")


@pytest.mark.asyncio
async def test_get_script_content_file_not_found():
    """Test retrieving non-existent file"""
    from gappsscript.apps_script_tools import get_script_content

    mock_service = Mock()
    mock_response = {
        "scriptId": "test123",
        "files": [{"name": "Code.gs", "type": "SERVER_JS", "source": ""}],
    }

    mock_service.projects().get().execute.return_value = mock_response

    result = await get_script_content(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        file_name="NonExistent.gs",
    )

    assert "File 'NonExistent.gs' not found" in result


@pytest.mark.asyncio
async def test_create_script_project():
    """Test creating new Apps Script project"""
    from gappsscript.apps_script_tools import create_script_project

    mock_service = Mock()
    mock_response = {
        "scriptId": "new123",
        "title": "New Project",
    }

    mock_service.projects().create().execute.return_value = mock_response

    result = await create_script_project(
        service=mock_service,
        user_google_email="test@example.com",
        title="New Project",
    )

    assert "Created Apps Script project: New Project" in result
    assert "Script ID: new123" in result
    assert "https://script.google.com/d/new123/edit" in result

    mock_service.projects().create.assert_called_once_with(body={"title": "New Project"})


@pytest.mark.asyncio
async def test_create_script_project_with_parent():
    """Test creating project with parent folder"""
    from gappsscript.apps_script_tools import create_script_project

    mock_service = Mock()
    mock_response = {"scriptId": "new123", "title": "New Project"}

    mock_service.projects().create().execute.return_value = mock_response

    result = await create_script_project(
        service=mock_service,
        user_google_email="test@example.com",
        title="New Project",
        parent_id="folder123",
    )

    assert "Script ID: new123" in result

    mock_service.projects().create.assert_called_once_with(
        body={"title": "New Project", "parentId": "folder123"}
    )


@pytest.mark.asyncio
async def test_update_script_content():
    """Test updating script project files"""
    from gappsscript.apps_script_tools import update_script_content

    mock_service = Mock()
    files_to_update = [
        {"name": "Code.gs", "type": "SERVER_JS", "source": "function test() {}"},
        {"name": "Helper.gs", "type": "SERVER_JS", "source": "function helper() {}"},
    ]

    mock_response = {
        "scriptId": "test123",
        "files": files_to_update,
    }

    mock_service.projects().updateContent().execute.return_value = mock_response

    result = await update_script_content(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        files=files_to_update,
    )

    assert "Updated script project: test123" in result
    assert "Code.gs" in result
    assert "Helper.gs" in result

    mock_service.projects().updateContent.assert_called_once_with(
        scriptId="test123", body={"files": files_to_update}
    )


@pytest.mark.asyncio
async def test_run_script_function_success():
    """Test successful script function execution"""
    from gappsscript.apps_script_tools import run_script_function

    mock_service = Mock()
    mock_response = {
        "response": {"result": "Email sent successfully"},
    }

    mock_service.scripts().run().execute.return_value = mock_response

    result = await run_script_function(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        function_name="sendEmail",
    )

    assert "Execution successful" in result
    assert "Function: sendEmail" in result
    assert "Email sent successfully" in result

    mock_service.scripts().run.assert_called_once_with(
        scriptId="test123", body={"function": "sendEmail", "devMode": False}
    )


@pytest.mark.asyncio
async def test_run_script_function_with_parameters():
    """Test running function with parameters"""
    from gappsscript.apps_script_tools import run_script_function

    mock_service = Mock()
    mock_response = {"response": {"result": "Success"}}

    mock_service.scripts().run().execute.return_value = mock_response

    result = await run_script_function(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        function_name="processData",
        parameters=["param1", 42, True],
        dev_mode=True,
    )

    assert "Execution successful" in result

    mock_service.scripts().run.assert_called_once_with(
        scriptId="test123",
        body={
            "function": "processData",
            "devMode": True,
            "parameters": ["param1", 42, True],
        },
    )


@pytest.mark.asyncio
async def test_run_script_function_error():
    """Test script execution error handling"""
    from gappsscript.apps_script_tools import run_script_function

    mock_service = Mock()
    mock_response = {
        "error": {"message": "ReferenceError: variable is not defined"},
    }

    mock_service.scripts().run().execute.return_value = mock_response

    result = await run_script_function(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        function_name="brokenFunction",
    )

    assert "Execution failed" in result
    assert "brokenFunction" in result
    assert "ReferenceError" in result


@pytest.mark.asyncio
async def test_create_deployment():
    """Test creating deployment"""
    from gappsscript.apps_script_tools import create_deployment

    mock_service = Mock()
    mock_response = {
        "deploymentId": "deploy123",
        "deploymentConfig": {},
    }

    mock_service.projects().deployments().create().execute.return_value = (
        mock_response
    )

    result = await create_deployment(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        description="Production deployment",
    )

    assert "Created deployment for script: test123" in result
    assert "Deployment ID: deploy123" in result
    assert "Production deployment" in result

    mock_service.projects().deployments().create.assert_called_once_with(
        scriptId="test123", body={"description": "Production deployment"}
    )


@pytest.mark.asyncio
async def test_create_deployment_with_version():
    """Test creating deployment with version description"""
    from gappsscript.apps_script_tools import create_deployment

    mock_service = Mock()
    mock_response = {"deploymentId": "deploy123"}

    mock_service.projects().deployments().create().execute.return_value = (
        mock_response
    )

    result = await create_deployment(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        description="Production",
        version_description="Version 1.0",
    )

    assert "Deployment ID: deploy123" in result

    call_args = mock_service.projects().deployments().create.call_args
    assert call_args[1]["body"]["versionNumber"]["description"] == "Version 1.0"


@pytest.mark.asyncio
async def test_list_deployments():
    """Test listing deployments"""
    from gappsscript.apps_script_tools import list_deployments

    mock_service = Mock()
    mock_response = {
        "deployments": [
            {
                "deploymentId": "deploy1",
                "description": "Production",
                "updateTime": "2026-01-10T12:00:00Z",
            },
            {
                "deploymentId": "deploy2",
                "description": "Staging",
                "updateTime": "2026-01-08T10:00:00Z",
            },
        ]
    }

    mock_service.projects().deployments().list().execute.return_value = mock_response

    result = await list_deployments(
        service=mock_service, user_google_email="test@example.com", script_id="test123"
    )

    assert "Deployments for script: test123" in result
    assert "Production" in result
    assert "deploy1" in result
    assert "Staging" in result

    mock_service.projects().deployments().list.assert_called_once_with(
        scriptId="test123"
    )


@pytest.mark.asyncio
async def test_list_deployments_empty():
    """Test listing deployments when none exist"""
    from gappsscript.apps_script_tools import list_deployments

    mock_service = Mock()
    mock_service.projects().deployments().list().execute.return_value = {
        "deployments": []
    }

    result = await list_deployments(
        service=mock_service, user_google_email="test@example.com", script_id="test123"
    )

    assert "No deployments found" in result


@pytest.mark.asyncio
async def test_update_deployment():
    """Test updating deployment"""
    from gappsscript.apps_script_tools import update_deployment

    mock_service = Mock()
    mock_response = {
        "deploymentId": "deploy123",
        "description": "Updated description",
    }

    mock_service.projects().deployments().update().execute.return_value = (
        mock_response
    )

    result = await update_deployment(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        deployment_id="deploy123",
        description="Updated description",
    )

    assert "Updated deployment: deploy123" in result
    assert "Script: test123" in result

    mock_service.projects().deployments().update.assert_called_once_with(
        scriptId="test123",
        deploymentId="deploy123",
        body={"description": "Updated description"},
    )


@pytest.mark.asyncio
async def test_delete_deployment():
    """Test deleting deployment"""
    from gappsscript.apps_script_tools import delete_deployment

    mock_service = Mock()
    mock_service.projects().deployments().delete().execute.return_value = {}

    result = await delete_deployment(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
        deployment_id="deploy123",
    )

    assert "Deleted deployment: deploy123 from script: test123" in result

    mock_service.projects().deployments().delete.assert_called_once_with(
        scriptId="test123", deploymentId="deploy123"
    )


@pytest.mark.asyncio
async def test_list_script_processes():
    """Test listing script execution processes"""
    from gappsscript.apps_script_tools import list_script_processes

    mock_service = Mock()
    mock_response = {
        "processes": [
            {
                "functionName": "sendEmail",
                "processType": "EDITOR",
                "processStatus": "COMPLETED",
                "startTime": "2026-01-13T09:00:00Z",
                "duration": "2.3s",
                "userAccessLevel": "OWNER",
            },
            {
                "functionName": "processData",
                "processType": "SIMPLE_TRIGGER",
                "processStatus": "FAILED",
                "startTime": "2026-01-13T08:55:00Z",
                "duration": "1.1s",
            },
        ]
    }

    mock_service.processes().list().execute.return_value = mock_response

    result = await list_script_processes(
        service=mock_service, user_google_email="test@example.com"
    )

    assert "Recent script executions" in result
    assert "sendEmail" in result
    assert "COMPLETED" in result
    assert "processData" in result
    assert "FAILED" in result

    mock_service.processes().list.assert_called_once_with(pageSize=50)


@pytest.mark.asyncio
async def test_list_script_processes_filtered():
    """Test listing processes filtered by script ID"""
    from gappsscript.apps_script_tools import list_script_processes

    mock_service = Mock()
    mock_response = {"processes": []}

    mock_service.processes().list().execute.return_value = mock_response

    result = await list_script_processes(
        service=mock_service,
        user_google_email="test@example.com",
        script_id="test123",
    )

    assert "No recent script executions found" in result

    mock_service.processes().list.assert_called_once_with(
        pageSize=50, scriptId="test123"
    )
