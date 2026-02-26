"""
Salesforce Tools
================
Artemis Salesforce connector — full CRM orchestration for Sol.
OAuth2 password grant + direct token auth, SOQL/SOSL queries, SObject CRUD,
bulk API, Flows, Reports, and convenience wrappers.

Install: pip install artemis-connectors
Auto-discovered by solstice-agent via entry_points.
"""

import json
import logging
from typing import Any, Dict, Optional

log = logging.getLogger("artemis.connectors.salesforce")

# ---------------------------------------------------------------------------
# Module-level connection state
# ---------------------------------------------------------------------------
_client = None           # httpx.Client (sync)
_instance_url: str = ""
_access_token: Optional[str] = None
_api_version: str = "v59.0"

# OAuth2 token endpoint
_SF_TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"


def _require_connection() -> bool:
    return _client is not None and _access_token is not None


def _api(method: str, path: str, json_body=None, params=None) -> Dict[str, Any]:
    """Central API request handler with auth header and 401 handling."""
    if not _require_connection():
        raise RuntimeError("Not connected. Run sf_connect first.")

    # Build full URL — if path already starts with /services, use it as-is
    if path.startswith("/services"):
        url = f"{_instance_url}{path}"
    else:
        url = f"{_instance_url}/services/data/{_api_version}{path}"

    headers = {"Authorization": f"Bearer {_access_token}"}

    kwargs: Dict[str, Any] = {"headers": headers}
    if json_body is not None:
        kwargs["json"] = json_body
    if params is not None:
        kwargs["params"] = params

    resp = _client.request(method, url, **kwargs)

    # Handle 401
    if resp.status_code == 401:
        return {"error": "Authentication failed (401). Token may be expired — run sf_connect again."}

    resp.raise_for_status()
    if resp.status_code == 204:
        return {"success": True}
    # Some DELETE responses return empty body
    if not resp.text:
        return {"success": True}
    return resp.json()


def _fmt(data: Any) -> str:
    if isinstance(data, dict):
        return json.dumps(data, indent=2, default=str)
    if isinstance(data, list):
        return json.dumps(data, indent=2, default=str)
    return str(data)


# ---------------------------------------------------------------------------
# Tool 1: sf_connect
# ---------------------------------------------------------------------------
def sf_connect(
    instance_url: str = "",
    access_token: str = "",
    client_id: str = "",
    client_secret: str = "",
    username: str = "",
    password: str = "",
    security_token: str = "",
    login_url: str = "",
) -> str:
    """Authenticate with Salesforce via OAuth2 password grant or direct token."""
    global _client, _instance_url, _access_token

    try:
        import httpx
    except ImportError:
        return "Error: httpx required. Install with: pip install httpx"

    # Close existing
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass

    _access_token = None
    _instance_url = ""

    try:
        _client = httpx.Client(timeout=30.0)

        # Direct token mode
        if access_token and instance_url:
            _access_token = access_token
            _instance_url = instance_url.rstrip("/")
            # Verify by hitting API versions
            resp = _client.get(
                f"{_instance_url}/services/data/",
                headers={"Authorization": f"Bearer {_access_token}"},
            )
            resp.raise_for_status()
            versions = resp.json()
            latest = versions[-1]["version"] if versions else "?"
            log.info(f"Connected to Salesforce via direct token: {_instance_url}")
            return (
                f"Connected to Salesforce ({_instance_url}).\n"
                f"  Auth: direct token\n"
                f"  Latest API version: {latest}"
            )

        # OAuth2 password grant
        if not (client_id and client_secret and username and password):
            return (
                "Error: Provide either (access_token + instance_url) or "
                "(client_id + client_secret + username + password)."
            )

        token_url = login_url or _SF_TOKEN_URL
        resp = _client.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password + security_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        _access_token = data["access_token"]
        _instance_url = data["instance_url"].rstrip("/")

        log.info(f"Connected to Salesforce via OAuth2: {_instance_url}")
        return (
            f"Connected to Salesforce ({_instance_url}).\n"
            f"  Auth: OAuth2 password grant\n"
            f"  User: {username}"
        )
    except Exception as e:
        _client = None
        _access_token = None
        _instance_url = ""
        return f"Connection failed: {e}"


# ---------------------------------------------------------------------------
# Tool 2: sf_status
# ---------------------------------------------------------------------------
def sf_status() -> str:
    """Get Salesforce API versions and current user info."""
    try:
        # Get API versions
        versions_resp = _api("GET", "/services/data/")
        # Get current user info
        user_resp = _api("GET", f"/chatter/users/me")
        return (
            f"API Versions:\n{_fmt(versions_resp)}\n\n"
            f"Current User:\n{_fmt(user_resp)}"
        )
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool 3: sf_query
# ---------------------------------------------------------------------------
def sf_query(soql: str) -> str:
    """Execute a SOQL query and return records."""
    try:
        result = _api("GET", "/query", params={"q": soql})
        if "error" in result:
            return _fmt(result)
        records = result.get("records", [])
        total = result.get("totalSize", len(records))
        return f"Query returned {total} record(s).\n{_fmt(records)}"
    except Exception as e:
        return f"SOQL query failed: {e}"


# ---------------------------------------------------------------------------
# Tool 4: sf_search
# ---------------------------------------------------------------------------
def sf_search(sosl: str) -> str:
    """Execute a SOSL full-text search."""
    try:
        result = _api("GET", "/search", params={"q": sosl})
        if "error" in result:
            return _fmt(result)
        if isinstance(result, list):
            return f"Search returned {len(result)} result(s).\n{_fmt(result)}"
        search_records = result.get("searchRecords", [])
        return f"Search returned {len(search_records)} result(s).\n{_fmt(search_records)}"
    except Exception as e:
        return f"SOSL search failed: {e}"


# ---------------------------------------------------------------------------
# Tool 5: sf_describe
# ---------------------------------------------------------------------------
def sf_describe(object_name: str) -> str:
    """Describe an SObject — metadata, fields, relationships."""
    try:
        result = _api("GET", f"/sobjects/{object_name}/describe")
        if "error" in result:
            return _fmt(result)
        name = result.get("name", object_name)
        fields = result.get("fields", [])
        field_names = [f["name"] for f in fields[:50]]
        return (
            f"SObject: {name}\n"
            f"  Label: {result.get('label', '?')}\n"
            f"  Fields ({len(fields)}): {', '.join(field_names)}"
            f"{'...' if len(fields) > 50 else ''}\n"
            f"  Queryable: {result.get('queryable', '?')}\n"
            f"  Createable: {result.get('createable', '?')}\n"
            f"  Updateable: {result.get('updateable', '?')}"
        )
    except Exception as e:
        return f"Describe failed: {e}"


# ---------------------------------------------------------------------------
# Tool 6: sf_list_objects
# ---------------------------------------------------------------------------
def sf_list_objects() -> str:
    """List all available SObjects in the org."""
    try:
        result = _api("GET", "/sobjects")
        if "error" in result:
            return _fmt(result)
        sobjects = result.get("sobjects", [])
        names = [s["name"] for s in sobjects]
        return f"Found {len(names)} SObject(s).\n{', '.join(names)}"
    except Exception as e:
        return f"List objects failed: {e}"


# ---------------------------------------------------------------------------
# Tool 7: sf_get_record
# ---------------------------------------------------------------------------
def sf_get_record(object_name: str, record_id: str) -> str:
    """Get a single record by SObject type and record ID."""
    try:
        result = _api("GET", f"/sobjects/{object_name}/{record_id}")
        return _fmt(result)
    except Exception as e:
        return f"Get record failed: {e}"


# ---------------------------------------------------------------------------
# Tool 8: sf_create_record
# ---------------------------------------------------------------------------
def sf_create_record(object_name: str, fields: str) -> str:
    """Create a new record. Fields is a JSON string of field name/value pairs."""
    try:
        field_data = json.loads(fields)
        result = _api("POST", f"/sobjects/{object_name}", json_body=field_data)
        if "error" in result:
            return _fmt(result)
        record_id = result.get("id", "?")
        success = result.get("success", False)
        return f"Record created. ID: {record_id}, Success: {success}"
    except json.JSONDecodeError:
        return "Error: 'fields' must be valid JSON"
    except Exception as e:
        return f"Create record failed: {e}"


# ---------------------------------------------------------------------------
# Tool 9: sf_update_record
# ---------------------------------------------------------------------------
def sf_update_record(object_name: str, record_id: str, fields: str) -> str:
    """Update a record. Fields is a JSON string of field name/value pairs to update."""
    try:
        field_data = json.loads(fields)
        result = _api("PATCH", f"/sobjects/{object_name}/{record_id}", json_body=field_data)
        return f"Record {record_id} updated successfully."
    except json.JSONDecodeError:
        return "Error: 'fields' must be valid JSON"
    except Exception as e:
        return f"Update record failed: {e}"


# ---------------------------------------------------------------------------
# Tool 10: sf_delete_record
# ---------------------------------------------------------------------------
def sf_delete_record(object_name: str, record_id: str) -> str:
    """Delete a record by SObject type and record ID."""
    try:
        result = _api("DELETE", f"/sobjects/{object_name}/{record_id}")
        return f"Record {record_id} deleted successfully."
    except Exception as e:
        return f"Delete record failed: {e}"


# ---------------------------------------------------------------------------
# Tool 11: sf_bulk_query
# ---------------------------------------------------------------------------
def sf_bulk_query(soql: str) -> str:
    """Submit a bulk SOQL query job for large datasets."""
    try:
        body = {
            "operation": "query",
            "query": soql,
        }
        result = _api("POST", "/jobs/query", json_body=body)
        if "error" in result:
            return _fmt(result)
        job_id = result.get("id", "?")
        state = result.get("state", "?")
        return f"Bulk query job submitted. Job ID: {job_id}, State: {state}\n{_fmt(result)}"
    except Exception as e:
        return f"Bulk query failed: {e}"


# ---------------------------------------------------------------------------
# Tool 12: sf_get_user
# ---------------------------------------------------------------------------
def sf_get_user(user_id: str = "") -> str:
    """Get user details. If user_id is empty, returns current user via chatter/users/me."""
    try:
        if user_id:
            result = _api("GET", f"/sobjects/User/{user_id}")
        else:
            result = _api("GET", f"/chatter/users/me")
        return _fmt(result)
    except Exception as e:
        return f"Get user failed: {e}"


# ---------------------------------------------------------------------------
# Tool 13: sf_run_flow
# ---------------------------------------------------------------------------
def sf_run_flow(flow_api_name: str, inputs: str = "{}") -> str:
    """Invoke a Salesforce Flow by its API name."""
    try:
        body = {}
        if inputs and inputs != "{}":
            body["inputs"] = [json.loads(inputs)]
        else:
            body["inputs"] = [{}]
        result = _api("POST", f"/actions/custom/flow/{flow_api_name}", json_body=body)
        return f"Flow '{flow_api_name}' invoked.\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'inputs' must be valid JSON"
    except Exception as e:
        return f"Run flow failed: {e}"


# ---------------------------------------------------------------------------
# Tool 14: sf_get_report
# ---------------------------------------------------------------------------
def sf_get_report(report_id: str) -> str:
    """Run a Salesforce report and return its results."""
    try:
        result = _api("GET", f"/analytics/reports/{report_id}", params={"includeDetails": "true"})
        if "error" in result:
            return _fmt(result)
        report_meta = result.get("reportMetadata", {})
        name = report_meta.get("name", "?")
        report_format = report_meta.get("reportFormat", "?")
        fact_map = result.get("factMap", {})
        row_count = 0
        for key, val in fact_map.items():
            rows = val.get("rows", [])
            row_count += len(rows)
        return (
            f"Report: {name} ({report_format})\n"
            f"  Rows: {row_count}\n"
            f"{_fmt(result)}"
        )
    except Exception as e:
        return f"Get report failed: {e}"


# ---------------------------------------------------------------------------
# Tool 15: sf_create_task
# ---------------------------------------------------------------------------
def sf_create_task(
    subject: str,
    who_id: str = "",
    what_id: str = "",
    status: str = "Not Started",
    priority: str = "Normal",
    activity_date: str = "",
    description: str = "",
) -> str:
    """Create a Task record (convenience wrapper for common CRM task creation)."""
    try:
        fields: Dict[str, Any] = {
            "Subject": subject,
            "Status": status,
            "Priority": priority,
        }
        if who_id:
            fields["WhoId"] = who_id
        if what_id:
            fields["WhatId"] = what_id
        if activity_date:
            fields["ActivityDate"] = activity_date
        if description:
            fields["Description"] = description

        result = _api("POST", "/sobjects/Task", json_body=fields)
        if "error" in result:
            return _fmt(result)
        record_id = result.get("id", "?")
        return f"Task created. ID: {record_id}, Subject: '{subject}'"
    except Exception as e:
        return f"Create task failed: {e}"


# ---------------------------------------------------------------------------
# Schemas (OpenAI function-calling format — lowercase "object")
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "sf_connect": {
        "name": "sf_connect",
        "description": (
            "Authenticate with Salesforce. Supports OAuth2 password grant "
            "(client_id, client_secret, username, password+security_token) or "
            "direct access_token+instance_url. "
            "This is an Artemis premium connector — run this first to unlock all sf_* tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_url": {"type": "string", "description": "Salesforce instance URL (e.g. https://myorg.my.salesforce.com)"},
                "access_token": {"type": "string", "description": "Direct access token (skip OAuth2 flow)"},
                "client_id": {"type": "string", "description": "OAuth2 Connected App client ID"},
                "client_secret": {"type": "string", "description": "OAuth2 Connected App client secret"},
                "username": {"type": "string", "description": "Salesforce username"},
                "password": {"type": "string", "description": "Salesforce password"},
                "security_token": {"type": "string", "description": "Salesforce security token (appended to password)"},
                "login_url": {"type": "string", "description": "Login URL override (default: https://login.salesforce.com/services/oauth2/token)"},
            },
            "required": [],
        },
    },
    "sf_status": {
        "name": "sf_status",
        "description": "Get Salesforce API versions and current authenticated user info.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "sf_query": {
        "name": "sf_query",
        "description": "Execute a SOQL query against Salesforce and return matching records.",
        "parameters": {
            "type": "object",
            "properties": {
                "soql": {"type": "string", "description": "SOQL query string (e.g. SELECT Id, Name FROM Account LIMIT 10)"},
            },
            "required": ["soql"],
        },
    },
    "sf_search": {
        "name": "sf_search",
        "description": "Execute a SOSL full-text search across Salesforce objects.",
        "parameters": {
            "type": "object",
            "properties": {
                "sosl": {"type": "string", "description": "SOSL search string (e.g. FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name))"},
            },
            "required": ["sosl"],
        },
    },
    "sf_describe": {
        "name": "sf_describe",
        "description": "Describe a Salesforce SObject — get its metadata, fields, and relationships.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "SObject API name (e.g. Account, Contact, Opportunity)"},
            },
            "required": ["object_name"],
        },
    },
    "sf_list_objects": {
        "name": "sf_list_objects",
        "description": "List all available SObjects in the Salesforce org.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "sf_get_record": {
        "name": "sf_get_record",
        "description": "Get a single Salesforce record by SObject type and record ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "SObject API name (e.g. Account)"},
                "record_id": {"type": "string", "description": "The 15 or 18 character record ID"},
            },
            "required": ["object_name", "record_id"],
        },
    },
    "sf_create_record": {
        "name": "sf_create_record",
        "description": "Create a new Salesforce record. Pass fields as a JSON string.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "SObject API name (e.g. Account)"},
                "fields": {"type": "string", "description": "JSON string of field name/value pairs (e.g. {\"Name\": \"Acme Corp\"})"},
            },
            "required": ["object_name", "fields"],
        },
    },
    "sf_update_record": {
        "name": "sf_update_record",
        "description": "Update a Salesforce record by SObject type and record ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "SObject API name (e.g. Account)"},
                "record_id": {"type": "string", "description": "The record ID to update"},
                "fields": {"type": "string", "description": "JSON string of field name/value pairs to update"},
            },
            "required": ["object_name", "record_id", "fields"],
        },
    },
    "sf_delete_record": {
        "name": "sf_delete_record",
        "description": "Delete a Salesforce record by SObject type and record ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "SObject API name (e.g. Account)"},
                "record_id": {"type": "string", "description": "The record ID to delete"},
            },
            "required": ["object_name", "record_id"],
        },
    },
    "sf_bulk_query": {
        "name": "sf_bulk_query",
        "description": "Submit a bulk SOQL query job for large datasets (Bulk API 2.0).",
        "parameters": {
            "type": "object",
            "properties": {
                "soql": {"type": "string", "description": "SOQL query string for bulk export"},
            },
            "required": ["soql"],
        },
    },
    "sf_get_user": {
        "name": "sf_get_user",
        "description": "Get Salesforce user details. Omit user_id to get current user.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User record ID (leave empty for current user)"},
            },
            "required": [],
        },
    },
    "sf_run_flow": {
        "name": "sf_run_flow",
        "description": "Invoke a Salesforce Flow by its API name with optional input variables.",
        "parameters": {
            "type": "object",
            "properties": {
                "flow_api_name": {"type": "string", "description": "The Flow API name to invoke"},
                "inputs": {"type": "string", "description": "JSON string of input variables for the Flow"},
            },
            "required": ["flow_api_name"],
        },
    },
    "sf_get_report": {
        "name": "sf_get_report",
        "description": "Run a Salesforce report by ID and return detailed results.",
        "parameters": {
            "type": "object",
            "properties": {
                "report_id": {"type": "string", "description": "The Salesforce report ID"},
            },
            "required": ["report_id"],
        },
    },
    "sf_create_task": {
        "name": "sf_create_task",
        "description": "Create a Salesforce Task record (convenience wrapper for CRM task creation).",
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Task subject line"},
                "who_id": {"type": "string", "description": "Related Contact or Lead ID"},
                "what_id": {"type": "string", "description": "Related Account or Opportunity ID"},
                "status": {"type": "string", "description": "Task status (default: Not Started)", "enum": ["Not Started", "In Progress", "Completed", "Waiting on someone else", "Deferred"]},
                "priority": {"type": "string", "description": "Task priority (default: Normal)", "enum": ["High", "Normal", "Low"]},
                "activity_date": {"type": "string", "description": "Due date in YYYY-MM-DD format"},
                "description": {"type": "string", "description": "Task description / notes"},
            },
            "required": ["subject"],
        },
    },
}

# Map names to functions
_HANDLERS = {
    "sf_connect": sf_connect,
    "sf_status": sf_status,
    "sf_query": sf_query,
    "sf_search": sf_search,
    "sf_describe": sf_describe,
    "sf_list_objects": sf_list_objects,
    "sf_get_record": sf_get_record,
    "sf_create_record": sf_create_record,
    "sf_update_record": sf_update_record,
    "sf_delete_record": sf_delete_record,
    "sf_bulk_query": sf_bulk_query,
    "sf_get_user": sf_get_user,
    "sf_run_flow": sf_run_flow,
    "sf_get_report": sf_get_report,
    "sf_create_task": sf_create_task,
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_salesforce_tools(registry):
    """Register all 15 Salesforce tools with a ToolRegistry."""
    for name, handler in _HANDLERS.items():
        registry.register(name, handler, _SCHEMAS[name])
