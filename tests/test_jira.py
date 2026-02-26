"""Tests for Artemis Jira connector."""

import json
import pytest
from unittest.mock import MagicMock, patch


class TestRegistration:
    def test_register_all_15(self):
        from artemis.connectors.jira import register_jira_tools, _SCHEMAS
        mock_reg = MagicMock()
        register_jira_tools(mock_reg)
        assert mock_reg.register.call_count == 15

    def test_schemas_complete(self):
        from artemis.connectors.jira import _SCHEMAS
        assert len(_SCHEMAS) == 15
        for name, schema in _SCHEMAS.items():
            assert schema["parameters"]["type"] == "object"
            assert "description" in schema
            assert schema["name"] == name

    def test_handlers_match_schemas(self):
        from artemis.connectors.jira import _HANDLERS, _SCHEMAS
        assert set(_HANDLERS.keys()) == set(_SCHEMAS.keys())

    def test_all_handlers_callable(self):
        from artemis.connectors.jira import _HANDLERS
        for name, handler in _HANDLERS.items():
            assert callable(handler), f"{name} handler is not callable"


class TestNotConnected:
    def test_search_without_connect(self):
        import artemis.connectors.jira as mod
        mod._client = None
        result = mod.jira_search(jql="project = TEST")
        assert "Error" in result or "Not connected" in result

    def test_status_without_connect(self):
        import artemis.connectors.jira as mod
        mod._client = None
        result = mod.jira_status()
        assert "Error" in result or "Not connected" in result

    def test_get_issue_without_connect(self):
        import artemis.connectors.jira as mod
        mod._client = None
        result = mod.jira_get_issue(issue_key="PROJ-1")
        assert "Error" in result or "Not connected" in result


class TestADF:
    def test_make_adf_text_structure(self):
        from artemis.connectors.jira import _make_adf_text
        result = _make_adf_text("Hello world")
        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) == 1
        para = result["content"][0]
        assert para["type"] == "paragraph"
        assert len(para["content"]) == 1
        text_node = para["content"][0]
        assert text_node["type"] == "text"
        assert text_node["text"] == "Hello world"

    def test_make_adf_text_empty(self):
        from artemis.connectors.jira import _make_adf_text
        result = _make_adf_text("")
        assert result["content"][0]["content"][0]["text"] == ""

    def test_make_adf_text_special_chars(self):
        from artemis.connectors.jira import _make_adf_text
        text = 'Line with "quotes" & <angle> brackets'
        result = _make_adf_text(text)
        assert result["content"][0]["content"][0]["text"] == text


class TestJQLConstruction:
    def test_search_builds_correct_body(self):
        """Verify jira_search sends the right JQL payload structure."""
        import artemis.connectors.jira as mod
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"issues":[],"total":0}'
        mock_response.json.return_value = {"issues": [], "total": 0}
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response

        # Inject mock state
        mod._client = mock_client
        mod._base_url = "https://test.atlassian.net"
        mod._auth_header = "Basic dGVzdDp0ZXN0"

        result = mod.jira_search(jql="project = TEST AND status = Open", max_results=5)

        # Verify the call
        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"
        assert "/rest/api/3/search" in call_args[0][1]
        body = call_args[1]["json"]
        assert body["jql"] == "project = TEST AND status = Open"
        assert body["maxResults"] == 5
        assert "summary" in body["fields"]
        assert "Found 0 issue(s)" in result

        # Cleanup
        mod._client = None
        mod._base_url = ""
        mod._auth_header = None
