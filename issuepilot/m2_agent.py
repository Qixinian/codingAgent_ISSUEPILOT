"""
M2 : “下一步做什么”交给支持工具调用的模型决定

可以循环执行：
接收编程任务
    ↓
模型判断下一步
    ↓
调用工具查看/搜索/修改代码
    ↓
把工具结果交还模型
    ↓
模型继续判断
    ↓
运行测试并输出答案
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass # @dataclass：快速创建数据类  asdict()：把数据类对象转换成字典
from typing import Any, Protocol # Protocol：定义一个对象需要满足什么接口

from .m2_tools import CodingTools # CodingAgent 决定调用哪个工具，而真正的读文件、写文件、搜索和测试操作由 CodingTools 完成。

# 描述一次工具调用
@dataclass(frozen=True)  # frozen=True 表示对象创建后不能修改 这种操作会报错，可以防止调用信息被意外篡改。
class ToolCall:
    id: str  # 工具调用的唯一编号
    name: str # 工具名称
    arguments: dict[str, Any] # 调用工具需要的参数

# 统一模型返回格式 
@dataclass(frozen=True)
class ModelResponse: # 表示模型的一次回复
    content: str | None = None # 普通文字 
    tool_calls: tuple[ToolCall, ...] = () # 工具调用

# 模型接口协议 接口规范
class ToolCallingModel(Protocol):
    def complete(
        self, 
        messages: list[dict[str, Any]], # 模型的对话历史
        tools: list[dict[str, Any]] # 允许模型调用的工具定义
        ) -> ModelResponse: ...

# 智能体最终结果
@dataclass(frozen=True)
class AgentResult:
    content: str # 智能体最终回复
    steps: int # 模型进行了多少轮决策
    completed: bool # 是否正常完成任务
    trace: tuple[dict[str, Any], ...] # 执行过的工具调用记录

# 核心智能体
class CodingAgent:
    """
    这是整个文件的主要类。它负责连接：

       - 用户任务
       - 模型
       - 工具
       - 对话历史
       - 工具调用结果
       - 最终答案
    """

    # 初始化方法
    def __init__(
        self,  
        tools: CodingTools,  # 实际操作代码仓库的工具
        model: ToolCallingModel, # 能够做出决策并调用工具的模型
        max_steps: int = 12 # 最多允许模型决策多少轮，默认12轮
    ) -> None:
        # 检查最大步数
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        # 保存初始化参数
        self.tools, self.model, self.max_steps = tools, model, max_steps

    # 执行一个编程任务
    def run(self, task: str) -> AgentResult:
        # 创建初始消息
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
        # 创建轨迹列表： 用于记录所有工具调用。
        trace: list[dict[str, Any]] = []
        # 进入循环  每一轮代表模型进行一次决策。它不是“最多调用12次工具”。因为模型每轮可能一次提出多个工具调用，所以实际工具调用次数可能超过12次。
        for step in range(1, self.max_steps + 1):
            # 请求模型作出决策 messages：完整对话历史 TOOL_SCHEMAS：允许调用的工具说明
            response = self.model.complete(messages, TOOL_SCHEMAS)
            # 构造助手消息
            assistant: dict[str, Any] = {"role": "assistant", "content": response.content}
            # 处理模型提出的工具调用
            if response.tool_calls:
                # 如果模型请求了工具，就给助手消息增加 tool_calls 字段：
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
            # 把模型回复加入历史
            messages.append(assistant)
            # 判断任务是否结束
            if not response.tool_calls:
                if _latest_tests_passed(trace):
                    return AgentResult(response.content or "Task finished.", step, True, tuple(trace))
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "任务尚未完成：必须使用 run_tests，且最近一次测试的 exit_code 必须为 0。"
                            "请根据测试错误继续读取或修改代码，然后重新运行测试。"
                        ),
                    }
                )
                continue
            # 执行工具调用
            for call in response.tool_calls:
                # 执行工具
                result = self._execute(call)
                # 记录执行轨迹
                trace.append({"step": step, "tool": call.name, "arguments": call.arguments, "result": result})
                # 把工具结果加入对话
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)}
                )
        # 如果模型到第12轮仍不断调用工具，循环结束后返回：
        return AgentResult(f"Stopped after reaching max_steps={self.max_steps}.", self.max_steps, False, tuple(trace))
    # 工具分发器
    def _execute(self, call: ToolCall) -> dict[str, Any]:
        # 这个方法根据 call.name 决定调用 CodingTools 中的哪个方法。
        # 捕获异常
        try:
            # 列出文件
            if call.name == "list_files":
                return {"ok": True, "files": self.tools.list_files()}
            # 读取文件
            if call.name == "read_file":
                return {"ok": True, "content": self.tools.read_file(call.arguments["path"])}
            # 搜索代码
            if call.name == "search_code":
                return {"ok": True, "matches": self.tools.search_code(call.arguments["query"])}
            # 写入文件
            if call.name == "write_file":
                return {"ok": True, **asdict(self.tools.write_file(call.arguments["path"], call.arguments["content"]))}
            # 运行测试
            if call.name == "run_tests":
                return {"ok": True, **asdict(self.tools.run_tests())}

            # 如果模型请求不存在的工具： 这构成一个工具白名单：模型只能使用代码明确支持的五个工具。
            raise ValueError(f"Unknown tool: {call.name}")
        # 统一错误返回
        except (
            KeyError, # 工具缺少必要参数
            OSError,  # 文件不存在、权限不足等
            UnicodeError,  # 文件编码无法解析
            ValueError # 参数值无效或工具名未知
        ) as error:
            return {"ok": False, "error": type(error).__name__, "message": str(error)}


def _latest_tests_passed(trace: list[dict[str, Any]]) -> bool:
    test_events = [event for event in trace if event["tool"] == "run_tests"]
    if not test_events:
        return False
    result = test_events[-1]["result"]
    return (
        result.get("ok") is True
        and result.get("exit_code") == 0
        and result.get("timed_out") is False
    )

# 创建工具定义
def _schema(
    name: str,  # 工具叫什么
    description: str, # 工具做什么
    properties: dict[str, Any],  # 接受哪些参数
    required: list[str] | None = None # 哪些参数必须提供
) -> dict[str, Any]:
    # 构造参数结构
    parameters: dict[str, Any] = {
        "type": "object", # 工具参数必须是一个对象
        "properties": properties, # 定义允许的参数
        "additionalProperties": False # 禁止额外参数
    }
    # 添加必填参数
    if required:
        parameters["required"] = required
    # 返回完整工具结构
    return {
        "type": "function", 
        "function": {
            "name": name, 
            "description": description, 
            "parameters": parameters
        }
    }

# 模型可用的工具清单
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
