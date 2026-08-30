# IssuePilot M2

M2 adds a bounded coding loop, repository-scoped writes, fixed pytest execution,
structured tool errors, diffs, traces, and model adapters.

## Install

    python -m pip install -r requirements-m2.txt

## Native Function Calling

Set `OPENAI_API_KEY`, and optionally `OPENAI_BASE_URL` and `OPENAI_MODEL`.

    python -m issuepilot.m2_cli examples\\m2_bug "Fix calculator.add and make tests pass"

## Spark Lite test mode

Spark Lite does not support native Function Calling. This adapter uses JSON tool
selection, so use it for integration testing rather than a Function Calling demo.

    $env:SPARK_API_PASSWORD="YOUR_API_PASSWORD_HERE"
    python -m issuepilot.m2_spark_cli examples\\m2_bug "修复 add 函数并确保测试通过"

Never commit a real API password or put it in source files.

## Spark Ultra-32K native Function Calling

Use the APIPassword shown on the Spark Ultra-32K HTTP service page:

    $env:SPARK_ULTRA_API_PASSWORD="YOUR_ULTRA_API_PASSWORD_HERE"
    python -m issuepilot.m2_ultra_cli examples\\m2_bug "修复 add 函数并确保测试通过"
