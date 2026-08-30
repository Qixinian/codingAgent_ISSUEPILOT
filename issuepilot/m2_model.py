"""
模型适配器
它负责把 CodingAgent 产生的对话消息和工具定义发送给 OpenAI兼容接口，再把接口返回的数据转换成 IssuePilot 内部统一使用的：
- ModelResponse
- ToolCall

整体数据流是：
CodingAgent
   │ messages + tools
   ▼
OpenAICompatibleModel.complete()
   │ 调用兼容接口
   ▼
模型返回普通文本或工具调用
   │ 解析响应
   ▼
ModelResponse
   │
   ▼
CodingAgent继续执行工具或结束任务
"""

from __future__ import annotations

import json
import os
from typing import Any

from .m2_agent import ModelResponse, ToolCall

# 定义模型适配器 封装了 OpenAI兼容接口。所谓“OpenAI兼容接口”，指的是服务使用与 OpenAI SDK相同或相近的请求格式
class OpenAICompatibleModel:
    # 初始化方法 创建模型对象时，可以传入模型名称，也可以不传。
    def __init__(self, model: str | None = None) -> None:
        # 读取 API密钥
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        
        # 动态导入 SDK
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install the dependency with: pip install openai") from error
        
        # 构造客户端选项
        options: dict[str, Any] = {"api_key": api_key} # 创建一个字典，保存初始化客户端所需的参数。
        # 读取自定义接口地址
        if base_url := os.getenv("OPENAI_BASE_URL"):
            options["base_url"] = base_url
        # 创建 API客户端
        self.client = OpenAI(**options)
        # 确定模型名称
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    # 它接收：messages：对话历史 tools：模型可调用的工具定义  返回ModelResponse
    def complete(
        self, 
        messages: list[dict[str, Any]], # 表示一个由多个消息字典组成的列表。每次调用模型时，都会发送完整历史，使模型知道：用户最初要求什么,自己之前调用过哪些工具,工具返回了哪些结果,当前应该继续做什么
        tools: list[dict[str, Any]] # 允许模型使用的工具说明。
    ) -> ModelResponse:
        # 发送模型请求
        response = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools)
        # 获取第一条模型结果
        message = response.choices[0].message
        # 解析工具调用
        calls = tuple(
            ToolCall(call.id, call.function.name, json.loads(call.function.arguments))
            for call in (message.tool_calls or [])
        )
        # 返回统一模型响应
        return ModelResponse(message.content, calls)

