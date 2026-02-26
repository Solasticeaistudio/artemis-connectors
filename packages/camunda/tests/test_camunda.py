"""Tests for Artemis Camunda connector."""

import os
import pytest
from unittest.mock import MagicMock

SAMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="Definitions_1">
  <bpmn:process id="order_process" name="Order Processing" isExecutable="true">
    <bpmn:startEvent id="start_1" name="Order Received"/>
    <bpmn:userTask id="review_1" name="Review Order"/>
    <bpmn:serviceTask id="fulfill_1" name="Fulfill Order"/>
    <bpmn:exclusiveGateway id="gw_1" name="Approved?"/>
    <bpmn:endEvent id="end_1" name="Done"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start_1" targetRef="review_1"/>
    <bpmn:sequenceFlow id="f2" sourceRef="review_1" targetRef="gw_1"/>
    <bpmn:sequenceFlow id="f3" sourceRef="gw_1" targetRef="fulfill_1" name="Yes">
      <bpmn:conditionExpression>approved == true</bpmn:conditionExpression>
    </bpmn:sequenceFlow>
    <bpmn:sequenceFlow id="f4" sourceRef="gw_1" targetRef="end_1" name="No"/>
    <bpmn:sequenceFlow id="f5" sourceRef="fulfill_1" targetRef="end_1"/>
  </bpmn:process>
</bpmn:definitions>"""

INVALID_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D1">
  <bpmn:process id="bad" name="Bad" isExecutable="true">
    <bpmn:userTask id="t1" name="Lonely"/>
    <bpmn:endEvent id="end_1"/>
    <bpmn:sequenceFlow id="f1" sourceRef="t1" targetRef="end_1"/>
  </bpmn:process>
</bpmn:definitions>"""


class TestBpmnParse:
    def test_parse(self, tmp_path):
        f = tmp_path / "test.bpmn"
        f.write_text(SAMPLE_BPMN)
        from artemis.connectors.camunda import bpmn_parse
        result = bpmn_parse(str(f))
        assert "order_process" in result
        assert "startEvent" in result
        assert "userTask" in result

    def test_parse_missing_file(self):
        from artemis.connectors.camunda import bpmn_parse
        result = bpmn_parse("/no/such/file.bpmn")
        assert "Error" in result


class TestBpmnValidate:
    def test_valid(self, tmp_path):
        f = tmp_path / "ok.bpmn"
        f.write_text(SAMPLE_BPMN)
        from artemis.connectors.camunda import bpmn_validate
        result = bpmn_validate(str(f))
        assert "VALID" in result

    def test_invalid(self, tmp_path):
        f = tmp_path / "bad.bpmn"
        f.write_text(INVALID_BPMN)
        from artemis.connectors.camunda import bpmn_validate
        result = bpmn_validate(str(f))
        assert "INVALID" in result
        assert "no start event" in result.lower()


class TestRegistration:
    def test_register_all_15(self):
        from artemis.connectors.camunda import register_camunda_tools, _SCHEMAS
        mock_reg = MagicMock()
        register_camunda_tools(mock_reg)
        assert mock_reg.register.call_count == 15

    def test_schemas_complete(self):
        from artemis.connectors.camunda import _SCHEMAS
        for name, schema in _SCHEMAS.items():
            assert schema["parameters"]["type"] == "object"
            assert "description" in schema

    def test_entry_point_discoverable(self):
        """Verify the entry point is configured correctly (requires pip install -e .)."""
        from importlib.metadata import entry_points
        eps = entry_points(group="solstice_agent.connectors")
        names = [ep.name for ep in eps]
        assert "camunda" in names


class TestNotConnected:
    def test_status_without_connect(self):
        import artemis.connectors.camunda as mod
        mod._client = None
        result = mod.camunda_status()
        assert "Error" in result or "Not connected" in result
