from pathlib import Path

from issuepilot.m2_agent import CodingAgent, ModelResponse, ToolCall
from issuepilot.m2_tools import CodingTools
from issuepilot.spark_lite import SparkLiteModel


class ScriptedModel:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = iter(responses)
        self.messages = []

    def complete(self, messages, tools) -> ModelResponse:
        self.messages = messages
        return next(self.responses)


def test_agent_writes_code_runs_tests_and_finishes(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text(
        "def add(left, right):\n    return left - right\n", encoding="utf-8"
    )
    (tmp_path / "test_calculator.py").write_text(
        "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    model = ScriptedModel(
        [
            ModelResponse(tool_calls=(ToolCall("1", "read_file", {"path": "calculator.py"}),)),
            ModelResponse(tool_calls=(ToolCall(
                "2", "write_file",
                {"path": "calculator.py", "content": "def add(left, right):\n    return left + right\n"},
            ),)),
            ModelResponse(tool_calls=(ToolCall("3", "run_tests", {}),)),
            ModelResponse("Fixed add and all tests pass."),
        ]
    )
    result = CodingAgent(CodingTools(tmp_path), model).run("Fix add and pass tests")
    assert result.completed
    assert result.steps == 4
    assert [event["tool"] for event in result.trace] == ["read_file", "write_file", "run_tests"]
    assert result.trace[-1]["result"]["exit_code"] == 0
    first_call = model.messages[2]["tool_calls"][0]
    assert first_call["type"] == "function"
    assert first_call["function"]["name"] == "read_file"


def test_agent_returns_tool_errors_to_model(tmp_path: Path) -> None:
    model = ScriptedModel([
        ModelResponse(tool_calls=(ToolCall("1", "read_file", {"path": "../secret"}),)),
        ModelResponse("Recovered from the tool error."),
    ])
    result = CodingAgent(CodingTools(tmp_path), model).run("Read an invalid path")
    assert result.completed
    assert result.trace[0]["result"]["ok"] is False


def test_agent_stops_at_max_steps(tmp_path: Path) -> None:
    model = ScriptedModel([
        ModelResponse(tool_calls=(ToolCall(str(index), "list_files", {}),)) for index in range(2)
    ])
    result = CodingAgent(CodingTools(tmp_path), model, max_steps=2).run("Never finish")
    assert not result.completed
    assert result.steps == 2


def test_spark_lite_puts_contract_in_user_message() -> None:
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = type("Message", (), {"content": '{"final":"done"}'})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    client = type(
        "Client",
        (),
        {"chat": type("Chat", (), {"completions": Completions()})()},
    )()
    model = object.__new__(SparkLiteModel)
    model.client = client
    response = model.complete(
        [{"role": "system", "content": "agent rules"}, {"role": "user", "content": "task"}],
        [],
    )
    assert response.content == "done"
    assert [message["role"] for message in captured["messages"]] == ["user"]
    assert "agent rules" in captured["messages"][0]["content"]
    assert "只输出一个 JSON 对象" in captured["messages"][0]["content"]


def test_spark_lite_retries_non_json_response() -> None:
    responses = iter(["普通解释", '{"final":"done"}'])
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            message = type("Message", (), {"content": next(responses)})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    model = object.__new__(SparkLiteModel)
    model.client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    response = model.complete([{"role": "user", "content": "task"}], [])
    assert response.content == "done"
    assert len(calls) == 2


def test_spark_lite_retries_empty_final() -> None:
    responses = iter(['{"final":null}', '{"tool":"list_files","arguments":{}}'])

    class Completions:
        def create(self, **kwargs):
            message = type("Message", (), {"content": next(responses)})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    model = object.__new__(SparkLiteModel)
    model.client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    tools = [{"type": "function", "function": {"name": "list_files"}}]
    response = model.complete([{"role": "user", "content": "task"}], tools)
    assert response.tool_calls[0].name == "list_files"
