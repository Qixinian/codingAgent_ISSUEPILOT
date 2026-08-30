import json

from issuepilot.spark_ultra import SparkUltraModel, _parse_arguments, _parse_text_tool


def test_spark_ultra_uses_native_tool_calls() -> None:
    captured = {}
    function = type(
        "Function",
        (),
        {"name": "read_file", "arguments": json.dumps({"path": "app.py"})},
    )()
    call = type("Call", (), {"id": "call-1", "function": function})()
    message = type("Message", (), {"content": None, "tool_calls": [call]})()
    response = type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return response

    model = object.__new__(SparkUltraModel)
    model.client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    result = model.complete([{"role": "user", "content": "locate app"}], [{"type": "function"}])

    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments == {"path": "app.py"}
    assert captured["model"] == "4.0Ultra"
    assert captured["extra_body"] == {"tool_calls_switch": True}


def test_spark_ultra_retries_textual_tool_markup_as_required() -> None:
    text_message = type(
        "Message",
        (),
        {"content": "function=list_files></function>", "tool_calls": None},
    )()
    function = type("Function", (), {"name": "list_files", "arguments": "{}"})()
    call = type("Call", (), {"id": "call-2", "function": function})()
    tool_message = type("Message", (), {"content": None, "tool_calls": [call]})()
    responses = iter(
        [
            type("Response", (), {"choices": [type("Choice", (), {"message": text_message})()]})(),
            type("Response", (), {"choices": [type("Choice", (), {"message": tool_message})()]})(),
        ]
    )
    choices = []

    class Completions:
        def create(self, **kwargs):
            choices.append(kwargs["tool_choice"])
            return next(responses)

    model = object.__new__(SparkUltraModel)
    model.client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    result = model.complete([{"role": "user", "content": "list"}], [{"type": "function"}])
    assert result.tool_calls[0].name == "list_files"
    assert choices == ["auto", "required"]


def test_spark_ultra_accepts_raw_newlines_in_tool_arguments() -> None:
    raw = '{"path":"app.py","content":"line one\nline two"}'
    assert _parse_arguments(raw) == {
        "path": "app.py",
        "content": "line one\nline two",
    }


def test_spark_ultra_recovers_malformed_write_file_code() -> None:
    raw = (
        '{"path":"app.py","content":"from pydantic import field_validator\n'
        'message = "email is invalid"\n"}'
    )
    assert _parse_arguments(raw, "write_file") == {
        "path": "app.py",
        "content": 'from pydantic import field_validator\nmessage = "email is invalid"\n',
    }


def test_spark_ultra_parses_text_tool_with_schema_whitelist() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]
    call = _parse_text_tool(
        "I will read it function=read_file><parameter=path>app.py</parameter>"
        "<parameter=command>danger</parameter></function>",
        tools,
    )
    assert call.name == "read_file"
    assert call.arguments == {"path": "app.py"}


def test_spark_ultra_falls_back_after_two_text_tool_responses() -> None:
    message = type(
        "Message",
        (),
        {"content": "function=list_files></function>", "tool_calls": None},
    )()
    response = type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    class Completions:
        def create(self, **kwargs):
            return response

    model = object.__new__(SparkUltraModel)
    model.client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    tools = [{"type": "function", "function": {"name": "list_files", "parameters": {"properties": {}}}}]
    result = model.complete([{"role": "user", "content": "list"}], tools)
    assert result.tool_calls[0].name == "list_files"
