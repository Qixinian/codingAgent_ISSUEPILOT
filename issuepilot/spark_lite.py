from __future__ import annotations

import json
import os
import re
from typing import Any

from .m2_agent import ModelResponse, ToolCall


class SparkLiteModel:
    """JSON fallback because Spark Lite has no native Function Calling."""

    def __init__(self) -> None:
        password = os.getenv("SPARK_API_PASSWORD")
        if not password:
            raise RuntimeError("SPARK_API_PASSWORD is not set")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install the dependency with: pip install openai") from error
        self.client = OpenAI(api_key=password, base_url="https://spark-api-open.xf-yun.com/v1/")

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        history = "\n".join(_history_line(message) for message in messages)
        contract = (
            "你是代码工具调度器。不要解释、不要使用 Markdown，只输出一个 JSON 对象。\n"
            '调用工具格式：{"tool":"工具名","arguments":{}}\n'
            '任务完成格式：{"final":"包含测试结果的总结"}\n'
            f"可用工具：{json.dumps(tools, ensure_ascii=False)}\n"
            f"对话与工具执行历史：\n{history}\n"
            "现在只选择一个下一步动作并输出 JSON："
        )
        converted: list[dict[str, str]] = [{"role": "user", "content": contract}]
        text = self._request(converted)
        try:
            payload = _parse_action(text, tools)
        except (ValueError, json.JSONDecodeError, KeyError, TypeError):
            converted.extend(
                [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            "上一个回答格式错误。禁止解释，只输出一个 JSON 对象，格式必须是 "
                            '{"tool":"工具名","arguments":{}} 或 {"final":"总结"}。'
                        ),
                    },
                ]
            )
            retry = self._request(converted)
            try:
                payload = _parse_action(retry, tools)
            except (ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
                raise ValueError(f"Spark Lite failed to return a JSON action after retry: {retry[:200]}") from error
        if "final" in payload:
            return ModelResponse(str(payload["final"]))
        return ModelResponse(None, (ToolCall("spark-lite-call", payload["tool"], payload.get("arguments", {})),))

    def _request(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat.completions.create(model="lite", messages=messages, temperature=0.1)
        return response.choices[0].message.content or ""


def _json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Spark Lite did not return a JSON action: {text[:200]}")
    return match.group(0)


def _parse_action(text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.loads(_json_object(text))
    final = payload.get("final")
    if isinstance(final, str) and final.strip():
        return {"final": final.strip()}
    tool_name = payload.get("tool")
    allowed = {item["function"]["name"] for item in tools}
    if not isinstance(tool_name, str) or tool_name not in allowed:
        raise ValueError("JSON action has neither a non-empty final nor an allowed tool")
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        raise TypeError("tool arguments must be an object")
    return {"tool": tool_name, "arguments": arguments}


def _history_line(message: dict[str, Any]) -> str:
    if message["role"] == "tool":
        return f"tool_result: {message.get('content', '')}"
    if message.get("tool_calls"):
        return f"assistant_action: {json.dumps(message['tool_calls'], ensure_ascii=False)}"
    return f"{message['role']}: {message.get('content', '')}"
