from __future__ import annotations

import json
import os
from typing import Any

from .m2_agent import ModelResponse, ToolCall


class OpenAICompatibleModel:
    def __init__(self, model: str | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install the dependency with: pip install openai") from error
        options: dict[str, Any] = {"api_key": api_key}
        if base_url := os.getenv("OPENAI_BASE_URL"):
            options["base_url"] = base_url
        self.client = OpenAI(**options)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        response = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools)
        message = response.choices[0].message
        calls = tuple(
            ToolCall(call.id, call.function.name, json.loads(call.function.arguments))
            for call in (message.tool_calls or [])
        )
        return ModelResponse(message.content, calls)

