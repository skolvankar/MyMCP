"""Client for the upstream server and for the bridge server.

The upstream server comes from mcp_config.json.
Pass a script path as the target to connect to the bridge instead.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.client import CallToolResult
from loguru import logger
from mcp.types import Tool

CONFIG_PATH = Path(__file__).parent / "mcp_config.json"
SAMPLE_VALUES = {"string": "Goa, India", "number": 1, "integer": 1, "boolean": True}


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Read the server config. Fail fast when it has no servers."""
    config = json.loads(path.read_text(encoding="utf-8"))
    if not config.get("mcpServers"):
        raise ValueError(f"{path.name} names no servers under mcpServers")
    return config


def _connect(target: str | None, session: Client | None = None) -> Client:
    """Reuse a connected session, or build a client for the target.

    A target is a script path. No target means the config.
    """
    if session is not None and session.is_connected():
        return session
    return Client(target if target else load_config())


def open_session() -> Client:
    """Build a client that the caller holds open for many upstream calls."""
    return _connect(None)


async def list_tools(
    target: str | None = None, session: Client | None = None
) -> list[Tool]:
    """Return the live tool list of the target server."""
    logger.info(f"LIST tools | target={target or 'config'}")
    async with _connect(target, session) as client:
        tools = await client.list_tools()
    logger.success(f"LIST tools | count={len(tools)}")
    return tools


async def call_tool(
    name: str,
    arguments: dict[str, Any],
    target: str | None = None,
    session: Client | None = None,
) -> CallToolResult:
    """Call one tool by name. The caller reads is_error on the result."""
    # Only the keys go to the log. The values can be personal data.
    logger.info(f"CALL {name} | keys={sorted(arguments)} | target={target or 'config'}")
    async with _connect(target, session) as client:
        result = await client.call_tool(name, arguments, raise_on_error=False)
    logger.success(f"CALL {name} | is_error={result.is_error}")
    return result


def sample_arguments(schema: dict[str, Any]) -> dict[str, Any]:
    """Build sample values for the required inputs of a schema."""
    properties = schema.get("properties", {})
    arguments: dict[str, Any] = {}
    for field in schema.get("required", []):
        spec = properties.get(field, {})
        enum = spec.get("enum")
        arguments[field] = enum[0] if enum else SAMPLE_VALUES.get(spec.get("type"), "")
    return arguments


def result_text(result: CallToolResult) -> str:
    """Join the text blocks of a tool result."""
    return "\n".join(b.text for b in result.content if hasattr(b, "text"))


def parse_args_option(
    parser: argparse.ArgumentParser, raw: str | None
) -> dict[str, Any] | None:
    """Read the args option. Fail fast unless it is a JSON object."""
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        parser.error(f"--args is not valid JSON: {exc}")
    if not isinstance(parsed, dict):
        parser.error("--args must be a JSON object")
    return parsed


async def main() -> None:
    """List the tools, then call one tool and print the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", help="Script path of a server to use.")
    parser.add_argument("--tool", help="Tool name. The first listed tool by default.")
    parser.add_argument("--args", help="Tool arguments as a JSON object.")
    options = parser.parse_args()

    parsed_args = parse_args_option(parser, options.args)

    tools = await list_tools(options.target)
    if not tools:
        parser.error("the server lists no tools")
    for tool in tools:
        print(f"TOOL {tool.name}")

    tool = next((t for t in tools if t.name == options.tool), None)
    if options.tool and tool is None:
        parser.error(f"unknown tool: {options.tool}")
    tool = tool or tools[0]
    arguments = (
        parsed_args if parsed_args is not None else sample_arguments(tool.input_schema)
    )

    result = await call_tool(tool.name, arguments, options.target)
    print(f"CALL {tool.name} {json.dumps(arguments)}")
    print(f"IS_ERROR {result.is_error}")
    print(
        f"HAS_UI {bool(result.structured_content and '$prefab' in result.structured_content)}"
    )
    print(result_text(result)[:600])


if __name__ == "__main__":
    asyncio.run(main())
