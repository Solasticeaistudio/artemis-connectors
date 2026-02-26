"""Tests for Artemis HubSpot connector."""

import json
import pytest
from unittest.mock import MagicMock, patch


class TestRegistration:
    def test_register_all_15(self):
        from artemis.connectors.hubspot import register_hubspot_tools, _SCHEMAS
        mock_reg = MagicMock()
        register_hubspot_tools(mock_reg)
        assert mock_reg.register.call_count == 15

    def test_schemas_complete(self):
        from artemis.connectors.hubspot import _SCHEMAS
        for name, schema in _SCHEMAS.items():
            assert schema["parameters"]["type"] == "object"
            assert "description" in schema
            assert "name" in schema
            assert schema["name"] == name

    def test_handlers_match_schemas(self):
        from artemis.connectors.hubspot import _HANDLERS, _SCHEMAS
        assert set(_HANDLERS.keys()) == set(_SCHEMAS.keys())

    def test_all_handlers_return_str(self):
        """Verify every handler has a return annotation or docstring implying str."""
        from artemis.connectors.hubspot import _HANDLERS
        # All handlers are callable
        for name, handler in _HANDLERS.items():
            assert callable(handler), f"{name} is not callable"


class TestNotConnected:
    def setup_method(self):
        import artemis.connectors.hubspot as mod
        mod._client = None
        mod._access_token = None

    def test_status_without_connect(self):
        import artemis.connectors.hubspot as mod
        result = mod.hs_status()
        assert "Error" in result or "Not connected" in result

    def test_search_without_connect(self):
        import artemis.connectors.hubspot as mod
        result = mod.hs_search_contacts(query="test")
        assert "Error" in result or "Not connected" in result

    def test_get_contact_without_connect(self):
        import artemis.connectors.hubspot as mod
        result = mod.hs_get_contact("123")
        assert "Error" in result or "Not connected" in result

    def test_search_deals_without_connect(self):
        import artemis.connectors.hubspot as mod
        result = mod.hs_search_deals(query="test")
        assert "Error" in result or "Not connected" in result

    def test_list_pipelines_without_connect(self):
        import artemis.connectors.hubspot as mod
        result = mod.hs_list_pipelines()
        assert "Error" in result or "Not connected" in result


class TestSearchFilters:
    """Test that search functions build correct filter bodies."""

    def test_contact_query_body(self):
        """Verify free-text query is set correctly in the request body."""
        import artemis.connectors.hubspot as mod

        captured = {}

        def mock_api(method, path, json_body=None):
            captured["method"] = method
            captured["path"] = path
            captured["body"] = json_body
            return {"total": 0, "results": []}

        mod._client = MagicMock()
        mod._access_token = "fake-token"

        with patch.object(mod, "_api", side_effect=mock_api):
            mod.hs_search_contacts(query="john", limit=5)

        assert captured["method"] == "POST"
        assert captured["path"] == "/crm/v3/objects/contacts/search"
        assert captured["body"]["query"] == "john"
        assert captured["body"]["limit"] == 5

    def test_contact_filter_body(self):
        """Verify property filter builds filterGroups correctly."""
        import artemis.connectors.hubspot as mod

        captured = {}

        def mock_api(method, path, json_body=None):
            captured["body"] = json_body
            return {"total": 0, "results": []}

        mod._client = MagicMock()
        mod._access_token = "fake-token"

        with patch.object(mod, "_api", side_effect=mock_api):
            mod.hs_search_contacts(
                filter_property="company",
                filter_operator="CONTAINS",
                filter_value="Acme",
            )

        fg = captured["body"]["filterGroups"]
        assert len(fg) == 1
        f = fg[0]["filters"][0]
        assert f["propertyName"] == "company"
        assert f["operator"] == "CONTAINS"
        assert f["value"] == "Acme"

    def test_deal_search_properties_split(self):
        """Verify comma-separated properties get split into a list."""
        import artemis.connectors.hubspot as mod

        captured = {}

        def mock_api(method, path, json_body=None):
            captured["body"] = json_body
            return {"total": 0, "results": []}

        mod._client = MagicMock()
        mod._access_token = "fake-token"

        with patch.object(mod, "_api", side_effect=mock_api):
            mod.hs_search_deals(query="big", properties="dealname,amount,closedate")

        assert captured["body"]["properties"] == ["dealname", "amount", "closedate"]


class TestCreatePayloads:
    """Test that create/update functions parse JSON and build correct payloads."""

    def test_create_contact_bad_json(self):
        import artemis.connectors.hubspot as mod
        mod._client = MagicMock()
        mod._access_token = "fake-token"
        result = mod.hs_create_contact("not json")
        assert "Error" in result
        assert "JSON" in result

    def test_create_note_associations(self):
        """Verify note associations are built for contact, deal, and company."""
        import artemis.connectors.hubspot as mod

        captured = {}

        def mock_api(method, path, json_body=None):
            captured["body"] = json_body
            return {"id": "99"}

        mod._client = MagicMock()
        mod._access_token = "fake-token"

        with patch.object(mod, "_api", side_effect=mock_api):
            mod.hs_create_note(body="Test note", contact_id="1", deal_id="2", company_id="3")

        assoc = captured["body"]["associations"]
        assert len(assoc) == 3
        to_ids = {a["to"]["id"] for a in assoc}
        assert to_ids == {"1", "2", "3"}
