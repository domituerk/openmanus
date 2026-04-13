"""Google Calendar tool for managing calendar events."""
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.exceptions import ToolError
from app.tool.base import BaseTool, ToolResult


class GoogleCalendarTool(BaseTool):
    """Tool for managing Google Calendar events."""

    name: str = "google_calendar"
    description: str = """Manage Google Calendar events. Supports listing, creating, updating, and deleting calendar events.

    Operations supported:
    - list_events: List events in a calendar within a date range
    - create_event: Create a new event with optional attendees
    - update_event: Update an existing event
    - delete_event: Delete an event
    - find_free_slots: Find available time slots when attendees are free
    """

    parameters: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list_events", "create_event", "update_event", "delete_event", "find_free_slots"],
                "description": "The calendar operation to perform",
            },
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID (usually email address, default is 'primary')",
            },
            "event_id": {
                "type": "string",
                "description": "Event ID (required for update/delete operations)",
            },
            "title": {
                "type": "string",
                "description": "Event title (required for create_event)",
            },
            "description": {
                "type": "string",
                "description": "Event description",
            },
            "start_time": {
                "type": "string",
                "description": "Start time in ISO format (e.g., '2024-04-15T10:00:00+02:00')",
            },
            "end_time": {
                "type": "string",
                "description": "End time in ISO format (e.g., '2024-04-15T11:00:00+02:00')",
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of attendee email addresses",
            },
            "location": {
                "type": "string",
                "description": "Event location",
            },
            "time_min": {
                "type": "string",
                "description": "Start of time range to search (ISO format)",
            },
            "time_max": {
                "type": "string",
                "description": "End of time range to search (ISO format)",
            },
            "min_duration_minutes": {
                "type": "integer",
                "description": "Minimum duration for free slots in minutes (default: 30)",
            },
        },
        "required": ["operation"],
    }

    _scopes = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self):
        super().__init__()
        self.service = None
        self._auth_attempted = False
        self._auth_error = None

    def _authenticate(self):
        """Authenticate with Google Calendar API."""
        self._auth_attempted = True
        try:
            # Try to load from service account credentials (for server environments)
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path and os.path.exists(creds_path):
                self.service = self._build_service_from_service_account(creds_path)
                return

            # Try to load from OAuth2 credentials file
            if os.path.exists("token.json"):
                creds = self._load_oauth_credentials("token.json")
                if creds:
                    self.service = build("calendar", "v3", credentials=creds)
                    return

            # Try to create new OAuth2 flow
            if os.path.exists("credentials.json"):
                creds = self._create_oauth_flow("credentials.json")
                if creds:
                    self.service = build("calendar", "v3", credentials=creds)
                    return

            self._auth_error = (
                "Google Calendar authentication failed. "
                "Please set GOOGLE_APPLICATION_CREDENTIALS or provide credentials.json"
            )
        except Exception as e:
            self._auth_error = f"Authentication error: {str(e)}"

    def _build_service_from_service_account(self, creds_path: str):
        """Build service from service account credentials."""
        credentials = Credentials.from_service_account_file(creds_path, scopes=self._scopes)
        return build("calendar", "v3", credentials=credentials)

    def _load_oauth_credentials(self, token_path: str) -> Optional[OAuth2Credentials]:
        """Load OAuth credentials from token.json file."""
        try:
            with open(token_path, "r") as token_file:
                token_data = json.load(token_file)
                # Create credentials from the token data
                creds = OAuth2Credentials.from_authorized_user_info(token_data)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                return creds
        except Exception as e:
            print(f"Error loading OAuth credentials: {str(e)}")
            return None

    def _create_oauth_flow(self, creds_path: str) -> Optional[OAuth2Credentials]:
        """Create new OAuth flow and save credentials."""
        try:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, self._scopes)
            creds = flow.run_local_server(port=0)

            # Save credentials for future use
            with open("token.json", "w") as token_file:
                token_file.write(creds.to_json())

            return creds
        except Exception as e:
            print(f"Error creating OAuth flow: {str(e)}")
            return None

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the Google Calendar operation."""
        try:
            # Lazy authentication on first use
            if not self._auth_attempted:
                self._authenticate()

            if self._auth_error:
                return ToolResult(error=f"Google Calendar authentication failed: {self._auth_error}")

            operation = kwargs.get("operation")

            if not self.service:
                return ToolResult(error="Google Calendar service not initialized")

            if operation == "list_events":
                result = self._list_events(**kwargs)
            elif operation == "create_event":
                result = self._create_event(**kwargs)
            elif operation == "update_event":
                result = self._update_event(**kwargs)
            elif operation == "delete_event":
                result = self._delete_event(**kwargs)
            elif operation == "find_free_slots":
                result = self._find_free_slots(**kwargs)
            else:
                return ToolResult(error=f"Unknown operation: {operation}")

            return ToolResult(output=result)
        except ToolError as e:
            return ToolResult(error=e.message)
        except Exception as e:
            return ToolResult(error=f"Error: {str(e)}")

    def _list_events(self, **kwargs) -> str:
        """List events in a calendar."""
        calendar_id = kwargs.get("calendar_id", "primary")
        time_min = kwargs.get("time_min")
        time_max = kwargs.get("time_max")

        if not time_min:
            time_min = datetime.utcnow().isoformat() + "Z"
        if not time_max:
            time_max = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"

        try:
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = events_result.get("items", [])
            if not events:
                return "No events found in the specified time range."

            event_list = []
            for event in events:
                event_info = {
                    "id": event.get("id"),
                    "summary": event.get("summary"),
                    "start": event.get("start", {}).get("dateTime", event.get("start", {}).get("date")),
                    "end": event.get("end", {}).get("dateTime", event.get("end", {}).get("date")),
                    "attendees": [a.get("email") for a in event.get("attendees", [])],
                }
                event_list.append(event_info)

            return json.dumps(event_list, indent=2)
        except Exception as e:
            raise ToolError(f"Failed to list events: {str(e)}")

    def _create_event(self, **kwargs) -> str:
        """Create a new calendar event."""
        calendar_id = kwargs.get("calendar_id", "primary")
        title = kwargs.get("title")
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        description = kwargs.get("description", "")
        location = kwargs.get("location", "")
        attendees = kwargs.get("attendees", [])

        if not title or not start_time or not end_time:
            raise ToolError("title, start_time, and end_time are required for creating an event")

        try:
            event = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
            }

            if attendees:
                event["attendees"] = [{"email": email} for email in attendees]

            created_event = self.service.events().insert(
                calendarId=calendar_id, body=event
            ).execute()

            return f"Event created successfully. Event ID: {created_event.get('id')}"
        except Exception as e:
            raise ToolError(f"Failed to create event: {str(e)}")

    def _update_event(self, **kwargs) -> str:
        """Update an existing calendar event."""
        calendar_id = kwargs.get("calendar_id", "primary")
        event_id = kwargs.get("event_id")
        title = kwargs.get("title")
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        description = kwargs.get("description")
        location = kwargs.get("location")
        attendees = kwargs.get("attendees")

        if not event_id:
            raise ToolError("event_id is required for updating an event")

        try:
            # Get the existing event
            event = self.service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            # Update fields if provided
            if title:
                event["summary"] = title
            if start_time:
                event["start"] = {"dateTime": start_time}
            if end_time:
                event["end"] = {"dateTime": end_time}
            if description is not None:
                event["description"] = description
            if location is not None:
                event["location"] = location
            if attendees:
                event["attendees"] = [{"email": email} for email in attendees]

            updated_event = self.service.events().update(
                calendarId=calendar_id, eventId=event_id, body=event
            ).execute()

            return f"Event updated successfully. Event ID: {updated_event.get('id')}"
        except Exception as e:
            raise ToolError(f"Failed to update event: {str(e)}")

    def _delete_event(self, **kwargs) -> str:
        """Delete a calendar event."""
        calendar_id = kwargs.get("calendar_id", "primary")
        event_id = kwargs.get("event_id")

        if not event_id:
            raise ToolError("event_id is required for deleting an event")

        try:
            self.service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            return f"Event {event_id} deleted successfully."
        except Exception as e:
            raise ToolError(f"Failed to delete event: {str(e)}")

    def _find_free_slots(self, **kwargs) -> str:
        """Find available time slots when specified attendees are free."""
        attendees = kwargs.get("attendees", [])
        time_min = kwargs.get("time_min")
        time_max = kwargs.get("time_max")
        min_duration_minutes = kwargs.get("min_duration_minutes", 30)

        if not time_min:
            time_min = datetime.utcnow().isoformat() + "Z"
        if not time_max:
            time_max = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"

        if not attendees:
            attendees = ["primary"]

        try:
            # Build the freebusy request
            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "items": [{"id": attendee} for attendee in attendees],
            }

            freebusy_result = self.service.freebusy().query(body=body).execute()

            # Process the busy times to find free slots
            free_slots = self._calculate_free_slots(
                freebusy_result, time_min, time_max, min_duration_minutes
            )

            if not free_slots:
                return "No free slots found for all attendees in the specified time range."

            return json.dumps(free_slots, indent=2)
        except Exception as e:
            raise ToolError(f"Failed to find free slots: {str(e)}")

    def _calculate_free_slots(
        self,
        freebusy_result: Dict,
        time_min: str,
        time_max: str,
        min_duration_minutes: int,
    ) -> List[Dict[str, str]]:
        """Calculate free time slots from freebusy data."""
        from dateutil import parser

        free_slots = []
        calendars = freebusy_result.get("calendars", {})

        # Merge busy times from all attendees
        all_busy = []
        for calendar_id, calendar_data in calendars.items():
            busy_times = calendar_data.get("busy", [])
            all_busy.extend(busy_times)

        # Sort busy times
        all_busy.sort(key=lambda x: x["start"])

        # Calculate free slots
        current_time = parser.parse(time_min)
        end_time = parser.parse(time_max)

        for busy in all_busy:
            busy_start = parser.parse(busy["start"])
            busy_end = parser.parse(busy["end"])

            # Check if there's a free slot before this busy time
            if current_time < busy_start:
                duration = (busy_start - current_time).total_seconds() / 60
                if duration >= min_duration_minutes:
                    free_slots.append(
                        {
                            "start": current_time.isoformat(),
                            "end": busy_start.isoformat(),
                            "duration_minutes": int(duration),
                        }
                    )

            # Move current time to after this busy slot
            current_time = max(current_time, busy_end)

        # Check for free time after the last busy slot
        if current_time < end_time:
            duration = (end_time - current_time).total_seconds() / 60
            if duration >= min_duration_minutes:
                free_slots.append(
                    {
                        "start": current_time.isoformat(),
                        "end": end_time.isoformat(),
                        "duration_minutes": int(duration),
                    }
                )

        return free_slots
