"""Tests for Artemis ServiceNow connector."""

import json
import pytest
from unittest.mock import MagicMock, patch


class TestRegistration:
    def test_register_all_15(self):
        from artemis.connectors.servicenow import register_servicenow_tools, _SCHEMAS
        mock_reg = MagicMock()
        register_servicenow_tools(mock_reg)
        assert mock_reg.register.call_count == 15

    def test_schemas_complete(self):
        from artemis.connectors.servicenow import _SCHEMAS
        assert len(_SCHEMAS) == 15
        for name, schema in _SCHEMAS.items():
            assert schema["parameters"]["type"] == "object"
            assert "description" in schema
            assert schema["name"] == name

    def test_handlers_match_schemas(self):
        from artemis.connectors.servicenow import _HANDLERS, _SCHEMAS
        assert set(_HANDLERS.keys()) == set(_SCHEMAS.keys())

    def test_all_handlers_return_str(self):
        """Verify all handler functions have return type annotation or return str."""
        from artemis.connectors.servicenow import _HANDLERS
        import inspect
        for name, handler in _HANDLERS.items():
            sig = inspect.signature(handler)
            assert sig.return_annotation in (str, inspect.Parameter.empty), (
                f"{name} should return str"
            )


class TestNotConnected:
    def test_query_without_connect(self):
        import artemis.connectors.servicenow as mod
        mod._client = None
        mod._auth_header = None
        result = mod.snow_query(table="incident")
        assert "Not connected" in result or "Error" in result

    def test_status_without_connect(self):
        import artemis.connectors.servicenow as mod
        mod._client = None
        mod._auth_header = None
        result = mod.snow_status()
        assert "Not connected" in result or "Error" in result

    def test_create_incident_without_connect(self):
        import artemis.connectors.servicenow as mod
        mod._client = None
        mod._auth_header = None
        result = mod.snow_create_incident(short_description="Test")
        assert "Not connected" in result or "Error" in result


class TestEncodedQuery:
    def test_incident_query_construction(self):
        """Verify snow_search_incidents builds correct encoded query parts."""
        import artemis.connectors.servicenow as mod

        # Mock the _api function to capture the params
        captured = {}

        def mock_api(method, path, json_body=None, params=None):
            captured["method"] = method
            captured["path"] = path
            captured["params"] = params
            return {"items": []}

        mod._client = MagicMock()
        mod._auth_header = "Basic dGVzdDp0ZXN0"

        with patch.object(mod, "_api", side_effect=mock_api):
            mod.snow_search_incidents(
                state="1",
                priority="2",
                assigned_to="admin",
                short_description="server down",
            )

        query = captured["params"]["sysparm_query"]
        assert "state=1" in query
        assert "priority=2" in query
        assert "assigned_to=admin" in query
        assert "short_descriptionLIKEserver down" in query
        # Verify parts are joined with ^
        assert "^" in query

    def test_change_query_construction(self):
        """Verify snow_search_changes builds correct encoded query."""
        import artemis.connectors.servicenow as mod

        captured = {}

        def mock_api(method, path, json_body=None, params=None):
            captured["params"] = params
            return {"items": []}

        mod._client = MagicMock()
        mod._auth_header = "Basic dGVzdDp0ZXN0"

        with patch.object(mod, "_api", side_effect=mock_api):
            mod.snow_search_changes(state="-1", type="Emergency")

        query = captured["params"]["sysparm_query"]
        assert "state=-1" in query
        assert "type=Emergency" in query


class TestConnectValidation:
    def test_connect_no_credentials(self):
        """Verify connect fails gracefully when no auth method is provided."""
        import artemis.connectors.servicenow as mod
        result = mod.snow_connect(instance_url="https://dev12345.service-now.com")
        assert "Error" in result
        assert "username/password" in result or "client_id" in result
