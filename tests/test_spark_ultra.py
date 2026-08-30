import json

from issuepilot.spark_ultra import SparkUltraModel


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
