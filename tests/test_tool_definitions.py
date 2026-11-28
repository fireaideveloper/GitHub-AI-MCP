"""Regression coverage for the public MCP definition contract."""
import inspect
from typing import Annotated, get_args, get_origin

from github_ai_mcp.core.job_engine import Service
from github_ai_mcp.server import READ, WRITE, ToolResult, build_server
from github_ai_mcp.tool_definitions import TOOL_DEFINITIONS


def test_all_public_tools_have_complete_parameter_documentation():
    names = READ + WRITE
    assert len(names) == len(set(names)) == 26
    assert set(TOOL_DEFINITIONS) == set(names)
    assert "approve_local" not in names
    for name in names:
        description, docs = TOOL_DEFINITIONS[name]
        parameters = set(inspect.signature(getattr(Service, name)).parameters) - {"self"}
        assert set(docs) == parameters, name
        assert len(description) > 60, name
        assert all(value.strip() for value in docs.values()), name


def test_registration_preserves_signature_and_exposes_parameter_metadata(monkeypatch):
    from github_ai_mcp import server as module

    registered = {}

    class CaptureServer:
        def __init__(self, *args, **kwargs):
            pass

        def add_tool(self, function, **kwargs):
            registered[kwargs["name"]] = (function, kwargs)

        def resource(self, *args, **kwargs):
            return lambda function: function

    monkeypatch.setattr(module, "MCPServer", CaptureServer)
    service = object.__new__(Service)
    build_server(service)
    assert set(registered) == {"github_mcp." + name for name in READ + WRITE}
    for name in READ + WRITE:
        function, options = registered["github_mcp." + name]
        original = inspect.signature(getattr(service, name))
        actual = inspect.signature(function)
        assert actual.return_annotation is ToolResult
        assert options["structured_output"] is True
        description, docs = TOOL_DEFINITIONS[name]
        assert options["description"] == description
        assert list(actual.parameters) == list(original.parameters)
        for key, parameter in actual.parameters.items():
            previous = original.parameters[key]
            assert parameter.kind == previous.kind
            assert parameter.default == previous.default
            assert get_origin(parameter.annotation) is Annotated
            base, field = get_args(parameter.annotation)
            assert base == previous.annotation
            assert field.description == docs[key]
