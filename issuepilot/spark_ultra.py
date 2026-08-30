from __future__ import annotations

import json
import os
from typing import Any

from .m2_agent import ModelResponse, ToolCall


class SparkUltraModel:
    """Spark Ultra-32K adapter using native Function Calling."""

    def __init__(self) -> None:
        password = os.getenv("SPARK_ULTRA_API_PASSWORD")
        if not password:
            raise RuntimeError("SPARK_ULTRA_API_PASSWORD is not set")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install the dependency with: pip install openai") from error
        self.client = OpenAI(
            api_key=password,
            base_url="https://spark-api-open.xf-yun.com/v1/",
        )

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        response = self.client.chat.completions.create(
            model="4.0Ultra",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            extra_body={"tool_calls_switch": True},
        )
        message = response.choices[0].message
        calls = tuple(
            ToolCall(
                call.id,
                call.function.name,
                json.loads(call.function.arguments),
            )
            for call in (message.tool_calls or [])
        )
        return ModelResponse(message.content, calls)

