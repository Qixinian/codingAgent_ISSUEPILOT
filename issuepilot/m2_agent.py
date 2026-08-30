from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .m2_tools import CodingTools


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class ToolCallingModel(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse: ...


@dataclass(frozen=True)
class AgentResult:
    content: str
    steps: int
    completed: bool
    trace: tuple[dict[str, Any], ...]


class CodingAgent:
    def __init__(self, tools: CodingTools, model: ToolCallingModel, max_steps: int = 12) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.tools, self.model, self.max_steps = tools, model, max_steps

    def run(self, task: str) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a coding agent. Inspect the repository, make the smallest required change, "
                    "run tests, and finish only after reporting test results."
                ),
            },
            {"role": "user", "content": task},
        ]
        trace: list[dict[str, Any]] = []
        for step in range(1, self.max_steps + 1):
            response = self.model.complete(messages, TOOL_SCHEMAS)
            assistant: dict[str, Any] = {"role": "assistant", "content": response.content}
            if response.tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in response.tool_calls
                ]
            messages.append(assistant)
            if not response.tool_calls:
                return AgentResult(response.content or "Task finished.", step, True, tuple(trace))
            for call in response.tool_calls:
                result = self._execute(call)
                trace.append({"step": step, "tool": call.name, "arguments": call.arguments, "result": result})
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)}
                )
        return AgentResult(f"Stopped after reaching max_steps={self.max_steps}.", self.max_steps, False, tuple(trace))

    def _execute(self, call: ToolCall) -> dict[str, Any]:
        try:
            if call.name == "list_files":
                return {"ok": True, "files": self.tools.list_files()}
            if call.name == "read_file":
                return {"ok": True, "content": self.tools.read_file(call.arguments["path"])}
            if call.name == "search_code":
                return {"ok": True, "matches": self.tools.search_code(call.arguments["query"])}
            if call.name == "write_file":
                return {"ok": True, **asdict(self.tools.write_file(call.arguments["path"], call.arguments["content"]))}
            if call.name == "run_tests":
                return {"ok": True, **asdict(self.tools.run_tests())}
            raise ValueError(f"Unknown tool: {call.name}")
        except (KeyError, OSError, UnicodeError, ValueError) as error:
            return {"ok": False, "error": type(error).__name__, "message": str(error)}


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        parameters["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


TOOL_SCHEMAS = [
    _schema("list_files", "List repository files", {}),
    _schema("read_file", "Read a UTF-8 text file", {"path": {"type": "string"}}, ["path"]),
    _schema("search_code", "Search repository text", {"query": {"type": "string"}}, ["query"]),
    _schema(
        "write_file",
        "Create or replace a UTF-8 text file inside the repository",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _schema("run_tests", "Run python -m pytest -q with a timeout", {}),
]
