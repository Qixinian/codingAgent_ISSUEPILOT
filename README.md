# IssuePilot

IssuePilot M1 是一个只读仓库定位 Agent。它提供三个受仓库目录约束的工具：

- `list_files`
- `read_file`
- `search_code`

## 运行

需要 Python 3.11+。在项目目录执行：

```powershell
python -m issuepilot examples/fastapi_app "登录接口定义在哪里？"
```

预期结果包含 `app.py:6` 和对应的 `/login` 代码依据。

## 测试

```powershell
python -m pytest
```

当前 M1 使用确定性的术语选择器，因此无需 API Key。后续里程碑可在保留工具边界的前提下接入支持 Function Calling 的模型。

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

## IssuePilot M2：三种模型的完整运行流程

### 共同主循环

![image-20260830174139432](D:\codexWork\IssuePilot\assets\image-20260830174139432.png)

### 普通Model

![image-20260830174609159](D:\codexWork\IssuePilot\assets\image-20260830174609159.png)

### Spark Lite

![image-20260830174627786](D:\codexWork\IssuePilot\assets\image-20260830174627786.png)

### Spark Ultra

![image-20260830174847256](D:\codexWork\IssuePilot\assets\image-20260830174847256.png)

### 差异总览

![image-20260830174941730](D:\codexWork\IssuePilot\assets\image-20260830174941730.png)

![image-20260830175716325](D:\codexWork\IssuePilot\assets\image-20260830175716325.png)

# 普通 Model、Lite、Ultra只在模型环节不同

本地工具执行过程完全相同：

```
ToolCall
   ↓
CodingAgent._execute()
   ↓
CodingTools
   ↓
工具结果
   ↓
加入messages
```

三者主要区别在于“怎样产生 `ToolCall`”。

## 普通 Model

接口原生返回：

```
message.tool_calls
```

转换成：

```
ToolCall(...)
```

## Spark Ultra

也是接口原生返回：

```
message.tool_calls
```

只是请求时额外使用：

```
tool_choice="auto"
extra_body={"tool_calls_switch": True}
```

## Spark Lite

没有原生工具调用，所以模型返回普通文字：

```
{
  "tool": "read_file",
  "arguments": {
    "path": "app.py"
  }
}
```

`spark_lite.py` 手动解析后创建：

```
ToolCall(
    id="spark-lite-call",
    name="read_file",
    arguments={"path": "app.py"},
)
```

从生成 `ToolCall` 以后，三者进入完全相同的 Agent和 Tools执行流程。
