# IssuePilot M3.1

M3.1 adds an asynchronous FastAPI service and SQLite persistence.

## Start the API

    python -m pip install -r requirements-m3.txt
    $env:SPARK_ULTRA_API_PASSWORD="YOUR_ULTRA_API_PASSWORD_HERE"
    python -m issuepilot.m3_cli --workspace D:\codexWork\IssuePilot --database D:\codexWork\IssuePilot\issuepilot.db

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.

## Create a task

    Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType application/json -Body '{"repository":"examples/m2_fastapi_email","task":"读取 TASK.md，增加邮箱格式校验并保证测试通过","max_steps":12}'

Use the returned task ID with:

    Invoke-RestMethod http://127.0.0.1:8000/tasks/TASK_ID
    Invoke-RestMethod http://127.0.0.1:8000/tasks/TASK_ID/events

Repository paths are resolved inside the configured workspace. Paths outside it are rejected.
Tasks left pending or running during a service restart are marked failed; their existing history remains available.

## Use a local Ollama model

The selected model must support tool calling. Start the API without a cloud key:

    python -m issuepilot.m3_cli --workspace D:\codexWork\IssuePilot --database D:\codexWork\IssuePilot\issuepilot.db --model-provider ollama --model qwen3:0.6b

Ollama must be running at `http://127.0.0.1:11434`. Override it with `OLLAMA_BASE_URL` if needed.
