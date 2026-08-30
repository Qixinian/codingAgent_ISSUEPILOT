"""
IssuePilot M2 的另一个模型适配器，作用和 m2_model.py 类似，但它专门针对星火 Lite。

m2_model.py 假设模型原生支持 Function Calling。
spark_lite.py 假设星火 Lite 不原生支持 Function Calling。
因此，它要求模型用普通文本输出一个 JSON对象，再由本地代码把 JSON转换成 ToolCall。

CodingAgent传入消息历史和工具定义
              ↓
SparkLiteModel把它们拼成中文提示词
              ↓
请求星火 Lite 输出一个JSON对象
              ↓
解析并验证JSON
       ┌──────┴──────┐
       ↓             ↓
 {"tool":...}    {"final":...}
       ↓             ↓
   ToolCall       最终答案
       ↓             ↓
CodingAgent执行工具   任务结束
"""

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
        # 将对话历史转成文本 将每条消息转换为单行文字，最后用换行符连接。
        history = "\n".join(_history_line(message) for message in messages)
        # 构造 JSON输出契约
        contract = (
            "你是代码工具调度器。不要解释、不要使用 Markdown，只输出一个 JSON 对象。\n"
            '调用工具格式：{"tool":"工具名","arguments":{}}\n'
            '任务完成格式：{"final":"包含测试结果的总结"}\n'
            f"可用工具：{json.dumps(tools, ensure_ascii=False)}\n"
            f"对话与工具执行历史：\n{history}\n"
            "现在只选择一个下一步动作并输出 JSON："
        )
        # 创建实际请求消息 简化了兼容过程，但也意味着原本的系统消息只是以普通文本形式嵌入历史，不再是接口层面的独立 system 消息。
        converted: list[dict[str, str]] = [{"role": "user", "content": contract}]
        # 第一次请求
        text = self._request(converted)
        # 第一次解析
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
            # 第二次请求
            retry = self._request(converted)
            # 第二次解析
            try:
                payload = _parse_action(retry, tools)
            except (ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
                raise ValueError(f"Spark Lite failed to return a JSON action after retry: {retry[:200]}") from error # 星火 Lite重试后仍然没有返回有效 JSON动作。
        # 处理最终答案
        if "final" in payload:
            return ModelResponse(str(payload["final"]))
        # 处理工具调用
        return ModelResponse(
            None, 
            (ToolCall("spark-lite-call", payload["tool"], payload.get("arguments", {})),) # 如果 payload 中没有 final，就把它转换成工具调用。
        )

    # 发送实际请求
    def _request(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat.completions.create(model="lite", messages=messages, temperature=0.1)
        return response.choices[0].message.content or ""

# 提取 JSON对象 在模型输出中寻找`{任意内容}`
def _json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    # 没找到JSON
    if not match:
        raise ValueError(f"Spark Lite did not return a JSON action: {text[:200]}")
    # 返回匹配内容
    return match.group(0)

# 验证模型动作 它不仅解析 JSON，还负责验证模型输出是否符合允许规则。
def _parse_action(text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    # 提取并解析 JSON
    payload = json.loads(_json_object(text))
    # 优先检查最终答案
    final = payload.get("final")
    # 必须同时满足：final 是字符串  删除首尾空白后不为空
    if isinstance(final, str):
        normalized = final.strip()
        if normalized and normalized.casefold() not in {"none", "null", "nil", "无", "空"}:
            return {"final": normalized}
    # 取得工具名称
    tool_name = payload.get("tool")
    # 建立工具白名单
    allowed = {item["function"]["name"] for item in tools}
    # 验证工具名 模型不能通过 JSON随意发明工具名称，只能选择 tools 参数中明确允许的工具。
    if not isinstance(tool_name, str) or tool_name not in allowed:
        raise ValueError("JSON action has neither a non-empty final nor an allowed tool")
    # 验证参数
    arguments = payload.get("arguments", {}) # 如果没有 arguments，默认为空字典。
    if not isinstance(arguments, dict):
        raise TypeError("tool arguments must be an object")
    # 返回标准化动作
    return {"tool": tool_name, "arguments": arguments}

# 格式化历史消息
def _history_line(message: dict[str, Any]) -> str:
    # 工具执行结果
    if message["role"] == "tool":
        return f"tool_result: {message.get('content', '')}"
    # 助手工具调用
    if message.get("tool_calls"):
        return f"assistant_action: {json.dumps(message['tool_calls'], ensure_ascii=False)}"
    # 普通消息
    return f"{message['role']}: {message.get('content', '')}"
