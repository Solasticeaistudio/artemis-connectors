"""
HubSpot Tools
=============
Artemis HubSpot CRM connector — contacts, deals, companies, pipelines, notes.
Full CRM lifecycle via HubSpot API v3 (https://api.hubapi.com).

Install: pip install artemis-connectors
Auto-discovered by solstice-agent via entry_points.
"""

import json
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("artemis.connectors.hubspot")

# ---------------------------------------------------------------------------
# Module-level connection state
# ---------------------------------------------------------------------------
_client = None           # httpx.Client (sync)
_base_url: str = "https://api.hubapi.com"
_access_token: Optional[str] = None


def _require_connection() -> bool:
    return _client is not None


def _api(method: str, path: str, json_body=None) -> Dict[str, Any]:
    """Central API request handler with Bearer auth."""
    if not _require_connection():
        raise RuntimeError("Not connected. Run hs_connect first.")

    headers = {"Authorization": f"Bearer {_access_token}"}
    url = f"{_base_url}{path}"

    kwargs: Dict[str, Any] = {"headers": headers}
    if json_body is not None:
        kwargs["json"] = json_body

    resp = _client.request(method, url, **kwargs)
    resp.raise_for_status()
    if resp.status_code == 204:
        return {"success": True}
    return resp.json()


def _fmt(data: Any) -> str:
    if isinstance(data, dict):
        return json.dumps(data, indent=2, default=str)
    return str(data)


# ---------------------------------------------------------------------------
# Tool 1: hs_connect
# ---------------------------------------------------------------------------
def hs_connect(
    api_key: str = "",
    oauth_token: str = "",
) -> str:
    """Authenticate with HubSpot using a private app token or OAuth token."""
    global _client, _access_token

    try:
        import httpx
    except ImportError:
        return "Error: httpx required. Install with: pip install httpx"

    token = api_key or oauth_token
    if not token:
        return "Error: provide either api_key (private app token) or oauth_token."

    # Close existing
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass

    try:
        _client = httpx.Client(timeout=30.0)
        _access_token = token

        # Test with a minimal contacts query
        result = _api("GET", "/crm/v3/objects/contacts?limit=1")
        total = result.get("total", 0)
        return (
            f"Connected to HubSpot ({_base_url}).\n"
            f"  Auth: {'Private App' if api_key else 'OAuth'}\n"
            f"  Contacts in portal: {total}"
        )
    except Exception as e:
        _client = None
        _access_token = None
        return f"Connection failed: {e}"


# ---------------------------------------------------------------------------
# Tool 2: hs_status
# ---------------------------------------------------------------------------
def hs_status() -> str:
    """Get HubSpot account info and API usage."""
    try:
        usage = _api("GET", "/account-info/v3/api-usage/daily/private-app")
        details = _api("GET", "/account-info/v3/details")
        return (
            f"Account Details:\n{_fmt(details)}\n\n"
            f"API Usage:\n{_fmt(usage)}"
        )
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool 3: hs_search_contacts
# ---------------------------------------------------------------------------
def hs_search_contacts(
    query: str = "",
    filter_property: str = "",
    filter_operator: str = "EQ",
    filter_value: str = "",
    properties: str = "email,firstname,lastname,phone,company",
    limit: int = 20,
) -> str:
    """Search contacts with filters or free-text query."""
    try:
        body: Dict[str, Any] = {"limit": limit}
        if properties:
            body["properties"] = [p.strip() for p in properties.split(",")]

        if query:
            body["query"] = query
        elif filter_property and filter_value:
            body["filterGroups"] = [{
                "filters": [{
                    "propertyName": filter_property,
                    "operator": filter_operator,
                    "value": filter_value,
                }]
            }]

        result = _api("POST", "/crm/v3/objects/contacts/search", json_body=body)
        total = result.get("total", 0)
        items = result.get("results", [])
        return f"Found {total} contact(s) ({len(items)} returned).\n{_fmt(result)}"
    except Exception as e:
        return f"Search contacts failed: {e}"


# ---------------------------------------------------------------------------
# Tool 4: hs_get_contact
# ---------------------------------------------------------------------------
def hs_get_contact(contact_id: str) -> str:
    """Get a contact by ID with standard properties."""
    try:
        result = _api("GET", f"/crm/v3/objects/contacts/{contact_id}?properties=email,firstname,lastname,phone,company")
        return _fmt(result)
    except Exception as e:
        return f"Get contact failed: {e}"


# ---------------------------------------------------------------------------
# Tool 5: hs_create_contact
# ---------------------------------------------------------------------------
def hs_create_contact(properties: str) -> str:
    """Create a contact. properties is a JSON string like {\"email\":\"a@b.com\",\"firstname\":\"Al\"}."""
    try:
        props = json.loads(properties)
        result = _api("POST", "/crm/v3/objects/contacts", json_body={"properties": props})
        cid = result.get("id", "?")
        return f"Contact created. ID: {cid}\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'properties' must be valid JSON"
    except Exception as e:
        return f"Create contact failed: {e}"


# ---------------------------------------------------------------------------
# Tool 6: hs_update_contact
# ---------------------------------------------------------------------------
def hs_update_contact(contact_id: str, properties: str) -> str:
    """Update a contact by ID. properties is a JSON string of fields to update."""
    try:
        props = json.loads(properties)
        result = _api("PATCH", f"/crm/v3/objects/contacts/{contact_id}", json_body={"properties": props})
        return f"Contact {contact_id} updated.\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'properties' must be valid JSON"
    except Exception as e:
        return f"Update contact failed: {e}"


# ---------------------------------------------------------------------------
# Tool 7: hs_search_deals
# ---------------------------------------------------------------------------
def hs_search_deals(
    query: str = "",
    filter_property: str = "",
    filter_operator: str = "EQ",
    filter_value: str = "",
    properties: str = "dealname,amount,dealstage,pipeline,closedate",
    limit: int = 20,
) -> str:
    """Search deals with filters or free-text query."""
    try:
        body: Dict[str, Any] = {"limit": limit}
        if properties:
            body["properties"] = [p.strip() for p in properties.split(",")]

        if query:
            body["query"] = query
        elif filter_property and filter_value:
            body["filterGroups"] = [{
                "filters": [{
                    "propertyName": filter_property,
                    "operator": filter_operator,
                    "value": filter_value,
                }]
            }]

        result = _api("POST", "/crm/v3/objects/deals/search", json_body=body)
        total = result.get("total", 0)
        items = result.get("results", [])
        return f"Found {total} deal(s) ({len(items)} returned).\n{_fmt(result)}"
    except Exception as e:
        return f"Search deals failed: {e}"


# ---------------------------------------------------------------------------
# Tool 8: hs_get_deal
# ---------------------------------------------------------------------------
def hs_get_deal(deal_id: str) -> str:
    """Get a deal by ID with standard properties."""
    try:
        result = _api("GET", f"/crm/v3/objects/deals/{deal_id}?properties=dealname,amount,dealstage,pipeline,closedate")
        return _fmt(result)
    except Exception as e:
        return f"Get deal failed: {e}"


# ---------------------------------------------------------------------------
# Tool 9: hs_create_deal
# ---------------------------------------------------------------------------
def hs_create_deal(properties: str) -> str:
    """Create a deal. properties is a JSON string like {\"dealname\":\"Big Deal\",\"amount\":\"50000\"}."""
    try:
        props = json.loads(properties)
        result = _api("POST", "/crm/v3/objects/deals", json_body={"properties": props})
        did = result.get("id", "?")
        return f"Deal created. ID: {did}\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'properties' must be valid JSON"
    except Exception as e:
        return f"Create deal failed: {e}"


# ---------------------------------------------------------------------------
# Tool 10: hs_update_deal
# ---------------------------------------------------------------------------
def hs_update_deal(deal_id: str, properties: str) -> str:
    """Update a deal by ID. properties is a JSON string of fields to update."""
    try:
        props = json.loads(properties)
        result = _api("PATCH", f"/crm/v3/objects/deals/{deal_id}", json_body={"properties": props})
        return f"Deal {deal_id} updated.\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'properties' must be valid JSON"
    except Exception as e:
        return f"Update deal failed: {e}"


# ---------------------------------------------------------------------------
# Tool 11: hs_search_companies
# ---------------------------------------------------------------------------
def hs_search_companies(
    query: str = "",
    filter_property: str = "",
    filter_operator: str = "EQ",
    filter_value: str = "",
    properties: str = "name,domain,industry,city,state,phone",
    limit: int = 20,
) -> str:
    """Search companies with filters or free-text query."""
    try:
        body: Dict[str, Any] = {"limit": limit}
        if properties:
            body["properties"] = [p.strip() for p in properties.split(",")]

        if query:
            body["query"] = query
        elif filter_property and filter_value:
            body["filterGroups"] = [{
                "filters": [{
                    "propertyName": filter_property,
                    "operator": filter_operator,
                    "value": filter_value,
                }]
            }]

        result = _api("POST", "/crm/v3/objects/companies/search", json_body=body)
        total = result.get("total", 0)
        items = result.get("results", [])
        return f"Found {total} company(ies) ({len(items)} returned).\n{_fmt(result)}"
    except Exception as e:
        return f"Search companies failed: {e}"


# ---------------------------------------------------------------------------
# Tool 12: hs_get_company
# ---------------------------------------------------------------------------
def hs_get_company(company_id: str) -> str:
    """Get a company by ID."""
    try:
        result = _api("GET", f"/crm/v3/objects/companies/{company_id}")
        return _fmt(result)
    except Exception as e:
        return f"Get company failed: {e}"


# ---------------------------------------------------------------------------
# Tool 13: hs_create_company
# ---------------------------------------------------------------------------
def hs_create_company(properties: str) -> str:
    """Create a company. properties is a JSON string like {\"name\":\"Acme Inc\",\"domain\":\"acme.com\"}."""
    try:
        props = json.loads(properties)
        result = _api("POST", "/crm/v3/objects/companies", json_body={"properties": props})
        cid = result.get("id", "?")
        return f"Company created. ID: {cid}\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'properties' must be valid JSON"
    except Exception as e:
        return f"Create company failed: {e}"


# ---------------------------------------------------------------------------
# Tool 14: hs_list_pipelines
# ---------------------------------------------------------------------------
def hs_list_pipelines() -> str:
    """List all deal pipelines and their stages."""
    try:
        result = _api("GET", "/crm/v3/pipelines/deals")
        pipelines = result.get("results", [])
        lines = [f"Found {len(pipelines)} pipeline(s)."]
        for p in pipelines:
            lines.append(f"\n  Pipeline: {p.get('label', '?')} (ID: {p.get('id', '?')})")
            for stage in p.get("stages", []):
                lines.append(f"    Stage: {stage.get('label', '?')} (ID: {stage.get('id', '?')})")
        return "\n".join(lines)
    except Exception as e:
        return f"List pipelines failed: {e}"


# ---------------------------------------------------------------------------
# Tool 15: hs_create_note
# ---------------------------------------------------------------------------
def hs_create_note(
    body: str,
    contact_id: str = "",
    deal_id: str = "",
    company_id: str = "",
) -> str:
    """Create an engagement note, optionally associated with a contact, deal, or company."""
    try:
        payload: Dict[str, Any] = {
            "properties": {
                "hs_note_body": body,
                "hs_timestamp": str(int(__import__("time").time() * 1000)),
            },
        }

        associations = []
        if contact_id:
            associations.append({
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}],
            })
        if deal_id:
            associations.append({
                "to": {"id": deal_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 214}],
            })
        if company_id:
            associations.append({
                "to": {"id": company_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 190}],
            })
        if associations:
            payload["associations"] = associations

        result = _api("POST", "/crm/v3/objects/notes", json_body=payload)
        nid = result.get("id", "?")
        return f"Note created. ID: {nid}\n{_fmt(result)}"
    except Exception as e:
        return f"Create note failed: {e}"


# ---------------------------------------------------------------------------
# Schemas (OpenAI function-calling format — lowercase "object")
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "hs_connect": {
        "name": "hs_connect",
        "description": (
            "Authenticate with HubSpot using a private app token or OAuth token. "
            "This is an Artemis premium connector — run this first to unlock all hs_* tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "HubSpot private app access token"},
                "oauth_token": {"type": "string", "description": "HubSpot OAuth2 access token"},
            },
            "required": [],
        },
    },
    "hs_status": {
        "name": "hs_status",
        "description": "Get HubSpot account details and daily API usage for private apps.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "hs_search_contacts": {
        "name": "hs_search_contacts",
        "description": "Search HubSpot contacts by free-text query or property filter.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search query"},
                "filter_property": {"type": "string", "description": "Property name to filter (e.g. email, company)"},
                "filter_operator": {"type": "string", "description": "Filter operator (EQ, NEQ, LT, GT, CONTAINS, etc.)", "enum": ["EQ", "NEQ", "LT", "LTE", "GT", "GTE", "CONTAINS", "NOT_CONTAINS"]},
                "filter_value": {"type": "string", "description": "Value to filter against"},
                "properties": {"type": "string", "description": "Comma-separated property names to return"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "hs_get_contact": {
        "name": "hs_get_contact",
        "description": "Get a HubSpot contact by ID with standard properties (email, name, phone, company).",
        "parameters": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "The contact ID"},
            },
            "required": ["contact_id"],
        },
    },
    "hs_create_contact": {
        "name": "hs_create_contact",
        "description": "Create a new HubSpot contact with the given properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "properties": {"type": "string", "description": "JSON string of contact properties (e.g. {\"email\":\"a@b.com\",\"firstname\":\"Al\"})"},
            },
            "required": ["properties"],
        },
    },
    "hs_update_contact": {
        "name": "hs_update_contact",
        "description": "Update an existing HubSpot contact by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "The contact ID to update"},
                "properties": {"type": "string", "description": "JSON string of properties to update"},
            },
            "required": ["contact_id", "properties"],
        },
    },
    "hs_search_deals": {
        "name": "hs_search_deals",
        "description": "Search HubSpot deals by free-text query or property filter.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search query"},
                "filter_property": {"type": "string", "description": "Property name to filter (e.g. dealstage, amount)"},
                "filter_operator": {"type": "string", "description": "Filter operator", "enum": ["EQ", "NEQ", "LT", "LTE", "GT", "GTE", "CONTAINS", "NOT_CONTAINS"]},
                "filter_value": {"type": "string", "description": "Value to filter against"},
                "properties": {"type": "string", "description": "Comma-separated property names to return"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "hs_get_deal": {
        "name": "hs_get_deal",
        "description": "Get a HubSpot deal by ID with standard properties (name, amount, stage, pipeline, close date).",
        "parameters": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "The deal ID"},
            },
            "required": ["deal_id"],
        },
    },
    "hs_create_deal": {
        "name": "hs_create_deal",
        "description": "Create a new HubSpot deal with the given properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "properties": {"type": "string", "description": "JSON string of deal properties (e.g. {\"dealname\":\"Big Deal\",\"amount\":\"50000\"})"},
            },
            "required": ["properties"],
        },
    },
    "hs_update_deal": {
        "name": "hs_update_deal",
        "description": "Update an existing HubSpot deal by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "The deal ID to update"},
                "properties": {"type": "string", "description": "JSON string of properties to update"},
            },
            "required": ["deal_id", "properties"],
        },
    },
    "hs_search_companies": {
        "name": "hs_search_companies",
        "description": "Search HubSpot companies by free-text query or property filter.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search query"},
                "filter_property": {"type": "string", "description": "Property name to filter (e.g. domain, industry)"},
                "filter_operator": {"type": "string", "description": "Filter operator", "enum": ["EQ", "NEQ", "LT", "LTE", "GT", "GTE", "CONTAINS", "NOT_CONTAINS"]},
                "filter_value": {"type": "string", "description": "Value to filter against"},
                "properties": {"type": "string", "description": "Comma-separated property names to return"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "hs_get_company": {
        "name": "hs_get_company",
        "description": "Get a HubSpot company by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_id": {"type": "string", "description": "The company ID"},
            },
            "required": ["company_id"],
        },
    },
    "hs_create_company": {
        "name": "hs_create_company",
        "description": "Create a new HubSpot company with the given properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "properties": {"type": "string", "description": "JSON string of company properties (e.g. {\"name\":\"Acme Inc\",\"domain\":\"acme.com\"})"},
            },
            "required": ["properties"],
        },
    },
    "hs_list_pipelines": {
        "name": "hs_list_pipelines",
        "description": "List all HubSpot deal pipelines and their stages.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "hs_create_note": {
        "name": "hs_create_note",
        "description": "Create an engagement note in HubSpot, optionally associated with a contact, deal, or company.",
        "parameters": {
            "type": "object",
            "properties": {
                "body": {"type": "string", "description": "The note body text (HTML supported)"},
                "contact_id": {"type": "string", "description": "Contact ID to associate the note with"},
                "deal_id": {"type": "string", "description": "Deal ID to associate the note with"},
                "company_id": {"type": "string", "description": "Company ID to associate the note with"},
            },
            "required": ["body"],
        },
    },
}

# Map names to functions
_HANDLERS = {
    "hs_connect": hs_connect,
    "hs_status": hs_status,
    "hs_search_contacts": hs_search_contacts,
    "hs_get_contact": hs_get_contact,
    "hs_create_contact": hs_create_contact,
    "hs_update_contact": hs_update_contact,
    "hs_search_deals": hs_search_deals,
    "hs_get_deal": hs_get_deal,
    "hs_create_deal": hs_create_deal,
    "hs_update_deal": hs_update_deal,
    "hs_search_companies": hs_search_companies,
    "hs_get_company": hs_get_company,
    "hs_create_company": hs_create_company,
    "hs_list_pipelines": hs_list_pipelines,
    "hs_create_note": hs_create_note,
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_hubspot_tools(registry):
    """Register all 15 HubSpot tools with a ToolRegistry."""
    for name, handler in _HANDLERS.items():
        registry.register(name, handler, _SCHEMAS[name])
