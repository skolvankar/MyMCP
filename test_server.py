"""Tests for server.py. Server tests use the live upstream server.

The tests of pure functions use inline schemas. They start no server.
The live schema has no enum and has one required input per tool.
"""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.client import CallToolResult
from mcp.types import Tool

from client import call_tool, list_tools, result_text, sample_arguments
from server import (
    build_question,
    drop_nulls,
    mcp,
    register_upstream_tools,
    result_card,
)
from test_client import skip_when_redirected

ROOT = Path(__file__).parent
SERVER = str(ROOT / "server.py")
PROVIDER_TOOLS = {"generate_prefab_ui", "search_prefab_components"}
TWO_INPUTS = {
    "type": "object",
    "properties": {
        "city": {"type": "string", "description": "City to use."},
        "size": {"type": "string", "enum": ["small", "large"]},
        "note": {"type": "string"},
    },
    "required": ["city", "size"],
}


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    asyncio.run(register_upstream_tools())
    yield


def first_tool_with_required(tools: list[Tool]) -> Tool:
    return next(tool for tool in tools if tool.input_schema.get("required"))


def has_ui(result: CallToolResult) -> bool:
    return bool(result.structured_content and "$prefab" in result.structured_content)


def is_question(result: CallToolResult) -> bool:
    return result_text(result).startswith("Clarifying question:")


def nested_schema(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "properties": {"size": spec},
        "required": ["size"],
        "$defs": {"Size": {"enum": ["small", "large"]}},
    }


def test_question_asks_only_the_first_missing_required_input() -> None:
    question = build_question("demo", TWO_INPUTS, {})
    assert question.field == "city"
    assert "City to use." in question.text
    assert question.options == []


def test_question_skips_provided_inputs_and_offers_enum_options() -> None:
    question = build_question("demo", TWO_INPUTS, {"city": "Pune"})
    assert question.field == "size"
    assert question.options == ["small", "large"]
    assert '"city": "Pune"' in question.next_step


@pytest.mark.parametrize(
    "spec",
    [
        {"$ref": "#/$defs/Size"},
        {"anyOf": [{"$ref": "#/$defs/Size"}, {"type": "null"}]},
        {"oneOf": [{"const": "small"}, {"const": "large"}]},
    ],
)
def test_question_finds_nested_enum_options(spec: dict[str, Any]) -> None:
    question = build_question("demo", nested_schema(spec), {})
    assert question.options == ["small", "large"]


def test_no_question_when_only_optional_inputs_are_missing() -> None:
    assert build_question("demo", TWO_INPUTS, {"city": "Pune", "size": "small"}) is None


def test_blank_required_input_counts_as_missing() -> None:
    assert build_question("demo", TWO_INPUTS, {"city": "  "}).field == "city"


def test_drop_nulls_keeps_falsy_values() -> None:
    assert drop_nulls({"a": None, "b": 0, "c": False}) == {"b": 0, "c": False}


def test_result_card_keeps_text_in_state() -> None:
    app = result_card("x {{ y }}")
    assert app.state == {"result": "x {{ y }}"}


def test_no_source_file_holds_a_literal_upstream_tool_name() -> None:
    names = [tool.name for tool in asyncio.run(list_tools())]
    for path in ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not [name for name in names if name in source], path.name


@pytest.mark.asyncio
@pytest.mark.usefixtures("registered")
async def test_bridge_lists_every_upstream_tool() -> None:
    upstream = {tool.name for tool in await list_tools()}
    async with Client(mcp) as client:
        bridge = {tool.name for tool in await client.list_tools()}
    assert bridge == upstream | PROVIDER_TOOLS


@pytest.mark.asyncio
@pytest.mark.usefixtures("registered")
async def test_missing_required_input_gets_one_question() -> None:
    tool = first_tool_with_required(await list_tools())
    field = tool.input_schema["required"][0]
    async with Client(mcp) as client:
        result = await client.call_tool(tool.name, {})
    assert is_question(result)
    assert has_ui(result)
    assert field in result_text(result)


@pytest.mark.asyncio
async def test_join_over_stdio_lists_tools_and_asks() -> None:
    upstream = await list_tools()
    bridge = await list_tools(SERVER)
    assert {t.name for t in bridge} == {t.name for t in upstream} | PROVIDER_TOOLS

    asked = await call_tool(upstream[0].name, {}, SERVER)
    assert asked.is_error is False, result_text(asked)
    assert is_question(asked)
    assert has_ui(asked)


@pytest.mark.asyncio
async def test_join_over_stdio_answer_matches_upstream() -> None:
    tool = (await list_tools())[0]
    arguments = sample_arguments(tool.input_schema)
    direct = await call_tool(tool.name, arguments)
    answered = await call_tool(tool.name, arguments, SERVER)
    assert not is_question(answered)
    assert answered.is_error == direct.is_error
    assert set(json.loads(result_text(answered))) == set(
        json.loads(result_text(direct))
    )


@pytest.mark.asyncio
async def test_join_over_stdio_answer_returns_data() -> None:
    tool = (await list_tools())[0]
    answered = await call_tool(tool.name, sample_arguments(tool.input_schema), SERVER)
    skip_when_redirected(answered)
    assert answered.is_error is False, result_text(answered)
    assert has_ui(answered)
