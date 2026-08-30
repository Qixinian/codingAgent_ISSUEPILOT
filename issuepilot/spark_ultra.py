"""
IssuePilot M2 的星火 Ultra-32K 模型适配器。

把 CodingAgent 的对话历史和工具定义发送给星火 Ultra，并把星火返回的原生 Function Calling 结果转换成 IssuePilot 内部的 ModelResponse 和 ToolCall。
星火有时没有返回结构化 message.tool_calls，却在普通文本中输出工具标记。
write_file 的 content 很长时，工具参数 JSON可能不标准，导致 json.loads() 失败。

与刚才的 spark_lite.py 最大区别是：

Spark Lite通过提示词要求模型输出 JSON，再由本地解析。
Spark Ultra直接使用接口原生的 Function Calling。
Ultra可以直接接收结构化的 tools。
Ultra返回结构化的 message.tool_calls

第一次请求：tool_choice="auto"
          ↓
是否返回 message.tool_calls？
  ┌───────┴────────┐
  │是              │否
  ▼                ▼
解析原生调用    内容是否像工具标记？
                    │
             ┌──────┴──────┐
             │否           │是
             ▼             ▼
         当最终答案    第二次请求
                    tool_choice="required"
                           ↓
                   是否有tool_calls？
                    ┌──────┴──────┐
                    │是           │否
                    ▼             ▼
               解析原生调用   解析文本工具标记
"""

from __future__ import annotations

import json
import os
import re
from html import unescape
from typing import Any

from .m2_agent import ModelResponse, ToolCall

# 定义 SparkUltraModel 即使没有显式继承 ToolCallingModel，只要方法签名和返回行为符合协议，就能使用。
class SparkUltraModel:
    """Spark Ultra-32K adapter using native Function Calling."""

    # 初始化方法
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

    # 允许方法
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        # 第一次请求：自动决定是否调用工具
        response = self._request(messages, tools, "auto")
        # 取得模型消息
        message = response.choices[0].message
        # 检测“伪工具调用” ：没有标准的 message.tool_calls  普通文本看起来像工具调用标记
        # 星火 Ultra理论上支持原生 Function Calling，但某些情况下可能把工具调用放进普通文本：<function=read_file><parameter=path>app.py</parameter></function>
        if not message.tool_calls and _looks_like_tool_markup(message.content):
            # 第二次请求：强制工具调用
            response = self._request(messages, tools, "required")
            # 这一轮必须调用工具，不应只返回普通文字。
            message = response.choices[0].message
            # 第二次仍然没有原生工具调用
            if not message.tool_calls:
                # 如果强制调用后，星火仍然只返回普通文本，就进入降级解析。
                fallback = _parse_text_tool(message.content, tools)
                return ModelResponse(None, (fallback,))
        # 解析工具调用 把星火接口返回的工具调用转换成 IssuePilot内部的 ToolCall
        calls = tuple(
            ToolCall(
                call.id,
                call.function.name,
                _parse_arguments(call.function.arguments, call.function.name),
            )
            for call in (message.tool_calls or [])
        )
        return ModelResponse(message.content, calls)

    # 统一发送请求
    def _request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str,
    ) -> Any:
        return self.client.chat.completions.create(
            model="4.0Ultra",
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            extra_body={"tool_calls_switch": True}, # 向星火兼容服务发送厂商扩展字段，用于开启工具调用。
        )

# 判断普通文本是否看起来像一个工具调用
def _looks_like_tool_markup(content: str | None) -> bool:
    if not content:
        return False
    lowered = content.casefold() # 忽略大小写
    # 只要包含以下任意特征，就认为像工具调用：
    # function=
    # <parameter=
    # </function>
    return "function=" in lowered or "<parameter=" in lowered or "</function>" in lowered

# 解析原生工具参数
def _parse_arguments(
    raw: str,  # 接口返回的工具参数字符串
    tool_name: str | None = None # 工具名称
) -> dict[str, Any]:
    # 正常解析
    try:
        arguments = json.loads(raw, strict=False) # 它会放宽对JSON字符串中部分控制字符的限制。
    # 如果参数JSON损坏，不是write_file，直接重新抛出原异常
    except json.JSONDecodeError:
        if tool_name != "write_file":
            raise
        arguments = _repair_write_arguments(raw)
    # 检查解析结果必须是字典
    if not isinstance(arguments, dict):
        raise TypeError("Spark Ultra tool arguments must be a JSON object")
    return arguments

# 修复写文件参数
def _repair_write_arguments(raw: str) -> dict[str, str]:
    # 提取 path
    path_match = re.search(r'"path"\s*:\s*"((?:\\.|[^"\\])*)"', raw)
    # 定位 content 的开始
    content_match = re.search(r'"content"\s*:\s*"', raw)
    # 检查字段是否存在 必须同时找到：path content 开头
    if not path_match or not content_match:
        raise ValueError("Cannot recover path and content from Spark Ultra write_file arguments")
    # 寻找最后一个双引号
    final_quote = raw.rfind('"')
    # 检查结束引号位置
    if final_quote <= content_match.end():
        raise ValueError("Cannot find the end of Spark Ultra write_file content")
    # 提取并恢复文本
    return {
        "path": _unescape_json_text(path_match.group(1)), # 取得正则捕获的路径内容。
        "content": _unescape_json_text(raw[content_match.end():final_quote]), # 从 "content":" 后面开始，一直取到最后一个双引号之前。
    }

# 恢复转义字符
def _unescape_json_text(value: str) -> str:
    return (
        value.replace("\\r\\n", "\n") # 将\r\n 恢复为换行。
        .replace("\\n", "\n") # 将\n 恢复为换行
        .replace("\\r", "\n") # 统一转换成换行
        .replace("\\t", "\t") # 恢复制表符
        .replace('\\"', '"')  # 恢复转义双引号。
        .replace("\\\\", "\\") # 把双反斜杠恢复成单反斜杠。
    )

# 解析文本工具调用 当星火两次都没有返回原生 message.tool_calls 时，这个函数把普通文本标记转换成 ToolCall。
def _parse_text_tool(content: str | None, tools: list[dict[str, Any]]) -> ToolCall:
    # 内容为空，无法解析，直接报错。
    if not content:
        raise ValueError("Spark Ultra returned empty textual tool markup")
    # 提取工具名称
    name_match = re.search(r"(?:<)?function=([A-Za-z_][A-Za-z0-9_]*)>", content)
    if not name_match:
        raise ValueError(f"Cannot parse Spark Ultra textual tool name: {content[:200]}")
    name = name_match.group(1)
    # 建立工具 schema映射
    schemas = {item["function"]["name"]: item["function"] for item in tools}
    # 检查工具白名单
    if name not in schemas:
        raise ValueError(f"Spark Ultra requested an unknown tool: {name}")
    # 取得允许的参数名
    allowed_parameters = set(
        schemas[name].get("parameters", {}).get("properties", {})
    )
    # 提取文本参数
    arguments = {
        parameter: unescape(value)
        for parameter, value in re.findall(
            r"<parameter=([A-Za-z_][A-Za-z0-9_]*)>(.*?)</parameter>",
            content,
            re.DOTALL, # 允许参数值中包含换行。
        )
        if parameter in allowed_parameters # 过滤额外参数
    }
    # 检查必填参数
    required = set(schemas[name].get("parameters", {}).get("required", []))
    # 计算缺少的参数：
    missing = required - arguments.keys()
    # 如果有缺失： 这样可以防止把不完整工具调用交给 CodingAgent。
    if missing:
        raise ValueError(f"Spark Ultra textual tool call is missing parameters: {sorted(missing)}")
    # 生成降级 ToolCall 工具调用ID
    return ToolCall(f"spark-text-{abs(hash(content))}", name, arguments)
