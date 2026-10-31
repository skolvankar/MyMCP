"""Live tests for client.py. They need network access and npx."""

from urllib.request import Request, urlopen

import pytest
from fastmcp.client.client import CallToolResult

from client import call_tool, list_tools, load_config, result_text, sample_arguments

pytestmark = pytest.mark.asyncio

REDIRECT_MARK = b"domain_switch"
BROWSER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"


def network_is_redirected() -> bool:
    """Ask Airbnb directly if it sends this network to a local domain."""
    request = Request(
        "https://www.airbnb.com/s/homes", headers={"User-Agent": BROWSER_AGENT}
    )
    with urlopen(request, timeout=30) as response:
        return REDIRECT_MARK in response.read(4096)


def skip_when_redirected(result: CallToolResult) -> None:
    """Skip an error only when Airbnb really redirects this network."""
    if result.is_error and network_is_redirected():
        pytest.skip("Airbnb redirected this network, so upstream returned no data.")


async def test_config_matches_the_task() -> None:
    assert load_config() == {
        "mcpServers": {
            "airbnb": {
                "command": "npx",
                "args": ["-y", "@openbnb/mcp-server-airbnb", "--ignore-robots-txt"],
            }
        }
    }


async def test_list_tools_returns_live_schemas() -> None:
    tools = await list_tools()
    assert tools
    assert all(tool.input_schema.get("type") == "object" for tool in tools)


async def test_call_tool_by_name_gets_an_upstream_response() -> None:
    tool = (await list_tools())[0]
    result = await call_tool(tool.name, sample_arguments(tool.input_schema))
    assert result_text(result)


async def test_call_tool_by_name_returns_data() -> None:
    tool = (await list_tools())[0]
    result = await call_tool(tool.name, sample_arguments(tool.input_schema))
    skip_when_redirected(result)
    assert result.is_error is False, result_text(result)
