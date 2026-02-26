"""
Jira Tools
==========
Artemis Atlassian Jira Cloud connector — deep project and issue management.
OAuth2-free Basic Auth (email + API token), JQL search, issue CRUD,
transitions, comments, sprints, boards, and user search.

Install: pip install artemis-connectors
Auto-discovered by solstice-agent via entry_points.
"""

import base64
import json
import logging
from typing import Any, Dict, Optional

log = logging.getLogger("artemis.connectors.jira")

# ---------------------------------------------------------------------------
# Module-level connection state
# ---------------------------------------------------------------------------
_client = None           # httpx.Client (sync)
_base_url: str = ""
_auth_header: Optional[str] = None  # "Basic base64(email:token)"


def _require_connection() -> bool:
    return _client is not None


def _api(method: str, path: str, json_body=None, params=None) -> Dict[str, Any]:
    """Central API request handler with Basic Auth."""
    if not _require_connection():
        raise RuntimeError("Not connected. Run jira_connect first.")

    url = f"{_base_url}{path}"
    headers = {"Authorization": _auth_header, "Accept": "application/json"}
    kwargs: Dict[str, Any] = {"headers": headers}
    if json_body is not None:
        kwargs["json"] = json_body
    if params is not None:
        kwargs["params"] = params

    resp = _client.request(method, url, **kwargs)
    resp.raise_for_status()

    if resp.status_code == 204 or not resp.content:
        return {"success": True}
    return resp.json()


def _fmt(data: Any) -> str:
    if isinstance(data, dict):
        return json.dumps(data, indent=2, default=str)
    return str(data)


def _make_adf_text(text: str) -> Dict[str, Any]:
    """Convert plain text to minimal Atlassian Document Format (ADF)."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": text}
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tool 1: jira_connect
# ---------------------------------------------------------------------------
def jira_connect(base_url: str, email: str, api_token: str) -> str:
    """Authenticate with Jira Cloud using Basic Auth (email + API token)."""
    global _client, _base_url, _auth_header

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

    _base_url = base_url.rstrip("/")
    creds = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    _auth_header = f"Basic {creds}"

    try:
        _client = httpx.Client(timeout=30.0)
        headers = {"Authorization": _auth_header, "Accept": "application/json"}
        resp = _client.get(f"{_base_url}/rest/api/3/myself", headers=headers)
        resp.raise_for_status()
        user = resp.json()
        display = user.get("displayName", user.get("emailAddress", "unknown"))
        account_id = user.get("accountId", "?")
        return (
            f"Connected to Jira Cloud ({_base_url}).\n"
            f"  Authenticated as: {display} (accountId: {account_id})"
        )
    except Exception as e:
        _client = None
        _auth_header = None
        _base_url = ""
        return f"Connection failed: {e}"


# ---------------------------------------------------------------------------
# Tool 2: jira_status
# ---------------------------------------------------------------------------
def jira_status() -> str:
    """Get Jira server info and current user."""
    try:
        server = _api("GET", "/rest/api/3/serverInfo")
        myself = _api("GET", "/rest/api/3/myself")
        return (
            f"Server: {server.get('serverTitle', '?')} ({server.get('baseUrl', '?')})\n"
            f"  Version: {server.get('version', '?')}, Build: {server.get('buildNumber', '?')}\n"
            f"  Deployment: {server.get('deploymentType', '?')}\n"
            f"User: {myself.get('displayName', '?')} ({myself.get('emailAddress', '?')})\n"
            f"  Account ID: {myself.get('accountId', '?')}"
        )
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool 3: jira_search
# ---------------------------------------------------------------------------
def jira_search(jql: str, max_results: int = 20) -> str:
    """Search Jira issues using JQL."""
    try:
        body = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "priority", "issuetype"],
        }
        result = _api("POST", "/rest/api/3/search", json_body=body)
        issues = result.get("issues", [])
        lines = [f"Found {result.get('total', len(issues))} issue(s) (showing {len(issues)}):"]
        for issue in issues:
            key = issue.get("key", "?")
            fields = issue.get("fields", {})
            summary = fields.get("summary", "")
            status = fields.get("status", {}).get("name", "?")
            assignee = fields.get("assignee")
            assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
            lines.append(f"  [{key}] {summary} — {status} ({assignee_name})")
        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


# ---------------------------------------------------------------------------
# Tool 4: jira_get_issue
# ---------------------------------------------------------------------------
def jira_get_issue(issue_key: str) -> str:
    """Get a single Jira issue by key."""
    try:
        fields = "summary,status,assignee,priority,description,created,updated,issuetype,project"
        result = _api("GET", f"/rest/api/3/issue/{issue_key}", params={"fields": fields})
        f = result.get("fields", {})
        assignee = f.get("assignee")
        assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
        priority = f.get("priority")
        priority_name = priority.get("name", "None") if priority else "None"
        project = f.get("project", {})
        issuetype = f.get("issuetype", {})
        lines = [
            f"Issue: {result.get('key', '?')}",
            f"  Summary: {f.get('summary', '')}",
            f"  Type: {issuetype.get('name', '?')}",
            f"  Status: {f.get('status', {}).get('name', '?')}",
            f"  Priority: {priority_name}",
            f"  Assignee: {assignee_name}",
            f"  Project: {project.get('name', '?')} ({project.get('key', '?')})",
            f"  Created: {f.get('created', '?')}",
            f"  Updated: {f.get('updated', '?')}",
        ]
        desc = f.get("description")
        if desc:
            lines.append(f"  Description: {json.dumps(desc, default=str)[:500]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Get issue failed: {e}"


# ---------------------------------------------------------------------------
# Tool 5: jira_create_issue
# ---------------------------------------------------------------------------
def jira_create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
    priority: str = "",
    assignee_account_id: str = "",
) -> str:
    """Create a new Jira issue."""
    try:
        fields: Dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description:
            fields["description"] = _make_adf_text(description)
        if priority:
            fields["priority"] = {"name": priority}
        if assignee_account_id:
            fields["assignee"] = {"accountId": assignee_account_id}

        result = _api("POST", "/rest/api/3/issue", json_body={"fields": fields})
        key = result.get("key", "?")
        issue_id = result.get("id", "?")
        return f"Issue created: {key} (id: {issue_id})\n  URL: {_base_url}/browse/{key}"
    except Exception as e:
        return f"Create issue failed: {e}"


# ---------------------------------------------------------------------------
# Tool 6: jira_update_issue
# ---------------------------------------------------------------------------
def jira_update_issue(issue_key: str, fields_json: str) -> str:
    """Update an existing Jira issue. Pass fields as a JSON string."""
    try:
        fields = json.loads(fields_json)
        _api("PUT", f"/rest/api/3/issue/{issue_key}", json_body={"fields": fields})
        return f"Issue {issue_key} updated."
    except json.JSONDecodeError:
        return "Error: 'fields_json' must be valid JSON"
    except Exception as e:
        return f"Update issue failed: {e}"


# ---------------------------------------------------------------------------
# Tool 7: jira_transition_issue
# ---------------------------------------------------------------------------
def jira_transition_issue(issue_key: str, status_name: str) -> str:
    """Transition an issue to a new status by name."""
    try:
        # Get available transitions
        result = _api("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        transitions = result.get("transitions", [])
        if not transitions:
            return f"No transitions available for {issue_key}."

        # Match by name (case-insensitive)
        match = None
        for t in transitions:
            if t.get("name", "").lower() == status_name.lower():
                match = t
                break

        if not match:
            available = [t.get("name", "?") for t in transitions]
            return f"Transition '{status_name}' not found. Available: {', '.join(available)}"

        _api("POST", f"/rest/api/3/issue/{issue_key}/transitions", json_body={
            "transition": {"id": match["id"]}
        })
        return f"Issue {issue_key} transitioned to '{match['name']}'."
    except Exception as e:
        return f"Transition failed: {e}"


# ---------------------------------------------------------------------------
# Tool 8: jira_add_comment
# ---------------------------------------------------------------------------
def jira_add_comment(issue_key: str, body_text: str) -> str:
    """Add a comment to a Jira issue."""
    try:
        result = _api("POST", f"/rest/api/3/issue/{issue_key}/comment", json_body={
            "body": _make_adf_text(body_text)
        })
        comment_id = result.get("id", "?")
        return f"Comment added to {issue_key} (comment id: {comment_id})."
    except Exception as e:
        return f"Add comment failed: {e}"


# ---------------------------------------------------------------------------
# Tool 9: jira_assign_issue
# ---------------------------------------------------------------------------
def jira_assign_issue(issue_key: str, account_id: str) -> str:
    """Assign an issue to a user by account ID."""
    try:
        _api("PUT", f"/rest/api/3/issue/{issue_key}/assignee", json_body={
            "accountId": account_id
        })
        return f"Issue {issue_key} assigned to account {account_id}."
    except Exception as e:
        return f"Assign issue failed: {e}"


# ---------------------------------------------------------------------------
# Tool 10: jira_list_projects
# ---------------------------------------------------------------------------
def jira_list_projects() -> str:
    """List all Jira projects."""
    try:
        result = _api("GET", "/rest/api/3/project", params={"maxResults": 50})
        if isinstance(result, list):
            projects = result
        else:
            projects = result.get("values", result.get("projects", []))
        lines = [f"Found {len(projects)} project(s):"]
        for p in projects:
            lines.append(f"  [{p.get('key', '?')}] {p.get('name', '?')} (id: {p.get('id', '?')})")
        return "\n".join(lines)
    except Exception as e:
        return f"List projects failed: {e}"


# ---------------------------------------------------------------------------
# Tool 11: jira_get_project
# ---------------------------------------------------------------------------
def jira_get_project(project_key: str) -> str:
    """Get details for a specific project."""
    try:
        result = _api("GET", f"/rest/api/3/project/{project_key}")
        lead = result.get("lead", {})
        lines = [
            f"Project: {result.get('name', '?')} ({result.get('key', '?')})",
            f"  ID: {result.get('id', '?')}",
            f"  Type: {result.get('projectTypeKey', '?')}",
            f"  Lead: {lead.get('displayName', '?')}",
            f"  Style: {result.get('style', '?')}",
        ]
        components = result.get("components", [])
        if components:
            names = [c.get("name", "?") for c in components]
            lines.append(f"  Components: {', '.join(names)}")
        return "\n".join(lines)
    except Exception as e:
        return f"Get project failed: {e}"


# ---------------------------------------------------------------------------
# Tool 12: jira_list_boards
# ---------------------------------------------------------------------------
def jira_list_boards(project_key: str = "") -> str:
    """List agile boards, optionally filtered by project."""
    try:
        params = {"maxResults": 50}
        if project_key:
            params["projectKeyOrId"] = project_key
        result = _api("GET", "/rest/agile/1.0/board", params=params)
        boards = result.get("values", [])
        lines = [f"Found {len(boards)} board(s):"]
        for b in boards:
            lines.append(f"  [{b.get('id', '?')}] {b.get('name', '?')} ({b.get('type', '?')})")
        return "\n".join(lines)
    except Exception as e:
        return f"List boards failed: {e}"


# ---------------------------------------------------------------------------
# Tool 13: jira_get_sprint
# ---------------------------------------------------------------------------
def jira_get_sprint(sprint_id: int) -> str:
    """Get details for a specific sprint."""
    try:
        result = _api("GET", f"/rest/agile/1.0/sprint/{sprint_id}")
        lines = [
            f"Sprint: {result.get('name', '?')} (id: {result.get('id', '?')})",
            f"  State: {result.get('state', '?')}",
            f"  Start: {result.get('startDate', 'N/A')}",
            f"  End: {result.get('endDate', 'N/A')}",
            f"  Goal: {result.get('goal', 'N/A')}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Get sprint failed: {e}"


# ---------------------------------------------------------------------------
# Tool 14: jira_sprint_issues
# ---------------------------------------------------------------------------
def jira_sprint_issues(sprint_id: int, max_results: int = 50) -> str:
    """Get issues in a sprint."""
    try:
        result = _api("GET", f"/rest/agile/1.0/sprint/{sprint_id}/issue",
                       params={"maxResults": max_results})
        issues = result.get("issues", [])
        lines = [f"Sprint {sprint_id} — {len(issues)} issue(s):"]
        for issue in issues:
            key = issue.get("key", "?")
            fields = issue.get("fields", {})
            summary = fields.get("summary", "")
            status = fields.get("status", {}).get("name", "?")
            assignee = fields.get("assignee")
            assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
            lines.append(f"  [{key}] {summary} — {status} ({assignee_name})")
        return "\n".join(lines)
    except Exception as e:
        return f"Sprint issues failed: {e}"


# ---------------------------------------------------------------------------
# Tool 15: jira_search_users
# ---------------------------------------------------------------------------
def jira_search_users(query: str, max_results: int = 10) -> str:
    """Search for Jira users by name or email."""
    try:
        result = _api("GET", "/rest/api/3/user/search",
                       params={"query": query, "maxResults": max_results})
        if isinstance(result, list):
            users = result
        else:
            users = result.get("users", [])
        lines = [f"Found {len(users)} user(s):"]
        for u in users:
            lines.append(
                f"  {u.get('displayName', '?')} — {u.get('emailAddress', 'N/A')} "
                f"(accountId: {u.get('accountId', '?')})"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Search users failed: {e}"


# ---------------------------------------------------------------------------
# Schemas (OpenAI function-calling format — lowercase "object")
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "jira_connect": {
        "name": "jira_connect",
        "description": (
            "Connect to Jira Cloud using Basic Auth (email + API token). "
            "This is an Artemis connector — run this first to unlock all jira_* tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "Jira Cloud URL (e.g. https://myteam.atlassian.net)"},
                "email": {"type": "string", "description": "Atlassian account email"},
                "api_token": {"type": "string", "description": "Atlassian API token"},
            },
            "required": ["base_url", "email", "api_token"],
        },
    },
    "jira_status": {
        "name": "jira_status",
        "description": "Get Jira server info (version, deployment type) and current authenticated user.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "jira_search": {
        "name": "jira_search",
        "description": "Search Jira issues using JQL (Jira Query Language). Returns key, summary, status, assignee.",
        "parameters": {
            "type": "object",
            "properties": {
                "jql": {"type": "string", "description": "JQL query string (e.g. 'project = PROJ AND status = Open')"},
                "max_results": {"type": "integer", "description": "Maximum results to return (default 20)"},
            },
            "required": ["jql"],
        },
    },
    "jira_get_issue": {
        "name": "jira_get_issue",
        "description": "Get full details for a single Jira issue by key (e.g. PROJ-123).",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)"},
            },
            "required": ["issue_key"],
        },
    },
    "jira_create_issue": {
        "name": "jira_create_issue",
        "description": "Create a new Jira issue with summary, type, description, priority, and assignee.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_key": {"type": "string", "description": "Project key (e.g. PROJ)"},
                "summary": {"type": "string", "description": "Issue summary/title"},
                "issue_type": {"type": "string", "description": "Issue type (e.g. Task, Bug, Story). Default: Task"},
                "description": {"type": "string", "description": "Issue description (plain text, converted to ADF)"},
                "priority": {"type": "string", "description": "Priority name (e.g. High, Medium, Low)"},
                "assignee_account_id": {"type": "string", "description": "Assignee Atlassian account ID"},
            },
            "required": ["project_key", "summary"],
        },
    },
    "jira_update_issue": {
        "name": "jira_update_issue",
        "description": "Update fields on an existing Jira issue. Pass fields as a JSON string.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)"},
                "fields_json": {"type": "string", "description": "JSON string of fields to update (e.g. '{\"summary\": \"New title\"}')"},
            },
            "required": ["issue_key", "fields_json"],
        },
    },
    "jira_transition_issue": {
        "name": "jira_transition_issue",
        "description": "Transition an issue to a new status by name (e.g. 'In Progress', 'Done').",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)"},
                "status_name": {"type": "string", "description": "Target status name (e.g. 'In Progress', 'Done')"},
            },
            "required": ["issue_key", "status_name"],
        },
    },
    "jira_add_comment": {
        "name": "jira_add_comment",
        "description": "Add a comment to a Jira issue. Text is converted to ADF format.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)"},
                "body_text": {"type": "string", "description": "Comment text (plain text)"},
            },
            "required": ["issue_key", "body_text"],
        },
    },
    "jira_assign_issue": {
        "name": "jira_assign_issue",
        "description": "Assign a Jira issue to a user by Atlassian account ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)"},
                "account_id": {"type": "string", "description": "Atlassian account ID of the assignee"},
            },
            "required": ["issue_key", "account_id"],
        },
    },
    "jira_list_projects": {
        "name": "jira_list_projects",
        "description": "List all accessible Jira projects with key, name, and ID.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "jira_get_project": {
        "name": "jira_get_project",
        "description": "Get detailed info for a specific Jira project by key.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_key": {"type": "string", "description": "Project key (e.g. PROJ)"},
            },
            "required": ["project_key"],
        },
    },
    "jira_list_boards": {
        "name": "jira_list_boards",
        "description": "List agile boards (Scrum/Kanban), optionally filtered by project.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_key": {"type": "string", "description": "Optional project key to filter boards"},
            },
            "required": [],
        },
    },
    "jira_get_sprint": {
        "name": "jira_get_sprint",
        "description": "Get details for a specific sprint (name, state, dates, goal).",
        "parameters": {
            "type": "object",
            "properties": {
                "sprint_id": {"type": "integer", "description": "Sprint ID"},
            },
            "required": ["sprint_id"],
        },
    },
    "jira_sprint_issues": {
        "name": "jira_sprint_issues",
        "description": "Get all issues in a specific sprint.",
        "parameters": {
            "type": "object",
            "properties": {
                "sprint_id": {"type": "integer", "description": "Sprint ID"},
                "max_results": {"type": "integer", "description": "Maximum results (default 50)"},
            },
            "required": ["sprint_id"],
        },
    },
    "jira_search_users": {
        "name": "jira_search_users",
        "description": "Search for Jira users by name or email to find account IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (name or email)"},
                "max_results": {"type": "integer", "description": "Maximum results (default 10)"},
            },
            "required": ["query"],
        },
    },
}

# Map names to functions
_HANDLERS = {
    "jira_connect": jira_connect,
    "jira_status": jira_status,
    "jira_search": jira_search,
    "jira_get_issue": jira_get_issue,
    "jira_create_issue": jira_create_issue,
    "jira_update_issue": jira_update_issue,
    "jira_transition_issue": jira_transition_issue,
    "jira_add_comment": jira_add_comment,
    "jira_assign_issue": jira_assign_issue,
    "jira_list_projects": jira_list_projects,
    "jira_get_project": jira_get_project,
    "jira_list_boards": jira_list_boards,
    "jira_get_sprint": jira_get_sprint,
    "jira_sprint_issues": jira_sprint_issues,
    "jira_search_users": jira_search_users,
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_jira_tools(registry):
    """Register all 15 Jira tools with a ToolRegistry."""
    for name, handler in _HANDLERS.items():
        registry.register(name, handler, _SCHEMAS[name])
