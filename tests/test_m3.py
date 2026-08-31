from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from issuepilot.m2_agent import CodingAgent, ModelResponse, ToolCall
from issuepilot.m2_tools import CodingTools
from issuepilot.m3.api import create_app
from issuepilot.m3.database import TaskDatabase
from issuepilot.m3.service import TaskService


class ScriptedModel:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = iter(responses)

    def complete(self, messages, tools) -> ModelResponse:
        return next(self.responses)


def successful_factory(repository: Path, max_steps: int, event_handler):
    model = ScriptedModel(
        [
            ModelResponse(tool_calls=(ToolCall("1", "read_file", {"path": "value.py"}),)),
            ModelResponse(
                tool_calls=(ToolCall("2", "write_file", {"path": "value.py", "content": "value = 2\n"}),)
            ),
            ModelResponse(tool_calls=(ToolCall("3", "run_tests", {}),)),
            ModelResponse("Updated value and tests pass."),
        ]
    )
    return CodingAgent(CodingTools(repository), model, max_steps, event_handler)


def make_repository(path: Path) -> None:
    path.mkdir()
    (path / "value.py").write_text("value = 1\n", encoding="utf-8")
    (path / "test_value.py").write_text(
        "from value import value\n\ndef test_value():\n    assert value == 2\n",
        encoding="utf-8",
    )


def test_async_service_persists_task_and_events(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    make_repository(repository)
    database_path = tmp_path / "tasks.db"

    async def scenario() -> str:
        service = TaskService(TaskDatabase(database_path), tmp_path, successful_factory)
        task_id = service.submit("repo", "Update value", 8)
        while service.database.get_task(task_id)["status"] not in {"completed", "failed"}:
            await asyncio.sleep(0.01)
        return task_id

    task_id = asyncio.run(scenario())
    reopened = TaskDatabase(database_path)
    task = reopened.get_task(task_id)
    events = reopened.get_events(task_id)

    assert task["status"] == "completed"
    assert task["result"] == "Updated value and tests pass."
    tools = [event["tool"] for event in events]
    assert tools[0] == "agent_started"
    assert tools.count("model_request_started") == 4
    assert tools.count("model_response_received") == 4
    assert [tool for tool in tools if tool in {"read_file", "write_file", "run_tests"}] == [
        "read_file",
        "write_file",
        "run_tests",
    ]
    assert tools[-1] == "agent_completed"
    run_tests = next(event for event in events if event["tool"] == "run_tests")
    assert run_tests["result"]["exit_code"] == 0


def test_service_rejects_repository_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    service = TaskService(TaskDatabase(tmp_path / "tasks.db"), workspace, successful_factory)

    try:
        service.resolve_repository(str(outside))
    except PermissionError:
        pass
    else:
        raise AssertionError("outside repository should be rejected")


def test_async_service_persists_agent_failure(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    make_repository(repository)
    database = TaskDatabase(tmp_path / "failed.db")

    class FailingAgent:
        def run(self, task: str):
            raise RuntimeError("model unavailable")

    def failing_factory(repository, max_steps, event_handler):
        return FailingAgent()

    async def scenario() -> dict:
        service = TaskService(database, tmp_path, failing_factory)
        task_id = service.submit("repo", "Update value", 8)
        while database.get_task(task_id)["status"] not in {"completed", "failed"}:
            await asyncio.sleep(0.01)
        return database.get_task(task_id)

    task = asyncio.run(scenario())
    assert task["status"] == "failed"
    assert task["error"] == "RuntimeError: model unavailable"
    assert [event["tool"] for event in database.get_events(task["id"])] == [
        "agent_started",
        "agent_failed",
    ]


def test_model_wait_is_visible_before_response(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    make_repository(repository)
    database = TaskDatabase(tmp_path / "waiting.db")
    model_started = threading.Event()
    release_model = threading.Event()

    class BlockingModel:
        def complete(self, messages, tools) -> ModelResponse:
            model_started.set()
            release_model.wait(timeout=2)
            raise RuntimeError("stop test")

    def blocking_factory(repository, max_steps, event_handler):
        return CodingAgent(CodingTools(repository), BlockingModel(), max_steps, event_handler)

    async def scenario() -> list[dict]:
        service = TaskService(database, tmp_path, blocking_factory)
        task_id = service.submit("repo", "Update value", 8)
        assert await asyncio.to_thread(model_started.wait, 1)
        events = database.get_events(task_id)
        release_model.set()
        while database.get_task(task_id)["status"] not in {"completed", "failed"}:
            await asyncio.sleep(0.01)
        return events

    events = asyncio.run(scenario())
    assert [event["tool"] for event in events] == [
        "agent_started",
        "model_request_started",
    ]


def test_api_creates_and_queries_task(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    make_repository(repository)
    app = create_app(tmp_path / "api.db", tmp_path, successful_factory)

    with TestClient(app) as client:
        response = client.post(
            "/tasks",
            json={"repository": "repo", "task": "Update value", "max_steps": 8},
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        for _ in range(200):
            task = client.get(f"/tasks/{task_id}").json()
            if task["status"] in {"completed", "failed"}:
                break
            import time

            time.sleep(0.01)

        assert task["status"] == "completed"
        events = client.get(f"/tasks/{task_id}/events").json()
        tools = [event["tool"] for event in events]
        assert tools[0] == "agent_started"
        assert tools[-1] == "agent_completed"
        assert [tool for tool in tools if tool in {"read_file", "write_file", "run_tests"}] == [
            "read_file",
            "write_file",
            "run_tests",
        ]
        assert client.get("/tasks/missing").status_code == 404
        assert client.post("/tasks", json={"repository": "../", "task": "escape"}).status_code == 400
