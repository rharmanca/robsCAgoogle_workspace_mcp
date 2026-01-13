"""
Google Apps Script MCP Tools

This module provides MCP tools for interacting with Google Apps Script API.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("list_script_projects", is_read_only=True, service_type="script")
@require_google_service("script", "script_readonly")
async def list_script_projects(
    service: Any,
    user_google_email: str,
    page_size: int = 50,
    page_token: Optional[str] = None,
) -> str:
    """
    Lists Google Apps Script projects accessible to the user.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        page_size: Number of results per page (default: 50)
        page_token: Token for pagination (optional)

    Returns:
        str: Formatted list of script projects
    """
    logger.info(
        f"[list_script_projects] Email: {user_google_email}, PageSize: {page_size}"
    )

    request_params = {"pageSize": page_size}
    if page_token:
        request_params["pageToken"] = page_token

    response = await asyncio.to_thread(
        service.projects().list(**request_params).execute
    )

    projects = response.get("projects", [])

    if not projects:
        return "No Apps Script projects found."

    output = [f"Found {len(projects)} Apps Script projects:"]
    for project in projects:
        title = project.get("title", "Untitled")
        script_id = project.get("scriptId", "Unknown ID")
        create_time = project.get("createTime", "Unknown")
        update_time = project.get("updateTime", "Unknown")

        output.append(
            f"- {title} (ID: {script_id}) Created: {create_time} Modified: {update_time}"
        )

    if "nextPageToken" in response:
        output.append(f"\nNext page token: {response['nextPageToken']}")

    logger.info(
        f"[list_script_projects] Found {len(projects)} projects for {user_google_email}"
    )
    return "\n".join(output)


@server.tool()
@handle_http_errors("get_script_project", is_read_only=True, service_type="script")
@require_google_service("script", "script_readonly")
async def get_script_project(
    service: Any,
    user_google_email: str,
    script_id: str,
) -> str:
    """
    Retrieves complete project details including all source files.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        script_id: The script project ID

    Returns:
        str: Formatted project details with all file contents
    """
    logger.info(f"[get_script_project] Email: {user_google_email}, ID: {script_id}")

    project = await asyncio.to_thread(
        service.projects().get(scriptId=script_id).execute
    )

    title = project.get("title", "Untitled")
    script_id = project.get("scriptId", "Unknown")
    creator = project.get("creator", {}).get("email", "Unknown")
    create_time = project.get("createTime", "Unknown")
    update_time = project.get("updateTime", "Unknown")

    output = [
        f"Project: {title} (ID: {script_id})",
        f"Creator: {creator}",
        f"Created: {create_time}",
        f"Modified: {update_time}",
        "",
        "Files:",
    ]

    files = project.get("files", [])
    for i, file in enumerate(files, 1):
        file_name = file.get("name", "Untitled")
        file_type = file.get("type", "Unknown")
        source = file.get("source", "")

        output.append(f"{i}. {file_name} ({file_type})")
        if source:
            output.append(f"   {source[:200]}{'...' if len(source) > 200 else ''}")
            output.append("")

    logger.info(f"[get_script_project] Retrieved project {script_id}")
    return "\n".join(output)


@server.tool()
@handle_http_errors("get_script_content", is_read_only=True, service_type="script")
@require_google_service("script", "script_readonly")
async def get_script_content(
    service: Any,
    user_google_email: str,
    script_id: str,
    file_name: str,
) -> str:
    """
    Retrieves content of a specific file within a project.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        script_id: The script project ID
        file_name: Name of the file to retrieve

    Returns:
        str: File content as string
    """
    logger.info(
        f"[get_script_content] Email: {user_google_email}, ID: {script_id}, File: {file_name}"
    )

    project = await asyncio.to_thread(
        service.projects().get(scriptId=script_id).execute
    )

    files = project.get("files", [])
    target_file = None

    for file in files:
        if file.get("name") == file_name:
            target_file = file
            break

    if not target_file:
        return f"File '{file_name}' not found in project {script_id}"

    source = target_file.get("source", "")
    file_type = target_file.get("type", "Unknown")

    output = [f"File: {file_name} ({file_type})", "", source]

    logger.info(f"[get_script_content] Retrieved file {file_name} from {script_id}")
    return "\n".join(output)


@server.tool()
@handle_http_errors("create_script_project", service_type="script")
@require_google_service("script", "script_projects")
async def create_script_project(
    service: Any,
    user_google_email: str,
    title: str,
    parent_id: Optional[str] = None,
) -> str:
    """
    Creates a new Apps Script project.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        title: Project title
        parent_id: Optional Drive folder ID or bound container ID

    Returns:
        str: Formatted string with new project details
    """
    logger.info(
        f"[create_script_project] Email: {user_google_email}, Title: {title}"
    )

    request_body = {"title": title}

    if parent_id:
        request_body["parentId"] = parent_id

    project = await asyncio.to_thread(
        service.projects().create(body=request_body).execute
    )

    script_id = project.get("scriptId", "Unknown")
    edit_url = f"https://script.google.com/d/{script_id}/edit"

    output = [
        f"Created Apps Script project: {title}",
        f"Script ID: {script_id}",
        f"Edit URL: {edit_url}",
    ]

    logger.info(f"[create_script_project] Created project {script_id}")
    return "\n".join(output)


@server.tool()
@handle_http_errors("update_script_content", service_type="script")
@require_google_service("script", "script_projects")
async def update_script_content(
    service: Any,
    user_google_email: str,
    script_id: str,
    files: List[Dict[str, str]],
) -> str:
    """
    Updates or creates files in a script project.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        script_id: The script project ID
        files: List of file objects with name, type, and source

    Returns:
        str: Formatted string confirming update with file list
    """
    logger.info(
        f"[update_script_content] Email: {user_google_email}, ID: {script_id}, Files: {len(files)}"
    )

    request_body = {"files": files}

    updated_content = await asyncio.to_thread(
        service.projects().updateContent(scriptId=script_id, body=request_body).execute
    )

    output = [f"Updated script project: {script_id}", "", "Modified files:"]

    for file in updated_content.get("files", []):
        file_name = file.get("name", "Untitled")
        file_type = file.get("type", "Unknown")
        output.append(f"- {file_name} ({file_type})")

    logger.info(f"[update_script_content] Updated {len(files)} files in {script_id}")
    return "\n".join(output)


@server.tool()
@handle_http_errors("run_script_function", service_type="script")
@require_google_service("script", "script_projects")
async def run_script_function(
    service: Any,
    user_google_email: str,
    script_id: str,
    function_name: str,
    parameters: Optional[List[Any]] = None,
    dev_mode: bool = False,
) -> str:
    """
    Executes a function in a deployed script.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        script_id: The script project ID
        function_name: Name of function to execute
        parameters: Optional list of parameters to pass
        dev_mode: Whether to run latest code vs deployed version

    Returns:
        str: Formatted string with execution result or error
    """
    logger.info(
        f"[run_script_function] Email: {user_google_email}, ID: {script_id}, Function: {function_name}"
    )

    request_body = {"function": function_name, "devMode": dev_mode}

    if parameters:
        request_body["parameters"] = parameters

    try:
        response = await asyncio.to_thread(
            service.scripts().run(scriptId=script_id, body=request_body).execute
        )

        if "error" in response:
            error_details = response["error"]
            error_message = error_details.get("message", "Unknown error")
            return f"Execution failed\nFunction: {function_name}\nError: {error_message}"

        result = response.get("response", {}).get("result")
        output = [
            "Execution successful",
            f"Function: {function_name}",
            f"Result: {result}",
        ]

        logger.info(f"[run_script_function] Successfully executed {function_name}")
        return "\n".join(output)

    except Exception as e:
        logger.error(f"[run_script_function] Execution error: {str(e)}")
        return f"Execution failed\nFunction: {function_name}\nError: {str(e)}"


@server.tool()
@handle_http_errors("create_deployment", service_type="script")
@require_google_service("script", "script_deployments")
async def create_deployment(
    service: Any,
    user_google_email: str,
    script_id: str,
    description: str,
    version_description: Optional[str] = None,
) -> str:
    """
    Creates a new deployment of the script.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        script_id: The script project ID
        description: Deployment description
        version_description: Optional version description

    Returns:
        str: Formatted string with deployment details
    """
    logger.info(
        f"[create_deployment] Email: {user_google_email}, ID: {script_id}, Desc: {description}"
    )

    request_body = {"description": description}

    if version_description:
        request_body["versionNumber"] = {"description": version_description}

    deployment = await asyncio.to_thread(
        service.projects()
        .deployments()
        .create(scriptId=script_id, body=request_body)
        .execute
    )

    deployment_id = deployment.get("deploymentId", "Unknown")
    deployment_config = deployment.get("deploymentConfig", {})

    output = [
        f"Created deployment for script: {script_id}",
        f"Deployment ID: {deployment_id}",
        f"Description: {description}",
    ]

    logger.info(f"[create_deployment] Created deployment {deployment_id}")
    return "\n".join(output)


@server.tool()
@handle_http_errors(
    "list_deployments", is_read_only=True, service_type="script"
)
@require_google_service("script", "script_deployments_readonly")
async def list_deployments(
    service: Any,
    user_google_email: str,
    script_id: str,
) -> str:
    """
    Lists all deployments for a script project.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        script_id: The script project ID

    Returns:
        str: Formatted string with deployment list
    """
    logger.info(f"[list_deployments] Email: {user_google_email}, ID: {script_id}")

    response = await asyncio.to_thread(
        service.projects().deployments().list(scriptId=script_id).execute
    )

    deployments = response.get("deployments", [])

    if not deployments:
        return f"No deployments found for script: {script_id}"

    output = [f"Deployments for script: {script_id}", ""]

    for i, deployment in enumerate(deployments, 1):
        deployment_id = deployment.get("deploymentId", "Unknown")
        description = deployment.get("description", "No description")
        update_time = deployment.get("updateTime", "Unknown")

        output.append(f"{i}. {description} ({deployment_id})")
        output.append(f"   Updated: {update_time}")
        output.append("")

    logger.info(f"[list_deployments] Found {len(deployments)} deployments")
    return "\n".join(output)


@server.tool()
@handle_http_errors("update_deployment", service_type="script")
@require_google_service("script", "script_deployments")
async def update_deployment(
    service: Any,
    user_google_email: str,
    script_id: str,
    deployment_id: str,
    description: Optional[str] = None,
) -> str:
    """
    Updates an existing deployment configuration.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        script_id: The script project ID
        deployment_id: The deployment ID to update
        description: Optional new description

    Returns:
        str: Formatted string confirming update
    """
    logger.info(
        f"[update_deployment] Email: {user_google_email}, Script: {script_id}, Deployment: {deployment_id}"
    )

    request_body = {}
    if description:
        request_body["description"] = description

    deployment = await asyncio.to_thread(
        service.projects()
        .deployments()
        .update(scriptId=script_id, deploymentId=deployment_id, body=request_body)
        .execute
    )

    output = [
        f"Updated deployment: {deployment_id}",
        f"Script: {script_id}",
        f"Description: {deployment.get('description', 'No description')}",
    ]

    logger.info(f"[update_deployment] Updated deployment {deployment_id}")
    return "\n".join(output)


@server.tool()
@handle_http_errors("delete_deployment", service_type="script")
@require_google_service("script", "script_deployments")
async def delete_deployment(
    service: Any,
    user_google_email: str,
    script_id: str,
    deployment_id: str,
) -> str:
    """
    Deletes a deployment.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        script_id: The script project ID
        deployment_id: The deployment ID to delete

    Returns:
        str: Confirmation message
    """
    logger.info(
        f"[delete_deployment] Email: {user_google_email}, Script: {script_id}, Deployment: {deployment_id}"
    )

    await asyncio.to_thread(
        service.projects()
        .deployments()
        .delete(scriptId=script_id, deploymentId=deployment_id)
        .execute
    )

    output = f"Deleted deployment: {deployment_id} from script: {script_id}"

    logger.info(f"[delete_deployment] Deleted deployment {deployment_id}")
    return output


@server.tool()
@handle_http_errors(
    "list_script_processes", is_read_only=True, service_type="script"
)
@require_google_service("script", "script_readonly")
async def list_script_processes(
    service: Any,
    user_google_email: str,
    page_size: int = 50,
    script_id: Optional[str] = None,
) -> str:
    """
    Lists recent execution processes for user's scripts.

    Args:
        service: Injected Google API service client
        user_google_email: User's email address
        page_size: Number of results (default: 50)
        script_id: Optional filter by script ID

    Returns:
        str: Formatted string with process list
    """
    logger.info(
        f"[list_script_processes] Email: {user_google_email}, PageSize: {page_size}"
    )

    request_params = {"pageSize": page_size}
    if script_id:
        request_params["scriptId"] = script_id

    response = await asyncio.to_thread(
        service.processes().list(**request_params).execute
    )

    processes = response.get("processes", [])

    if not processes:
        return "No recent script executions found."

    output = ["Recent script executions:", ""]

    for i, process in enumerate(processes, 1):
        function_name = process.get("functionName", "Unknown")
        process_type = process.get("processType", "Unknown")
        process_status = process.get("processStatus", "Unknown")
        start_time = process.get("startTime", "Unknown")
        duration = process.get("duration", "Unknown")
        user_access_level = process.get("userAccessLevel", "Unknown")

        output.append(f"{i}. {function_name}")
        output.append(f"   Status: {process_status}")
        output.append(f"   Started: {start_time}")
        output.append(f"   Duration: {duration}")
        output.append("")

    logger.info(f"[list_script_processes] Found {len(processes)} processes")
    return "\n".join(output)
