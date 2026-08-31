import json

from issuepilot.ollama_model import OllamaModel, _arguments, _ollama_messages


def test_ollama_converts_native_tool_call() -> None:
    captured = {}
    model = object.__new__(OllamaModel)
    model.model = "qwen3:4b"

    def fake_post(payload):
        captured.update(payload)
        return {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "read_file",
                            "arguments": {"path": "app.py"},
                        }
                    }
                ],
            }
        }

    model._post = fake_post
    result = model.complete([{"role": "user", "content": "read app"}], [{"type": "function"}])

    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments == {"path": "app.py"}
    assert captured["model"] == "qwen3:4b"
    assert captured["stream"] is False
    assert captured["think"] is False
    assert captured["options"] == {"temperature": 0, "num_predict": 1024}


def test_ollama_accepts_dictionary_arguments() -> None:
    assert _arguments({"query": "register"}) == {"query": "register"}


def test_ollama_converts_tool_history_to_tool_name() -> None:
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": json.dumps({"path": "app.py"})},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "file content"},
    ]
    converted = _ollama_messages(messages)
    assert converted[0]["tool_calls"][0]["function"]["arguments"] == {"path": "app.py"}
    assert converted[1]["tool_name"] == "read_file"
