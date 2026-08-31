"""
总体流程
    启动M3服务
    ↓
    选择模型提供商
    ├─ spark-ultra
    └─ ollama
    ↓
    create_agent_factory()
    ↓
    生成对应的Agent工厂
    ↓
    TaskService保存这个工厂
    ↓
    用户提交任务
    ↓
    工厂为该任务创建CodingAgent
    ↓
    后台线程运行Agent
    ↓
    工具事件写入数据库
    ↓
    更新任务最终状态

是业务服务层，位于 API、数据库和Agent之间。
    api.py
    接收HTTP请求
        ↓
    service.py
    验证路径、创建任务、启动后台执行
        ↓
    m2_agent.py
    模型与工具循环
        ↓
    database.py
    保存任务状态和工具事件
数据库可以保存完整地执行时间线：
    agent_started
        ↓
    model_request_started
        ↓
    model_response_received
        ↓
    list_files
        ↓
    model_request_started
        ↓
    model_response_received
        ↓
    read_file
        ↓
    ……
        ↓
    run_tests
        ↓
    model_request_started
        ↓
    model_response_received
        ↓
    agent_completed
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from ..m2_agent import CodingAgent
from ..m2_tools import CodingTools
from ..ollama_model import OllamaModel
from ..spark_ultra import SparkUltraModel
from .database import TaskDatabase

# Agent 运行接口 任何交给 TaskService 使用的对象，都必须具有 run(task) 方法。
class AgentRunner(Protocol):
    def run(self, task: str) -> Any: ...

# Agent工厂类型
AgentFactory = Callable[
    [
        Path, # Agent操作哪个仓库
        int,  # 最多进行多少轮模型决策
        Callable[ # 工具执行后的事件处理函数
            [dict[str, Any]], 
            None
        ]
    ], 
    AgentRunner # 返回 具有 run(task) 方法的Agent。
]

# 默认Agent工厂 创建默认的星火 Ultra Agent 如果 TaskService 没有传入其他工厂，就使用这个默认工厂
def default_agent_factory(
    repository: Path,
    max_steps: int,
    event_handler: Callable[[dict[str, Any]], None],
) -> CodingAgent:
    return CodingAgent(CodingTools(repository), SparkUltraModel(), max_steps, event_handler)

# 根据模型提供商名称，生成一个对应的Agent工厂函数。
def create_agent_factory(
    provider: str, # 模型提供商
    model: str | None = None # 模型名
) -> AgentFactory:
    # 每个Agent任务可以创建自己的模型适配器对象 selected_model  这样可以减少多个任务共享同一个客户端对象带来的状态和并发问题。
    # 星火Ultra selected_model:不是已经创建好的模型对象，而是一个创建模型的函数。
    if provider == "spark-ultra":
        selected_model = lambda: SparkUltraModel() # 等价 def selected_model():return SparkUltraModel()
    # Ollama 
    elif provider == "ollama":
        selected_model = lambda: OllamaModel(model)
    # 未知提供商
    else:
        raise ValueError(f"Unknown model provider: {provider}")

    # 内部函数 内部工厂创建Agent
    def factory(
        repository: Path,
        max_steps: int,
        event_handler: Callable[[dict[str, Any]], None],
    ) -> CodingAgent:
        return CodingAgent(
            CodingTools(repository),
            selected_model(),
            max_steps,
            event_handler,
        )

    return factory # 返回的是函数本身，不是执行结果。


class TaskService:
    # 初始化
    def __init__(
        self,
        database: TaskDatabase,
        workspace_root: str | Path,
        agent_factory: AgentFactory = default_agent_factory,
    ) -> None:
        self.database = database # 数据库
        self.workspace_root = Path(workspace_root).resolve(strict=True) # 解析工作区
        self.agent_factory = agent_factory # 保存工厂
        self.background_tasks: set[asyncio.Task[None]] = set() # 保存后台任务 保存当前进程中正在运行的异步任务对象。
        self.database.interrupt_running_tasks() # 处理中断任务 上一个服务进程已经结束，旧任务无法继续

    # 验证仓库
    def resolve_repository(self, repository: str) -> Path:
        candidate = (self.workspace_root / repository).resolve(strict=True)
        if candidate != self.workspace_root and self.workspace_root not in candidate.parents:
            raise PermissionError("Repository is outside the configured workspace")
        if not candidate.is_dir():
            raise NotADirectoryError(repository)
        return candidate

    # 提交任务
        # HTTP提交请求
        # ↓
        # create_task()
        # 让_run在后台协程执行
        # ↓
        # _run调用to_thread()
        # 让agent.run在工作线程执行
        # ↓
        # 事件循环继续服务其他请求
    def submit(self, repository: str, prompt: str, max_steps: int) -> str:
        path = self.resolve_repository(repository) # 验证仓库
        task_id = uuid4().hex # 生成任务ID
        self.database.create_task(task_id, str(path), prompt, max_steps) # 写入数据库
        # 创建后台任务 它让Agent任务在后台运行，而HTTP请求可以立即返回。
        background = asyncio.create_task(
            self._run(
                task_id, 
                path, 
                prompt, 
                max_steps
            )
        ) 
        # 保存任务引用
        self.background_tasks.add(background)
        # 任务结束后移除
        background.add_done_callback(self.background_tasks.discard)
        # 返回任务ID
        return task_id

    # 后台执行
    async def _run(self, task_id: str, repository: Path, prompt: str, max_steps: int) -> None:
        # 更新任务状态为running
        self.database.set_status(task_id, "running")
        # agent 开始事件
        self.database.add_event(
            task_id,
            {
                "step": 0,
                "tool": "agent_started",
                "arguments": {"max_steps": max_steps},
                "result": {"status": "running"},
            },
        )
        try:
            # 创建当前任务的Agent
            agent = self.agent_factory(
                repository,
                max_steps,
                lambda event: self.database.add_event(task_id, event),
            )
            # 在线程中运行Agent
                # 放到线程后：
                    # 工作线程
                    # 执行agent.run()

                    # FastAPI事件循环
                    # 继续处理HTTP请求
            result = await asyncio.to_thread(
                agent.run, # 是同步且耗时的。
                prompt
            )
            # 更新最终状态
            status = "completed" if result.completed else "failed"
            error = None if result.completed else result.content
            # 更新状态
            self.database.set_status(task_id, status, result.content, error)
            # agent正常结束事件
            self.database.add_event(
                task_id,
                {
                    "step": result.steps,
                    "tool": "agent_completed" if result.completed else "agent_failed",
                    "arguments": {},
                    "result": {"status": status, "steps": result.steps},
                },
            )
        # 捕获异常
        except Exception as error:
            self.database.set_status(task_id, "failed", error=f"{type(error).__name__}: {error}")
            # agent 发生异常事件
            self.database.add_event(
                task_id,
                {
                    "step": 0,
                    "tool": "agent_failed",
                    "arguments": {},
                    "result": {"status": "failed", "error_type": type(error).__name__},
                },
            )
