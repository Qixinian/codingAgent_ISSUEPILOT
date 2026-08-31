from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

from .m2_agent import ModelResponse, ToolCall


class OllamaModel:
    """Ollama adapter using the native /api/chat endpoint."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3:4b")
        root = base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.chat_url = f"{root.rstrip('/')}/api/chat"
        self.opener = build_opener(ProxyHandler({}))

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": _ollama_messages(messages),
            "tools": tools,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 1024},
        }
        data = self._post(payload)
        message = data["message"]
        calls = tuple(
            ToolCall(
                item.get("id") or f"ollama-call-{index}",
                item["function"]["name"],
                _arguments(item["function"].get("arguments", {})),
            )
            for index, item in enumerate(message.get("tool_calls") or [])
        )
        return ModelResponse(message.get("content"), calls)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.chat_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))


def _ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    tool_names: dict[str, str] = {}
    for message in messages:
        role = message["role"]
        if role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_name": tool_names.get(message.get("tool_call_id", ""), "unknown"),
                    "content": message.get("content", ""),
                }
            )
            continue
        item: dict[str, Any] = {"role": role, "content": message.get("content") or ""}
        if message.get("tool_calls"):
            native_calls = []
            for call in message["tool_calls"]:
                name = call["function"]["name"]
                tool_names[call["id"]] = name
                native_calls.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": _arguments(call["function"].get("arguments", {})),
                        },
                    }
                )
            item["tool_calls"] = native_calls
        converted.append(item)
    return converted


def _arguments(value: str | dict[str, Any]) -> dict[str, Any]:
    arguments = json.loads(value) if isinstance(value, str) else value
    if not isinstance(arguments, dict):
        raise TypeError("Ollama tool arguments must be an object")
    return arguments
