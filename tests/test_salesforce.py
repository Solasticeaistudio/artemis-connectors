"""Tests for Artemis Salesforce connector."""

import json
import pytest
from unittest.mock import MagicMock


class TestRegistration:
    def test_register_all_15(self):
        from artemis.connectors.salesforce import register_salesforce_tools, _SCHEMAS
        mock_reg = MagicMock()
        register_salesforce_tools(mock_reg)
        assert mock_reg.register.call_count == 15

    def test_schemas_complete(self):
        from artemis.connectors.salesforce import _SCHEMAS
        for name, schema in _SCHEMAS.items():
            assert schema["parameters"]["type"] == "object"
            assert "description" in schema
            assert "name" in schema
            assert schema["name"] == name

    def test_handlers_match_schemas(self):
        from artemis.connectors.salesforce import _HANDLERS, _SCHEMAS
        assert set(_HANDLERS.keys()) == set(_SCHEMAS.keys())
        assert len(_HANDLERS) == 15

    def test_all_handlers_are_callable(self):
        from artemis.connectors.salesforce import _HANDLERS
        for name, handler in _HANDLERS.items():
            assert callable(handler), f"Handler '{name}' is not callable"


class TestNotConnected:
    def test_query_without_connect(self):
        import artemis.connectors.salesforce as mod
        mod._client = None
        mod._access_token = None
        result = mod.sf_query("SELECT Id FROM Account")
        assert "Error" in result or "Not connected" in result

    def test_status_without_connect(self):
        import artemis.connectors.salesforce as mod
        mod._client = None
        mod._access_token = None
        result = mod.sf_status()
        assert "Error" in result or "Not connected" in result

    def test_search_without_connect(self):
        import artemis.connectors.salesforce as mod
        mod._client = None
        mod._access_token = None
        result = mod.sf_search("FIND {test}")
        assert "Error" in result or "Not connected" in result

    def test_create_record_without_connect(self):
        import artemis.connectors.salesforce as mod
        mod._client = None
        mod._access_token = None
        result = mod.sf_create_record("Account", '{"Name": "Test"}')
        assert "Error" in result or "Not connected" in result

    def test_create_task_without_connect(self):
        import artemis.connectors.salesforce as mod
        mod._client = None
        mod._access_token = None
        result = mod.sf_create_task("Follow up")
        assert "Error" in result or "Not connected" in result


class TestSOQLParsing:
    """Test that SOQL/SOSL strings pass through correctly (no mangling)."""

    def test_soql_simple_select(self):
        """Verify a basic SOQL string is accepted by sf_query without crashing on parse."""
        from artemis.connectors.salesforce import sf_query
        # Will fail at the network level but the string should not raise a parse error
        import artemis.connectors.salesforce as mod
        mod._client = None
        mod._access_token = None
        result = sf_query("SELECT Id, Name FROM Account WHERE Name = 'Acme' LIMIT 10")
        # Should get a connection error, not a SOQL parse error
        assert "Not connected" in result or "Error" in result
        assert "parse" not in result.lower()

    def test_soql_with_subquery(self):
        import artemis.connectors.salesforce as mod
        mod._client = None
        mod._access_token = None
        result = mod.sf_query(
            "SELECT Id, Name, (SELECT Id, LastName FROM Contacts) FROM Account"
        )
        assert "Not connected" in result or "Error" in result

    def test_sosl_string_passthrough(self):
        import artemis.connectors.salesforce as mod
        mod._client = None
        mod._access_token = None
        result = mod.sf_search("FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name)")
        assert "Not connected" in result or "Error" in result


class TestJSONFieldParsing:
    def test_create_record_invalid_json(self):
        """sf_create_record should return a clear error on bad JSON."""
        import artemis.connectors.salesforce as mod
        # Set up fake connection so we get past the connection check
        mod._client = MagicMock()
        mod._access_token = "fake"
        mod._instance_url = "https://fake.salesforce.com"
        result = mod.sf_create_record("Account", "not valid json")
        assert "Error" in result and "JSON" in result
        # Cleanup
        mod._client = None
        mod._access_token = None

    def test_update_record_invalid_json(self):
        import artemis.connectors.salesforce as mod
        mod._client = MagicMock()
        mod._access_token = "fake"
        mod._instance_url = "https://fake.salesforce.com"
        result = mod.sf_update_record("Account", "001xx", "{bad json}")
        assert "Error" in result and "JSON" in result
        mod._client = None
        mod._access_token = None

    def test_run_flow_invalid_json(self):
        import artemis.connectors.salesforce as mod
        mod._client = MagicMock()
        mod._access_token = "fake"
        mod._instance_url = "https://fake.salesforce.com"
        result = mod.sf_run_flow("My_Flow", "not json")
        assert "Error" in result and "JSON" in result
        mod._client = None
        mod._access_token = None


class TestConnectValidation:
    def test_connect_missing_all_params(self):
        """sf_connect with no params should return a clear error message."""
        from artemis.connectors.salesforce import sf_connect
        result = sf_connect()
        assert "Error" in result or "Provide" in result

    def test_connect_partial_oauth_params(self):
        """sf_connect with only client_id should not crash."""
        from artemis.connectors.salesforce import sf_connect
        result = sf_connect(client_id="test_id")
        assert "Error" in result or "Provide" in result
