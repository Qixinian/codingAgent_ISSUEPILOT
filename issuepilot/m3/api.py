"""
IssuePilot M3 的 HTTP API入口文件。它使用 FastAPI把原来的命令行智能体包装成网络服务。

它的主要职责是：

定义客户端提交任务时需要的数据格式。
创建 FastAPI应用。
创建数据库和任务服务。
提供提交任务接口。
提供查询任务状态接口。
提供查询工具执行事件接口。

整体结构：
HTTP客户端
   │
   ├─ POST /tasks
   │      ↓
   │   TaskService.submit()
   │      ↓
   │   创建并执行Agent任务
   │      ↓
   │   TaskDatabase保存状态和事件
   │
   ├─ GET /tasks/{task_id}
   │      ↓
   │   查询任务状态
   │
   └─ GET /tasks/{task_id}/events
          ↓
       查询工具执行记录
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from .database import TaskDatabase
from .service import AgentFactory, TaskService, default_agent_factory

# 提交任务的请求模型 它定义客户端调用：POST /tasks 时，请求体必须是什么结构。
class TaskCreate(BaseModel):
    repository: str # 要操作的仓库路径
    task: str = Field(min_length=1) # 表示用户交给 Agent的编程任务。min_length=1 表示字符串长度至少为1
    max_steps: int = Field(default=12, ge=1, le=50) # 表示 Agent最多进行多少轮模型决策。

# 任务接受响应 定义提交任务成功后返回的JSON结构。
class TaskAccepted(BaseModel):
    task_id: str # 任务唯一编号。客户端后续通过它查询任务、事件
    status: str # 当前状态。创建任务后返回：pending  说明任务已接收，但不代表已经执行完成。

# 应用工厂 通过函数创建应用。
# create_app()
    # │
    # ├─ 创建 FastAPI
    # ├─ 创建 TaskDatabase
    # ├─ 创建 TaskService
    # │
    # └─ 注册三个接口
    #      ├─ POST /tasks
    #      ├─ GET /tasks/{task_id}
    #      └─ GET /tasks/{task_id}/events
def create_app(
    database_path: str | Path = "issuepilot.db", # 数据库文件路径
    workspace_root: str | Path = ".", # IssuePilot允许操作的工作区根目录
    agent_factory: AgentFactory = default_agent_factory, # “Agent工厂函数”，负责创建 CodingAgent。
) -> FastAPI:
    # 创建 FastAPI 应用 创建整个 Web应用。title: 自动接口文档显示的项目名称。
    app = FastAPI(title="IssuePilot", version="0.3.1")
    # 创建数据库对象 
    database = TaskDatabase(database_path)
    # 创建服务对象 
    service = TaskService(database, workspace_root, agent_factory)
    # 把对象放入 app.state（应用级状态容器。它可以保存整个应用运行期间需要共享的对象。）
    app.state.database = database
    app.state.task_service = service

    # 注册 POST/tasks 成HTTP接口。声明成功响应必须符合TaskAccepted，202 表示请求已被接受，但后台任务还不一定完成。
    @app.post("/tasks", response_model=TaskAccepted, status_code=status.HTTP_202_ACCEPTED)
    async def create_task(payload: TaskCreate) -> TaskAccepted: # 异步请求
        try:
            # 提交任务
            task_id = service.submit(payload.repository, payload.task, payload.max_steps)
        # 处理提交错误
        except (FileNotFoundError, NotADirectoryError, PermissionError) as error: # 仓库不存在错误/路径存在但是是文件错误/超越权限错误
            raise HTTPException(status_code=400, detail=str(error)) from error # 转换成HTTP 400
        # 返回任务接受结果
        return TaskAccepted(task_id=task_id, status="pending")

    # 注册任务查询接口 花括号表示动态路径参数。
    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> dict:
        # 从数据库查询任务 根据任务ID
        task = database.get_task(task_id)
        # 请求一个不存在的ID，返回404
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        # 返回任务状态
        return task

    # 注册事件查询接口 用于查询该任务的工具执行过程。
    @app.get("/tasks/{task_id}/events")
    async def get_events(task_id: str) -> list[dict]:
        # 先检查任务是否存在 不存在则返回404
        if not database.get_task(task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        # 返回事件记录
        return database.get_events(task_id)

    return app

