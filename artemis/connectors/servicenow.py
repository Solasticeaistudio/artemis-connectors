"""
ServiceNow Tools
================
Artemis ServiceNow connector — ITSM, CMDB, change management, and scripting
via the ServiceNow Table API and REST APIs.

Install: pip install artemis-connectors
Auto-discovered by solstice-agent via entry_points.
"""

import json
import logging
import time
from typing import Any, Dict, Optional

log = logging.getLogger("artemis.connectors.servicenow")

# ---------------------------------------------------------------------------
# Module-level connection state
# ---------------------------------------------------------------------------
_client = None           # httpx.Client (sync)
_instance_url: str = ""
_auth_header: Optional[str] = None  # "Basic ..." or "Bearer ..."

# OAuth2 token management
_token_expires_at: float = 0
_oauth_client_id: str = ""
_oauth_client_secret: str = ""


def _require_connection() -> bool:
    return _client is not None and _auth_header is not None


def _refresh_oauth_token_if_needed() -> Optional[str]:
    """Refresh OAuth2 Bearer token if expired or about to expire (30s buffer)."""
    global _auth_header, _token_expires_at

    if _auth_header and _auth_header.startswith("Bearer") and time.time() < (_token_expires_at - 30):
        return _auth_header

    if not _client or not _instance_url or not _oauth_client_id:
        return None

    try:
        resp = _client.post(
            f"{_instance_url}/oauth_token.do",
            data={
                "grant_type": "client_credentials",
                "client_id": _oauth_client_id,
                "client_secret": _oauth_client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        _auth_header = f"Bearer {token}"
        _token_expires_at = time.time() + int(data.get("expires_in", 1800))
        log.info(f"ServiceNow OAuth2 token acquired, expires in {data.get('expires_in', 1800)}s")
        return _auth_header
    except Exception as e:
        log.error(f"OAuth2 token refresh failed: {e}")
        return None


def _api(method: str, path: str, json_body=None, params=None) -> Dict[str, Any]:
    """Central API request handler. Prepends _instance_url, sets auth and JSON headers."""
    if not _require_connection():
        raise RuntimeError("Not connected. Run snow_connect first.")

    # Refresh OAuth2 token if applicable
    if _auth_header and _auth_header.startswith("Bearer"):
        refreshed = _refresh_oauth_token_if_needed()
        if not refreshed:
            raise RuntimeError("Failed to refresh OAuth2 token.")

    url = f"{_instance_url}{path}"
    headers = {
        "Authorization": _auth_header,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    kwargs: Dict[str, Any] = {"headers": headers}
    if json_body is not None:
        kwargs["json"] = json_body
    if params is not None:
        kwargs["params"] = params

    resp = _client.request(method, url, **kwargs)
    resp.raise_for_status()

    if resp.status_code == 204:
        return {"success": True}

    data = resp.json()
    # ServiceNow wraps results in a "result" key
    if "result" in data:
        return data["result"] if isinstance(data["result"], dict) else {"items": data["result"]}
    return data


def _fmt(data: Any) -> str:
    if isinstance(data, dict):
        return json.dumps(data, indent=2, default=str)
    if isinstance(data, list):
        return json.dumps(data, indent=2, default=str)
    return str(data)


# ---------------------------------------------------------------------------
# Tool 1: snow_connect
# ---------------------------------------------------------------------------
def snow_connect(
    instance_url: str,
    username: str = "",
    password: str = "",
    client_id: str = "",
    client_secret: str = "",
) -> str:
    """Authenticate with a ServiceNow instance. Supports Basic Auth and OAuth2."""
    global _client, _instance_url, _auth_header
    global _token_expires_at, _oauth_client_id, _oauth_client_secret

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

    _auth_header = None
    _token_expires_at = 0
    _instance_url = instance_url.rstrip("/")

    try:
        _client = httpx.Client(timeout=30.0)

        if client_id and client_secret:
            # OAuth2 flow
            _oauth_client_id = client_id
            _oauth_client_secret = client_secret
            token_resp = _client.post(
                f"{_instance_url}/oauth_token.do",
                data={
                    "grant_type": "password",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "username": username,
                    "password": password,
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            _auth_header = f"Bearer {token_data['access_token']}"
            _token_expires_at = time.time() + int(token_data.get("expires_in", 1800))
            auth_mode = "OAuth2"
        elif username and password:
            # Basic Auth
            import base64
            creds = base64.b64encode(f"{username}:{password}".encode()).decode()
            _auth_header = f"Basic {creds}"
            _oauth_client_id = ""
            _oauth_client_secret = ""
            auth_mode = "Basic"
        else:
            _client = None
            return "Error: Provide username/password for Basic Auth, or client_id/client_secret for OAuth2."

        # Test connectivity
        test_resp = _client.get(
            f"{_instance_url}/api/now/table/sys_properties",
            params={"sysparm_limit": "1"},
            headers={
                "Authorization": _auth_header,
                "Accept": "application/json",
            },
        )
        test_resp.raise_for_status()

        return (
            f"Connected to ServiceNow ({_instance_url}).\n"
            f"  Auth: {auth_mode}\n"
            f"  Status: OK (test query succeeded)"
        )
    except Exception as e:
        _client = None
        _auth_header = None
        return f"Connection failed: {e}"


# ---------------------------------------------------------------------------
# Tool 2: snow_status
# ---------------------------------------------------------------------------
def snow_status() -> str:
    """Get ServiceNow instance info: instance name and basic properties."""
    try:
        result = _api(
            "GET",
            "/api/now/table/sys_properties",
            params={
                "sysparm_query": "name=instance_name",
                "sysparm_fields": "name,value",
                "sysparm_limit": "1",
            },
        )
        items = result.get("items", [result] if isinstance(result, dict) else result)
        instance_name = "unknown"
        if items and isinstance(items, list) and len(items) > 0:
            instance_name = items[0].get("value", "unknown")

        return (
            f"ServiceNow Instance Status\n"
            f"  URL: {_instance_url}\n"
            f"  Instance Name: {instance_name}\n"
            f"  Connected: True"
        )
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool 3: snow_query
# ---------------------------------------------------------------------------
def snow_query(
    table: str,
    query: str = "",
    limit: int = 20,
    fields: str = "",
) -> str:
    """Query any ServiceNow table with an encoded query string."""
    try:
        params: Dict[str, Any] = {"sysparm_limit": str(limit)}
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = fields

        result = _api("GET", f"/api/now/table/{table}", params=params)
        items = result.get("items", [result] if isinstance(result, dict) else result)
        if isinstance(items, list):
            return f"Found {len(items)} record(s) in '{table}'.\n{_fmt(items)}"
        return _fmt(result)
    except Exception as e:
        return f"Query failed: {e}"


# ---------------------------------------------------------------------------
# Tool 4: snow_get_record
# ---------------------------------------------------------------------------
def snow_get_record(table: str, sys_id: str) -> str:
    """Get a single record from a ServiceNow table by sys_id."""
    try:
        result = _api("GET", f"/api/now/table/{table}/{sys_id}")
        return _fmt(result)
    except Exception as e:
        return f"Get record failed: {e}"


# ---------------------------------------------------------------------------
# Tool 5: snow_create_record
# ---------------------------------------------------------------------------
def snow_create_record(table: str, data: str = "{}") -> str:
    """Create a record in any ServiceNow table. Data is a JSON string of field values."""
    try:
        body = json.loads(data)
        result = _api("POST", f"/api/now/table/{table}", json_body=body)
        sys_id = result.get("sys_id", "?") if isinstance(result, dict) else "?"
        return f"Record created in '{table}'. sys_id: {sys_id}\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'data' must be valid JSON"
    except Exception as e:
        return f"Create record failed: {e}"


# ---------------------------------------------------------------------------
# Tool 6: snow_update_record
# ---------------------------------------------------------------------------
def snow_update_record(table: str, sys_id: str, data: str = "{}") -> str:
    """Update a record in a ServiceNow table. Data is a JSON string of fields to update."""
    try:
        body = json.loads(data)
        result = _api("PATCH", f"/api/now/table/{table}/{sys_id}", json_body=body)
        return f"Record updated in '{table}' (sys_id: {sys_id}).\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'data' must be valid JSON"
    except Exception as e:
        return f"Update record failed: {e}"


# ---------------------------------------------------------------------------
# Tool 7: snow_delete_record
# ---------------------------------------------------------------------------
def snow_delete_record(table: str, sys_id: str) -> str:
    """Delete a record from a ServiceNow table by sys_id."""
    try:
        _api("DELETE", f"/api/now/table/{table}/{sys_id}")
        return f"Record deleted from '{table}' (sys_id: {sys_id})."
    except Exception as e:
        return f"Delete record failed: {e}"


# ---------------------------------------------------------------------------
# Tool 8: snow_search_incidents
# ---------------------------------------------------------------------------
def snow_search_incidents(
    state: str = "",
    priority: str = "",
    assigned_to: str = "",
    short_description: str = "",
    limit: int = 20,
) -> str:
    """Search incidents with convenience filters."""
    try:
        parts = []
        if state:
            parts.append(f"state={state}")
        if priority:
            parts.append(f"priority={priority}")
        if assigned_to:
            parts.append(f"assigned_to={assigned_to}")
        if short_description:
            parts.append(f"short_descriptionLIKE{short_description}")
        query = "^".join(parts)

        params: Dict[str, Any] = {"sysparm_limit": str(limit)}
        if query:
            params["sysparm_query"] = query

        result = _api("GET", "/api/now/table/incident", params=params)
        items = result.get("items", [result] if isinstance(result, dict) else result)
        if isinstance(items, list):
            return f"Found {len(items)} incident(s).\n{_fmt(items)}"
        return _fmt(result)
    except Exception as e:
        return f"Search incidents failed: {e}"


# ---------------------------------------------------------------------------
# Tool 9: snow_create_incident
# ---------------------------------------------------------------------------
def snow_create_incident(
    short_description: str,
    description: str = "",
    priority: str = "3",
    urgency: str = "2",
    category: str = "",
    assigned_to: str = "",
) -> str:
    """Create an incident in ServiceNow."""
    try:
        body: Dict[str, Any] = {"short_description": short_description}
        if description:
            body["description"] = description
        if priority:
            body["priority"] = priority
        if urgency:
            body["urgency"] = urgency
        if category:
            body["category"] = category
        if assigned_to:
            body["assigned_to"] = assigned_to

        result = _api("POST", "/api/now/table/incident", json_body=body)
        number = result.get("number", "?") if isinstance(result, dict) else "?"
        sys_id = result.get("sys_id", "?") if isinstance(result, dict) else "?"
        return (
            f"Incident created.\n"
            f"  Number: {number}\n"
            f"  sys_id: {sys_id}\n"
            f"  Priority: {priority}, Urgency: {urgency}\n{_fmt(result)}"
        )
    except Exception as e:
        return f"Create incident failed: {e}"


# ---------------------------------------------------------------------------
# Tool 10: snow_resolve_incident
# ---------------------------------------------------------------------------
def snow_resolve_incident(
    sys_id: str,
    close_code: str = "Solved (Permanently)",
    close_notes: str = "",
) -> str:
    """Resolve an incident by setting state=6 (Resolved) with close code and notes."""
    try:
        body: Dict[str, Any] = {
            "state": "6",
            "close_code": close_code,
        }
        if close_notes:
            body["close_notes"] = close_notes

        result = _api("PATCH", f"/api/now/table/incident/{sys_id}", json_body=body)
        return f"Incident {sys_id} resolved.\n  Close code: {close_code}\n{_fmt(result)}"
    except Exception as e:
        return f"Resolve incident failed: {e}"


# ---------------------------------------------------------------------------
# Tool 11: snow_search_changes
# ---------------------------------------------------------------------------
def snow_search_changes(
    state: str = "",
    priority: str = "",
    assigned_to: str = "",
    type: str = "",
    limit: int = 20,
) -> str:
    """Search change requests with convenience filters."""
    try:
        parts = []
        if state:
            parts.append(f"state={state}")
        if priority:
            parts.append(f"priority={priority}")
        if assigned_to:
            parts.append(f"assigned_to={assigned_to}")
        if type:
            parts.append(f"type={type}")
        query = "^".join(parts)

        params: Dict[str, Any] = {"sysparm_limit": str(limit)}
        if query:
            params["sysparm_query"] = query

        result = _api("GET", "/api/now/table/change_request", params=params)
        items = result.get("items", [result] if isinstance(result, dict) else result)
        if isinstance(items, list):
            return f"Found {len(items)} change request(s).\n{_fmt(items)}"
        return _fmt(result)
    except Exception as e:
        return f"Search changes failed: {e}"


# ---------------------------------------------------------------------------
# Tool 12: snow_get_cmdb_ci
# ---------------------------------------------------------------------------
def snow_get_cmdb_ci(sys_id: str) -> str:
    """Get a CMDB Configuration Item by sys_id."""
    try:
        result = _api("GET", f"/api/now/table/cmdb_ci/{sys_id}")
        name = result.get("name", "?") if isinstance(result, dict) else "?"
        ci_class = result.get("sys_class_name", "?") if isinstance(result, dict) else "?"
        return f"CMDB CI: {name} ({ci_class})\n{_fmt(result)}"
    except Exception as e:
        return f"Get CMDB CI failed: {e}"


# ---------------------------------------------------------------------------
# Tool 13: snow_search_cmdb
# ---------------------------------------------------------------------------
def snow_search_cmdb(
    query: str = "",
    fields: str = "name,sys_id,sys_class_name,operational_status",
    limit: int = 20,
) -> str:
    """Search CMDB Configuration Items."""
    try:
        params: Dict[str, Any] = {
            "sysparm_limit": str(limit),
            "sysparm_fields": fields,
        }
        if query:
            params["sysparm_query"] = query

        result = _api("GET", "/api/now/table/cmdb_ci", params=params)
        items = result.get("items", [result] if isinstance(result, dict) else result)
        if isinstance(items, list):
            return f"Found {len(items)} CMDB CI(s).\n{_fmt(items)}"
        return _fmt(result)
    except Exception as e:
        return f"Search CMDB failed: {e}"


# ---------------------------------------------------------------------------
# Tool 14: snow_list_tables
# ---------------------------------------------------------------------------
def snow_list_tables(limit: int = 50) -> str:
    """List available ServiceNow tables."""
    try:
        result = _api(
            "GET",
            "/api/now/table/sys_db_object",
            params={
                "sysparm_fields": "name,label",
                "sysparm_limit": str(limit),
            },
        )
        items = result.get("items", [result] if isinstance(result, dict) else result)
        if isinstance(items, list):
            lines = [f"Found {len(items)} table(s):"]
            for t in items:
                if isinstance(t, dict):
                    lines.append(f"  {t.get('name', '?')} — {t.get('label', '')}")
            return "\n".join(lines)
        return _fmt(result)
    except Exception as e:
        return f"List tables failed: {e}"


# ---------------------------------------------------------------------------
# Tool 15: snow_run_script
# ---------------------------------------------------------------------------
def snow_run_script(
    script: str,
    name: str = "ArtemisScript",
) -> str:
    """Run a server-side GlideRecord script via the ServiceNow Scripted REST API or background script endpoint."""
    try:
        # Use the ServiceNow scripted REST / background script evaluation endpoint
        body = {
            "script": script,
        }
        # Try the background script evaluation table API
        result = _api(
            "POST",
            "/api/now/table/sys_script_include",
            json_body={
                "name": name,
                "script": script,
                "api_name": name.lower().replace(" ", "_"),
                "active": "true",
            },
        )
        sys_id = result.get("sys_id", "?") if isinstance(result, dict) else "?"
        return f"Script include created. sys_id: {sys_id}, name: {name}\n{_fmt(result)}"
    except Exception as e:
        return f"Run script failed: {e}"


# ---------------------------------------------------------------------------
# Schemas (OpenAI function-calling format — lowercase "object")
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "snow_connect": {
        "name": "snow_connect",
        "description": (
            "Authenticate with a ServiceNow instance. Supports Basic Auth (username/password) "
            "and OAuth2 (client_id/client_secret via /oauth_token.do). "
            "This is an Artemis premium connector — run this first to unlock all snow_* tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_url": {"type": "string", "description": "ServiceNow instance URL (e.g. https://dev12345.service-now.com)"},
                "username": {"type": "string", "description": "ServiceNow username (for Basic Auth or OAuth2 password grant)"},
                "password": {"type": "string", "description": "ServiceNow password"},
                "client_id": {"type": "string", "description": "OAuth2 client ID (optional, enables OAuth2 flow)"},
                "client_secret": {"type": "string", "description": "OAuth2 client secret"},
            },
            "required": ["instance_url"],
        },
    },
    "snow_status": {
        "name": "snow_status",
        "description": "Get ServiceNow instance info: instance name and connection status.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "snow_query": {
        "name": "snow_query",
        "description": (
            "Query any ServiceNow table with an encoded query string. "
            "Use sysparm_query syntax (e.g. 'active=true^priority=1')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name (e.g. incident, change_request, cmdb_ci)"},
                "query": {"type": "string", "description": "Encoded query string (e.g. 'active=true^priority=1')"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
                "fields": {"type": "string", "description": "Comma-separated field names to return"},
            },
            "required": ["table"],
        },
    },
    "snow_get_record": {
        "name": "snow_get_record",
        "description": "Get a single record from a ServiceNow table by sys_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "sys_id": {"type": "string", "description": "The record sys_id"},
            },
            "required": ["table", "sys_id"],
        },
    },
    "snow_create_record": {
        "name": "snow_create_record",
        "description": "Create a record in any ServiceNow table. Pass field values as a JSON string.",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "data": {"type": "string", "description": "JSON string of field values"},
            },
            "required": ["table"],
        },
    },
    "snow_update_record": {
        "name": "snow_update_record",
        "description": "Update a record in a ServiceNow table by sys_id. Pass fields to update as a JSON string.",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "sys_id": {"type": "string", "description": "The record sys_id"},
                "data": {"type": "string", "description": "JSON string of fields to update"},
            },
            "required": ["table", "sys_id"],
        },
    },
    "snow_delete_record": {
        "name": "snow_delete_record",
        "description": "Delete a record from a ServiceNow table by sys_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "sys_id": {"type": "string", "description": "The record sys_id"},
            },
            "required": ["table", "sys_id"],
        },
    },
    "snow_search_incidents": {
        "name": "snow_search_incidents",
        "description": (
            "Search incidents with convenience filters for state, priority, assigned_to, "
            "and short_description (contains match)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Incident state (1=New, 2=In Progress, 3=On Hold, 6=Resolved, 7=Closed)"},
                "priority": {"type": "string", "description": "Priority (1=Critical, 2=High, 3=Moderate, 4=Low, 5=Planning)"},
                "assigned_to": {"type": "string", "description": "Assigned to user (sys_id or display name)"},
                "short_description": {"type": "string", "description": "Search text (LIKE match on short_description)"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "snow_create_incident": {
        "name": "snow_create_incident",
        "description": "Create an incident in ServiceNow with standard ITIL fields.",
        "parameters": {
            "type": "object",
            "properties": {
                "short_description": {"type": "string", "description": "Brief summary of the incident"},
                "description": {"type": "string", "description": "Detailed description"},
                "priority": {"type": "string", "description": "Priority (1-5, default 3)"},
                "urgency": {"type": "string", "description": "Urgency (1-3, default 2)"},
                "category": {"type": "string", "description": "Category (e.g. Software, Hardware, Network)"},
                "assigned_to": {"type": "string", "description": "Assign to user (sys_id or name)"},
            },
            "required": ["short_description"],
        },
    },
    "snow_resolve_incident": {
        "name": "snow_resolve_incident",
        "description": "Resolve an incident by setting state=6 (Resolved) with close code and notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "sys_id": {"type": "string", "description": "The incident sys_id"},
                "close_code": {"type": "string", "description": "Close code (default: 'Solved (Permanently)')"},
                "close_notes": {"type": "string", "description": "Resolution notes"},
            },
            "required": ["sys_id"],
        },
    },
    "snow_search_changes": {
        "name": "snow_search_changes",
        "description": "Search change requests with filters for state, priority, assigned_to, and type.",
        "parameters": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Change state (-5=New, -4=Assess, -3=Authorize, -2=Scheduled, -1=Implement, 0=Review, 3=Closed, 4=Canceled)"},
                "priority": {"type": "string", "description": "Priority (1-5)"},
                "assigned_to": {"type": "string", "description": "Assigned to user"},
                "type": {"type": "string", "description": "Change type (Normal, Standard, Emergency)"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "snow_get_cmdb_ci": {
        "name": "snow_get_cmdb_ci",
        "description": "Get a CMDB Configuration Item by sys_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "sys_id": {"type": "string", "description": "The CI sys_id"},
            },
            "required": ["sys_id"],
        },
    },
    "snow_search_cmdb": {
        "name": "snow_search_cmdb",
        "description": "Search CMDB Configuration Items with an encoded query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Encoded query (e.g. 'nameLIKEserver^operational_status=1')"},
                "fields": {"type": "string", "description": "Comma-separated fields (default: name,sys_id,sys_class_name,operational_status)"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "snow_list_tables": {
        "name": "snow_list_tables",
        "description": "List available ServiceNow tables (from sys_db_object).",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max tables to return (default 50)"},
            },
            "required": [],
        },
    },
    "snow_run_script": {
        "name": "snow_run_script",
        "description": (
            "Run a server-side script by creating a Script Include in ServiceNow. "
            "Useful for GlideRecord operations and automation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "The server-side JavaScript/GlideScript code to run"},
                "name": {"type": "string", "description": "Name for the script include (default: ArtemisScript)"},
            },
            "required": ["script"],
        },
    },
}

# Map names to functions
_HANDLERS = {
    "snow_connect": snow_connect,
    "snow_status": snow_status,
    "snow_query": snow_query,
    "snow_get_record": snow_get_record,
    "snow_create_record": snow_create_record,
    "snow_update_record": snow_update_record,
    "snow_delete_record": snow_delete_record,
    "snow_search_incidents": snow_search_incidents,
    "snow_create_incident": snow_create_incident,
    "snow_resolve_incident": snow_resolve_incident,
    "snow_search_changes": snow_search_changes,
    "snow_get_cmdb_ci": snow_get_cmdb_ci,
    "snow_search_cmdb": snow_search_cmdb,
    "snow_list_tables": snow_list_tables,
    "snow_run_script": snow_run_script,
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_servicenow_tools(registry):
    """Register all 15 ServiceNow tools with a ToolRegistry."""
    for name, handler in _HANDLERS.items():
        registry.register(name, handler, _SCHEMAS[name])
