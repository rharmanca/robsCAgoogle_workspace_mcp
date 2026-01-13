"""
Manual test script for Apps Script integration

This script allows manual testing of Apps Script tools against real Google API.
Requires valid OAuth credentials and enabled Apps Script API.

Usage:
    python tests/gappsscript/manual_test.py

Note: This will interact with real Apps Script projects.
      Use with caution and in a test environment.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle


SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
]


def get_credentials():
    """
    Get OAuth credentials for Apps Script API.

    Returns:
        Credentials object
    """
    creds = None
    token_path = "token.pickle"

    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("client_secret.json"):
                print("Error: client_secret.json not found")
                print(
                    "Please download OAuth credentials from Google Cloud Console"
                )
                print(
                    "and save as client_secret.json in the project root"
                )
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secret.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return creds


async def test_list_projects(service):
    """Test listing Apps Script projects"""
    print("\n=== Test: List Projects ===")

    from gappsscript.apps_script_tools import list_script_projects

    try:
        result = await list_script_projects(
            service=service, user_google_email="test@example.com", page_size=10
        )
        print(result)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


async def test_create_project(service):
    """Test creating a new Apps Script project"""
    print("\n=== Test: Create Project ===")

    from gappsscript.apps_script_tools import create_script_project

    try:
        result = await create_script_project(
            service=service,
            user_google_email="test@example.com",
            title="MCP Test Project",
        )
        print(result)

        if "Script ID:" in result:
            script_id = result.split("Script ID: ")[1].split("\n")[0]
            return script_id
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


async def test_get_project(service, script_id):
    """Test retrieving project details"""
    print(f"\n=== Test: Get Project {script_id} ===")

    from gappsscript.apps_script_tools import get_script_project

    try:
        result = await get_script_project(
            service=service, user_google_email="test@example.com", script_id=script_id
        )
        print(result)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


async def test_update_content(service, script_id):
    """Test updating script content"""
    print(f"\n=== Test: Update Content {script_id} ===")

    from gappsscript.apps_script_tools import update_script_content

    files = [
        {
            "name": "Code",
            "type": "SERVER_JS",
            "source": """function testFunction() {
  Logger.log('Hello from MCP test!');
  return 'Test successful';
}""",
        }
    ]

    try:
        result = await update_script_content(
            service=service,
            user_google_email="test@example.com",
            script_id=script_id,
            files=files,
        )
        print(result)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


async def test_run_function(service, script_id):
    """Test running a script function"""
    print(f"\n=== Test: Run Function {script_id} ===")

    from gappsscript.apps_script_tools import run_script_function

    try:
        result = await run_script_function(
            service=service,
            user_google_email="test@example.com",
            script_id=script_id,
            function_name="testFunction",
            dev_mode=True,
        )
        print(result)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


async def test_create_deployment(service, script_id):
    """Test creating a deployment"""
    print(f"\n=== Test: Create Deployment {script_id} ===")

    from gappsscript.apps_script_tools import create_deployment

    try:
        result = await create_deployment(
            service=service,
            user_google_email="test@example.com",
            script_id=script_id,
            description="MCP Test Deployment",
        )
        print(result)

        if "Deployment ID:" in result:
            deployment_id = result.split("Deployment ID: ")[1].split("\n")[0]
            return deployment_id
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


async def test_list_deployments(service, script_id):
    """Test listing deployments"""
    print(f"\n=== Test: List Deployments {script_id} ===")

    from gappsscript.apps_script_tools import list_deployments

    try:
        result = await list_deployments(
            service=service, user_google_email="test@example.com", script_id=script_id
        )
        print(result)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


async def test_list_processes(service):
    """Test listing script processes"""
    print("\n=== Test: List Processes ===")

    from gappsscript.apps_script_tools import list_script_processes

    try:
        result = await list_script_processes(
            service=service, user_google_email="test@example.com", page_size=10
        )
        print(result)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


async def cleanup_test_project(service, script_id):
    """
    Cleanup test project (requires Drive API).
    Note: Apps Script API does not have a delete endpoint.
    Projects must be deleted via Drive API by moving to trash.
    """
    print(f"\n=== Cleanup: Delete Project {script_id} ===")
    print("Note: Apps Script projects must be deleted via Drive API")
    print(f"Please manually delete: https://script.google.com/d/{script_id}/edit")


async def run_all_tests():
    """Run all manual tests"""
    print("="*60)
    print("Apps Script MCP Manual Test Suite")
    print("="*60)

    print("\nGetting OAuth credentials...")
    creds = get_credentials()

    print("Building Apps Script API service...")
    service = build("script", "v1", credentials=creds)

    test_script_id = None
    deployment_id = None

    try:
        success = await test_list_projects(service)
        if not success:
            print("\nWarning: List projects failed")

        test_script_id = await test_create_project(service)
        if test_script_id:
            print(f"\nCreated test project: {test_script_id}")

            await test_get_project(service, test_script_id)
            await test_update_content(service, test_script_id)

            await asyncio.sleep(2)

            await test_run_function(service, test_script_id)

            deployment_id = await test_create_deployment(service, test_script_id)
            if deployment_id:
                print(f"\nCreated deployment: {deployment_id}")

            await test_list_deployments(service, test_script_id)
        else:
            print("\nSkipping tests that require a project (creation failed)")

        await test_list_processes(service)

    finally:
        if test_script_id:
            await cleanup_test_project(service, test_script_id)

    print("\n" + "="*60)
    print("Manual Test Suite Complete")
    print("="*60)


def main():
    """Main entry point"""
    print("\nIMPORTANT: This script will:")
    print("1. Create a test Apps Script project in your account")
    print("2. Run various operations on it")
    print("3. Leave the project for manual cleanup")
    print("\nYou must manually delete the test project after running this.")

    response = input("\nContinue? (yes/no): ")
    if response.lower() not in ["yes", "y"]:
        print("Aborted")
        return

    asyncio.run(run_all_tests())


if __name__ == "__main__":
    main()
