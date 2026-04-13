"""Microsoft Todo tool for managing tasks and todo lists."""
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from azure.identity import ClientSecretCredential, InteractiveBrowserCredential
from msgraph.core import GraphClient

from app.exceptions import ToolError
from app.tool.base import BaseTool, ToolResult


class MicrosoftTodoTool(BaseTool):
    """Tool for managing Microsoft Todo tasks and lists."""

    name: str = "microsoft_todo"
    description: str = """Manage Microsoft Todo tasks and lists. Supports creating, updating, and deleting tasks and lists.

    Operations supported:
    - list_lists: Get all todo lists
    - list_tasks: Get tasks from a specific list
    - create_task: Create a new task in a list
    - update_task: Update an existing task
    - delete_task: Delete a task
    - create_list: Create a new todo list
    - delete_list: Delete a todo list
    - mark_complete: Mark a task as complete
    - mark_incomplete: Mark a task as incomplete
    """

    parameters: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "list_lists",
                    "list_tasks",
                    "create_task",
                    "update_task",
                    "delete_task",
                    "create_list",
                    "delete_list",
                    "mark_complete",
                    "mark_incomplete",
                ],
                "description": "The todo operation to perform",
            },
            "list_id": {
                "type": "string",
                "description": "The ID of the todo list",
            },
            "task_id": {
                "type": "string",
                "description": "The ID of the task (required for update/delete operations)",
            },
            "title": {
                "type": "string",
                "description": "Title of the task or list (required for create operations)",
            },
            "body": {
                "type": "string",
                "description": "Description or body of the task",
            },
            "due_date": {
                "type": "string",
                "description": "Due date in ISO format (e.g., '2024-04-15T10:00:00Z')",
            },
            "importance": {
                "type": "string",
                "enum": ["low", "normal", "high"],
                "description": "Importance level of the task",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Categories/tags for the task",
            },
            "is_reminder_on": {
                "type": "boolean",
                "description": "Whether to set a reminder for the task",
            },
        },
        "required": ["operation"],
    }

    _scopes = ["https://graph.microsoft.com/.default"]

    def __init__(self):
        super().__init__()
        self.graph_client = None
        self._auth_attempted = False
        self._auth_error = None

    def _authenticate(self):
        """Authenticate with Microsoft Graph API."""
        self._auth_attempted = True
        try:
            # Try to use environment variables for service principal
            tenant_id = os.getenv("AZURE_TENANT_ID")
            client_id = os.getenv("AZURE_CLIENT_ID")
            client_secret = os.getenv("AZURE_CLIENT_SECRET")

            if tenant_id and client_id and client_secret:
                credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
                self.graph_client = GraphClient(credential=credential)
                return

            # Try interactive browser authentication
            credential = InteractiveBrowserCredential()
            self.graph_client = GraphClient(credential=credential)
        except Exception as e:
            self._auth_error = f"Authentication error: {str(e)}"

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the Microsoft Todo operation."""
        try:
            # Lazy authentication on first use
            if not self._auth_attempted:
                self._authenticate()

            if self._auth_error:
                return ToolResult(
                    error=f"Microsoft Todo authentication failed: {self._auth_error}"
                )

            operation = kwargs.get("operation")

            if not self.graph_client:
                return ToolResult(error="Microsoft Todo service not initialized")

            if operation == "list_lists":
                result = await self._list_lists(**kwargs)
            elif operation == "list_tasks":
                result = await self._list_tasks(**kwargs)
            elif operation == "create_task":
                result = await self._create_task(**kwargs)
            elif operation == "update_task":
                result = await self._update_task(**kwargs)
            elif operation == "delete_task":
                result = await self._delete_task(**kwargs)
            elif operation == "create_list":
                result = await self._create_list(**kwargs)
            elif operation == "delete_list":
                result = await self._delete_list(**kwargs)
            elif operation == "mark_complete":
                result = await self._mark_complete(**kwargs)
            elif operation == "mark_incomplete":
                result = await self._mark_incomplete(**kwargs)
            else:
                return ToolResult(error=f"Unknown operation: {operation}")

            return ToolResult(output=result)
        except ToolError as e:
            return ToolResult(error=e.message)
        except Exception as e:
            return ToolResult(error=f"Error: {str(e)}")

    async def _list_lists(self, **kwargs) -> str:
        """List all todo lists."""
        try:
            response = await self.graph_client.get(
                "/me/todo/lists", request_options={"timeout": 10}
            )

            lists = response.get("value", [])
            if not lists:
                return "No todo lists found."

            list_data = []
            for todo_list in lists:
                list_info = {
                    "id": todo_list.get("id"),
                    "displayName": todo_list.get("displayName"),
                    "wellknownListName": todo_list.get("wellknownListName"),
                }
                list_data.append(list_info)

            return json.dumps(list_data, indent=2)
        except Exception as e:
            raise ToolError(f"Failed to list todo lists: {str(e)}")

    async def _list_tasks(self, list_id: str = None, **kwargs) -> str:
        """List tasks from a specific list."""
        if not list_id:
            raise ToolError("list_id is required for listing tasks")

        try:
            response = await self.graph_client.get(
                f"/me/todo/lists/{list_id}/tasks",
                request_options={"timeout": 10},
            )

            tasks = response.get("value", [])
            if not tasks:
                return f"No tasks found in list {list_id}."

            task_data = []
            for task in tasks:
                task_info = {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "status": task.get("status"),
                    "importance": task.get("importance"),
                    "dueDateTime": task.get("dueDateTime"),
                    "isReminderOn": task.get("isReminderOn"),
                    "categories": task.get("categories", []),
                }
                task_data.append(task_info)

            return json.dumps(task_data, indent=2)
        except Exception as e:
            raise ToolError(f"Failed to list tasks: {str(e)}")

    async def _create_task(
        self, list_id: str = None, title: str = None, **kwargs
    ) -> str:
        """Create a new task in a list."""
        if not list_id:
            raise ToolError("list_id is required for creating a task")
        if not title:
            raise ToolError("title is required for creating a task")

        try:
            task_body = {
                "title": title,
            }

            if kwargs.get("body"):
                task_body["body"] = {"content": kwargs.get("body")}

            if kwargs.get("due_date"):
                task_body["dueDateTime"] = {
                    "dateTime": kwargs.get("due_date"),
                    "timeZone": "UTC",
                }

            if kwargs.get("importance"):
                task_body["importance"] = kwargs.get("importance").lower()

            if kwargs.get("categories"):
                task_body["categories"] = kwargs.get("categories")

            if kwargs.get("is_reminder_on") is not None:
                task_body["isReminderOn"] = kwargs.get("is_reminder_on")

            response = await self.graph_client.post(
                f"/me/todo/lists/{list_id}/tasks",
                content=task_body,
                request_options={"timeout": 10},
            )

            task_id = response.get("id")
            return f"Task created successfully. Task ID: {task_id}"
        except Exception as e:
            raise ToolError(f"Failed to create task: {str(e)}")

    async def _update_task(
        self, list_id: str = None, task_id: str = None, **kwargs
    ) -> str:
        """Update an existing task."""
        if not list_id:
            raise ToolError("list_id is required for updating a task")
        if not task_id:
            raise ToolError("task_id is required for updating a task")

        try:
            task_body = {}

            if kwargs.get("title"):
                task_body["title"] = kwargs.get("title")

            if kwargs.get("body"):
                task_body["body"] = {"content": kwargs.get("body")}

            if kwargs.get("due_date"):
                task_body["dueDateTime"] = {
                    "dateTime": kwargs.get("due_date"),
                    "timeZone": "UTC",
                }

            if kwargs.get("importance"):
                task_body["importance"] = kwargs.get("importance").lower()

            if kwargs.get("categories"):
                task_body["categories"] = kwargs.get("categories")

            if kwargs.get("is_reminder_on") is not None:
                task_body["isReminderOn"] = kwargs.get("is_reminder_on")

            await self.graph_client.patch(
                f"/me/todo/lists/{list_id}/tasks/{task_id}",
                content=task_body,
                request_options={"timeout": 10},
            )

            return f"Task {task_id} updated successfully."
        except Exception as e:
            raise ToolError(f"Failed to update task: {str(e)}")

    async def _delete_task(
        self, list_id: str = None, task_id: str = None, **kwargs
    ) -> str:
        """Delete a task."""
        if not list_id:
            raise ToolError("list_id is required for deleting a task")
        if not task_id:
            raise ToolError("task_id is required for deleting a task")

        try:
            await self.graph_client.delete(
                f"/me/todo/lists/{list_id}/tasks/{task_id}",
                request_options={"timeout": 10},
            )

            return f"Task {task_id} deleted successfully."
        except Exception as e:
            raise ToolError(f"Failed to delete task: {str(e)}")

    async def _create_list(self, title: str = None, **kwargs) -> str:
        """Create a new todo list."""
        if not title:
            raise ToolError("title is required for creating a list")

        try:
            list_body = {"displayName": title}

            response = await self.graph_client.post(
                "/me/todo/lists",
                content=list_body,
                request_options={"timeout": 10},
            )

            list_id = response.get("id")
            return f"Todo list created successfully. List ID: {list_id}"
        except Exception as e:
            raise ToolError(f"Failed to create todo list: {str(e)}")

    async def _delete_list(self, list_id: str = None, **kwargs) -> str:
        """Delete a todo list."""
        if not list_id:
            raise ToolError("list_id is required for deleting a list")

        try:
            await self.graph_client.delete(
                f"/me/todo/lists/{list_id}",
                request_options={"timeout": 10},
            )

            return f"Todo list {list_id} deleted successfully."
        except Exception as e:
            raise ToolError(f"Failed to delete todo list: {str(e)}")

    async def _mark_complete(
        self, list_id: str = None, task_id: str = None, **kwargs
    ) -> str:
        """Mark a task as complete."""
        if not list_id:
            raise ToolError("list_id is required for marking a task complete")
        if not task_id:
            raise ToolError("task_id is required for marking a task complete")

        try:
            task_body = {"status": "completed"}

            await self.graph_client.patch(
                f"/me/todo/lists/{list_id}/tasks/{task_id}",
                content=task_body,
                request_options={"timeout": 10},
            )

            return f"Task {task_id} marked as complete."
        except Exception as e:
            raise ToolError(f"Failed to mark task as complete: {str(e)}")

    async def _mark_incomplete(
        self, list_id: str = None, task_id: str = None, **kwargs
    ) -> str:
        """Mark a task as incomplete."""
        if not list_id:
            raise ToolError("list_id is required for marking a task incomplete")
        if not task_id:
            raise ToolError("task_id is required for marking a task incomplete")

        try:
            task_body = {"status": "notStarted"}

            await self.graph_client.patch(
                f"/me/todo/lists/{list_id}/tasks/{task_id}",
                content=task_body,
                request_options={"timeout": 10},
            )

            return f"Task {task_id} marked as incomplete."
        except Exception as e:
            raise ToolError(f"Failed to mark task as incomplete: {str(e)}")
