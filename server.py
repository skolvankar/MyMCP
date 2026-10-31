"""FastMCP bridge server for the upstream tools.

The server registers one tool per upstream tool at startup.
A call with a missing required input gets a Generative UI question.
A complete call goes to the upstream server.
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import Client, FastMCP
from fastmcp.apps.config import AppConfig, app_config_to_meta_dict
from fastmcp.apps.generative import GenerativeUI
from fastmcp.exceptions import ToolError
from fastmcp.tools.base import Tool, ToolResult
from loguru import logger
from prefab_ui.app import PrefabApp
from prefab_ui.components import Card, CardContent, Text
from prefab_ui.generative import RESOURCE_URI
from pydantic import Field

from client import call_tool, list_tools, open_session, result_text

mcp = FastMCP("Airbnb Bridge")
mcp.add_provider(GenerativeUI())

# The Prefab sandbox finds Deno on the PATH. Deno installs next to this Python.
os.environ["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"

UI_TOOL = "generate_prefab_ui"
CARD_TEXT_LIMIT = 2000

# The sandbox injects question, options and reply as variables.
# Values go through data, so schema text never becomes code.
# Values also stay in state, so the renderer does not read them as templates.
QUESTION_CODE = """
from prefab_ui.actions import SetState
from prefab_ui.actions.mcp import SendMessage
from prefab_ui.app import PrefabApp
from prefab_ui.components import Button, Card, CardContent, Column, Input, Muted, Text
from prefab_ui.components.control_flow import If
from prefab_ui.rx import STATE

state = {"answered": False, "answer": "", "question": question, "reply": reply}
state.update({"option_%d" % i: option for i, option in enumerate(options)})

with PrefabApp(state=state) as app:
    with Card(css_class="max-w-lg mx-auto"):
        with CardContent():
            with Column(gap=3):
                Text("{{ question }}", css_class="font-medium")
                with If(STATE.answered):
                    Muted("Answer sent.")
                with If(~STATE.answered):
                    with Column(gap=2):
                        for i in range(len(options)):
                            value = "{{ option_%d }}" % i
                            Button(
                                value,
                                variant="outline",
                                on_click=[
                                    SendMessage("{{ reply }}" + value),
                                    SetState("answered", True),
                                ],
                            )
                        if not options:
                            Input(name="answer", placeholder="Type your answer")
                            Button(
                                "Send",
                                disabled=~STATE.answer,
                                on_click=[
                                    SendMessage("{{ reply }}{{ answer }}"),
                                    SetState("answered", True),
                                ],
                            )
"""


@dataclass
class Question:
    """One clarifying question for one missing required input."""

    field: str
    text: str
    options: list[str]
    next_step: str

    def ui_data(self) -> dict[str, Any]:
        """Return the values that the sandbox injects into QUESTION_CODE."""
        reply = f"{self.next_step} The answer is: "
        return {"question": self.text, "options": self.options, "reply": reply}

    def model_text(self) -> str:
        """Return the text that a client without a UI reads."""
        choices = f" Options: {', '.join(self.options)}." if self.options else ""
        return f"Clarifying question: {self.text}{choices} {self.next_step}"


def enum_values(spec: dict[str, Any], schema: dict[str, Any]) -> list[Any]:
    """Collect enum values from a property, its branches and its references."""
    pending = [spec]
    seen: set[str] = set()
    values: list[Any] = []
    while pending:
        item = pending.pop(0)
        ref = item.get("$ref")
        if ref and ref not in seen:
            seen.add(ref)
            pending.append(schema.get("$defs", {}).get(ref.rsplit("/", 1)[-1], {}))
        values.extend(item.get("enum", []))
        if "const" in item:
            values.append(item["const"])
        pending.extend(item.get("anyOf", []))
        pending.extend(item.get("oneOf", []))
    return [value for value in values if value is not None]


def build_question(
    tool_name: str, schema: dict[str, Any], provided: dict[str, Any]
) -> Question | None:
    """Build a question for the first missing required input in a schema.

    Return None when the call has every required input.
    """
    missing = [
        field
        for field in schema.get("required", [])
        if provided.get(field) is None or str(provided[field]).strip() == ""
    ]
    if not missing:
        return None

    field = missing[0]
    spec = schema.get("properties", {}).get(field, {})
    description = spec.get("description", "")
    text = f"The {tool_name} tool needs {field}. {description}".strip()
    known = {key: value for key, value in provided.items() if key != field}
    next_step = (
        f"Call {tool_name} again with these inputs: {json.dumps(known)}. "
        f"Set {field} to the answer."
    )
    options = [str(value) for value in enum_values(spec, schema)]
    return Question(field=field, text=text, options=options, next_step=next_step)


def drop_nulls(arguments: dict[str, Any]) -> dict[str, Any]:
    """Remove null inputs. The upstream schema does not accept them."""
    return {key: value for key, value in arguments.items() if value is not None}


def result_card(text: str) -> PrefabApp:
    """Build the card that shows a forwarded result in a UI host."""
    with Card(css_class="max-w-lg mx-auto") as view, CardContent():
        Text("{{ result }}", css_class="whitespace-pre-wrap")
    return PrefabApp(view=view, state={"result": text[:CARD_TEXT_LIMIT]})


async def ask(question: Question) -> ToolResult:
    """Render a question through the Generative UI provider."""
    text = question.model_text()
    try:
        rendered = await mcp.call_tool(
            UI_TOOL, {"code": QUESTION_CODE, "data": question.ui_data()}
        )
    except (ToolError, ValueError, RuntimeError, OSError) as exc:
        # The text still carries the question, so the call can continue.
        logger.warning(f"ASK {question.field} | UI failed | reason={exc}")
        return ToolResult(content=text)
    logger.success(f"ASK {question.field} | options={len(question.options)}")
    return ToolResult(content=text, structured_content=rendered.structured_content)


class BridgeTool(Tool):
    """A local tool that asks for missing inputs and forwards complete calls."""

    upstream_schema: dict[str, Any]
    session: Any = Field(default=None, exclude=True)

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        """Ask one question, or forward the call to the upstream server."""
        logger.info(f"CALL {self.name} | keys={sorted(arguments)}")
        arguments = drop_nulls(arguments)
        question = build_question(self.name, self.upstream_schema, arguments)
        if question is not None:
            return await ask(question)

        result = await call_tool(self.name, arguments, session=self.session)
        text = result_text(result)
        if result.is_error:
            logger.error(f"FAILED: {self.name} | upstream returned an error")
            raise ToolError(text)
        # The tool declares a UI, so a host needs a card for this result too.
        return ToolResult(
            content=result.content,
            structured_content=result.structured_content or result_card(text),
        )


async def register_upstream_tools(session: Client | None = None) -> list[str]:
    """Register one bridge tool per tool in the live upstream list."""
    meta = {"ui": app_config_to_meta_dict(AppConfig(resource_uri=RESOURCE_URI))}
    names = []
    for upstream in await list_tools(session=session):
        schema = upstream.input_schema
        # The exposed schema drops required, so a partial call reaches the bridge.
        exposed = {key: value for key, value in schema.items() if key != "required"}
        tool = BridgeTool(
            name=upstream.name,
            description=upstream.description,
            parameters=exposed,
            upstream_schema=schema,
            session=session,
            annotations=upstream.annotations,
            meta=meta,
        )
        mcp.add_tool(tool)
        names.append(upstream.name)
    logger.success(f"REGISTER | tools={len(names)}")
    return names


async def main() -> None:
    """Hold one upstream session, register the tools, then serve on stdio."""
    async with open_session() as session:
        await register_upstream_tools(session)
        await mcp.run_async(transport="stdio", show_banner=False)


if __name__ == "__main__":
    asyncio.run(main())
